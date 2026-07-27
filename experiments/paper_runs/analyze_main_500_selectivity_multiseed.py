#!/usr/bin/env python3

import argparse
import csv
import json
import math
import re
import sqlite3
from pathlib import Path


METRICS = ("malicious_ir_pct", "benign_support_pct", "benign_disagreement_pct")
CONDITION_LABELS = {
    "no_defense": "No Defense",
    "debunking": "Debunking",
    "prebunking": "Prebunking",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Estimate benign-post support/disagreement for main_500 multiseed runs "
            "from existing user CSVs, SQLite DBs, and paper-facing metrics."
        )
    )
    parser.add_argument(
        "--run-root",
        required=True,
        help="Run directory containing csv/, db/, and metrics/ subdirectories.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for summary outputs.",
    )
    parser.add_argument(
        "--label",
        default="main_500_selectivity_multiseed",
        help="Output prefix.",
    )
    parser.add_argument(
        "--conditions",
        nargs="+",
        default=["no_defense", "prebunking", "debunking"],
        help="Ordered condition list to aggregate.",
    )
    return parser.parse_args()


def parse_seed(path: Path) -> int | None:
    match = re.search(r"seed_(\d+)", path.stem)
    return int(match.group(1)) if match else None


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def sample_std(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    mu = mean(values)
    return math.sqrt(sum((value - mu) ** 2 for value in values) / (len(values) - 1))


def ci95(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    return 1.96 * sample_std(values) / math.sqrt(len(values))


def condition_label(condition: str) -> str:
    return CONDITION_LABELS.get(condition, condition.replace("_", " ").title())


def load_good_user_ids(csv_path: Path) -> set[int]:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {
        int(row["user_id"])
        for row in rows
        if not row["user_type"].startswith("bad")
    }


def compute_benign_flow(db_path: Path, good_user_ids: set[int]) -> dict[str, float | int]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    ordered_good_ids = sorted(good_user_ids)
    placeholders = ",".join("?" for _ in ordered_good_ids)
    benign_root_post_ids = [
        row[0]
        for row in cur.execute(
            f"""
            SELECT post_id
            FROM post
            WHERE original_post_id IS NULL
              AND user_id IN ({placeholders})
            """,
            tuple(ordered_good_ids),
        )
    ]
    if not benign_root_post_ids:
        return {
            "benign_user_count": len(good_user_ids),
            "benign_root_post_count": 0,
            "support_user_count": 0,
            "disagreement_user_count": 0,
            "benign_support_pct": 0.0,
            "benign_disagreement_pct": 0.0,
        }

    post_placeholders = ",".join("?" for _ in benign_root_post_ids)
    post_args = tuple(benign_root_post_ids)

    support_users: set[int] = set()
    disagreement_users: set[int] = set()

    for (user_id,) in cur.execute(
        f"SELECT DISTINCT user_id FROM like WHERE post_id IN ({post_placeholders})",
        post_args,
    ):
        if user_id in good_user_ids:
            support_users.add(user_id)

    for (user_id,) in cur.execute(
        f"SELECT DISTINCT user_id FROM post WHERE original_post_id IN ({post_placeholders})",
        post_args,
    ):
        if user_id in good_user_ids:
            support_users.add(user_id)

    for user_id, agree in cur.execute(
        f"SELECT user_id, agree FROM comment WHERE post_id IN ({post_placeholders})",
        post_args,
    ):
        if user_id not in good_user_ids:
            continue
        if int(agree) == 1:
            support_users.add(user_id)
        else:
            disagreement_users.add(user_id)

    for (user_id,) in cur.execute(
        f"SELECT DISTINCT user_id FROM dislike WHERE post_id IN ({post_placeholders})",
        post_args,
    ):
        if user_id in good_user_ids:
            disagreement_users.add(user_id)

    benign_user_count = len(good_user_ids)
    return {
        "benign_user_count": benign_user_count,
        "benign_root_post_count": len(benign_root_post_ids),
        "support_user_count": len(support_users),
        "disagreement_user_count": len(disagreement_users),
        "benign_support_pct": 100.0 * len(support_users) / benign_user_count,
        "benign_disagreement_pct": 100.0 * len(disagreement_users) / benign_user_count,
    }


def load_malicious_ir(metrics_path: Path) -> float:
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    return float(payload["macro"]["infection_rate_pct"])


def load_condition_rows(run_root: Path, condition: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    metrics_dir = run_root / "metrics"
    for metrics_path in sorted(metrics_dir.glob(f"*_{condition}_metrics.json")):
        stem = metrics_path.stem.removesuffix("_metrics")
        seed = parse_seed(metrics_path)
        csv_path = run_root / "csv" / f"{stem}.csv"
        db_path = run_root / "db" / f"{stem}.db"
        good_user_ids = load_good_user_ids(csv_path)
        benign_flow = compute_benign_flow(db_path, good_user_ids)
        rows.append(
            {
                "condition": condition,
                "seed": seed,
                "label": stem,
                "malicious_ir_pct": load_malicious_ir(metrics_path),
                **benign_flow,
            }
        )
    return rows


def summarize(rows: list[dict[str, object]]) -> dict[str, dict[str, float]]:
    summary: dict[str, dict[str, float]] = {}
    for metric_name in METRICS:
        values = [float(row[metric_name]) for row in rows]
        summary[metric_name] = {
            "mean": mean(values),
            "std": sample_std(values),
            "ci95": ci95(values),
        }
    return summary


def paired_delta(
    reference_rows: list[dict[str, object]],
    target_rows: list[dict[str, object]],
) -> dict[str, dict[str, float] | int | list[int]]:
    reference_by_seed = {
        int(row["seed"]): row
        for row in reference_rows
        if row["seed"] is not None
    }
    target_by_seed = {
        int(row["seed"]): row
        for row in target_rows
        if row["seed"] is not None
    }
    shared_seeds = sorted(set(reference_by_seed) & set(target_by_seed))
    metrics: dict[str, dict[str, float]] = {}
    for metric_name in METRICS:
        deltas = [
            float(target_by_seed[seed][metric_name]) - float(reference_by_seed[seed][metric_name])
            for seed in shared_seeds
        ]
        metrics[metric_name] = {
            "delta_mean": mean(deltas),
            "delta_std": sample_std(deltas),
            "delta_ci95": ci95(deltas),
        }
    return {
        "shared_n": len(shared_seeds),
        "shared_seeds": shared_seeds,
        "metrics": metrics,
    }


def write_raw_csv(output_path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "seed",
        "condition",
        "label",
        "malicious_ir_pct",
        "benign_support_pct",
        "benign_disagreement_pct",
        "benign_user_count",
        "benign_root_post_count",
        "support_user_count",
        "disagreement_user_count",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_summary_csv(output_path: Path, summaries: list[dict[str, object]]) -> None:
    fieldnames = ["condition", "n"]
    for metric_name in METRICS:
        fieldnames.extend(
            [
                f"{metric_name}_mean",
                f"{metric_name}_std",
                f"{metric_name}_ci95",
            ]
        )
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for summary in summaries:
            row = {
                "condition": summary["condition"],
                "n": summary["n"],
            }
            metric_summary = summary["metrics"]
            for metric_name in METRICS:
                row[f"{metric_name}_mean"] = f"{metric_summary[metric_name]['mean']:.4f}"
                row[f"{metric_name}_std"] = f"{metric_summary[metric_name]['std']:.4f}"
                row[f"{metric_name}_ci95"] = f"{metric_summary[metric_name]['ci95']:.4f}"
            writer.writerow(row)


def format_pct(value: float) -> str:
    return f"{value:.2f}\\%"


def format_stat(stat: dict[str, float]) -> str:
    return f"{stat['mean']:.2f} ± {stat['std']:.2f}"


def build_markdown(
    label: str,
    raw_rows: list[dict[str, object]],
    summaries: list[dict[str, object]],
    paired_summaries: dict[str, dict[str, object]],
) -> str:
    lines = [
        f"# {label}",
        "",
        "## Raw Seed Rows",
        "",
        "| Seed | Condition | Malicious IR | Benign Support | Benign Disagreement | Benign Root Posts |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in raw_rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["seed"]),
                    condition_label(str(row["condition"])),
                    f"{float(row['malicious_ir_pct']):.2f}",
                    f"{float(row['benign_support_pct']):.2f}",
                    f"{float(row['benign_disagreement_pct']):.2f}",
                    str(row["benign_root_post_count"]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Condition Summary",
            "",
            "| Condition | n | Malicious IR | Benign Support | Benign Disagreement |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for summary in summaries:
        metrics = summary["metrics"]
        lines.append(
            "| "
            + " | ".join(
                [
                    condition_label(str(summary["condition"])),
                    str(summary["n"]),
                    format_stat(metrics["malicious_ir_pct"]),
                    format_stat(metrics["benign_support_pct"]),
                    format_stat(metrics["benign_disagreement_pct"]),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Paired Deltas vs No Defense", ""])
    for condition, payload in paired_summaries.items():
        metrics = payload["metrics"]
        lines.extend(
            [
                f"### {condition_label(condition)} vs No Defense",
                f"- Shared seeds: {', '.join(str(seed) for seed in payload['shared_seeds'])}",
                f"- Malicious IR delta: {metrics['malicious_ir_pct']['delta_mean']:+.2f} ± {metrics['malicious_ir_pct']['delta_ci95']:.2f}",
                f"- Benign support delta: {metrics['benign_support_pct']['delta_mean']:+.2f} ± {metrics['benign_support_pct']['delta_ci95']:.2f}",
                f"- Benign disagreement delta: {metrics['benign_disagreement_pct']['delta_mean']:+.2f} ± {metrics['benign_disagreement_pct']['delta_ci95']:.2f}",
                "",
            ]
        )

    lines.extend(
        [
            "## Notes",
            "- Benign support counts distinct benign users who liked, reposted, or agreed with benign root posts authored by benign users in the same run.",
            "- Benign disagreement counts distinct benign users who disliked or publicly disagreed with those benign root posts.",
            "- This remains an in-simulator benign-flow proxy rather than a matched verified-news benchmark.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_latex_table(raw_rows: list[dict[str, object]], summaries: list[dict[str, object]]) -> str:
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\scriptsize",
        r"\setlength{\tabcolsep}{6pt}",
        r"\caption{Auxiliary benign-post flow check for the headline full-coverage condition across the same five seeds used in the main macro comparison.}",
        r"\label{tab:appendix_selectivity_checks}",
        r"\begin{threeparttable}",
        r"\begin{tabularx}{\textwidth}{",
        r"  >{\centering\arraybackslash}p{0.08\textwidth}",
        r"  >{\raggedright\arraybackslash}p{0.29\textwidth}",
        r"  *{3}{>{\centering\arraybackslash}X}",
        r"}",
        r"\toprule",
        r"\textbf{Seed} & \textbf{Condition} & \textbf{\shortstack{Malicious\\IR}} & \textbf{\shortstack{Benign\\Support}} & \textbf{\shortstack{Benign\\Disagreement}} \\",
        r"\midrule",
    ]

    ordered_conditions = {summary["condition"]: summary for summary in summaries}
    for row in raw_rows:
        lines.append(
            " & ".join(
                [
                    str(row["seed"]),
                    condition_label(str(row["condition"])),
                    format_pct(float(row["malicious_ir_pct"])),
                    format_pct(float(row["benign_support_pct"])),
                    format_pct(float(row["benign_disagreement_pct"])),
                ]
            )
            + r" \\"
        )

    lines.append(r"\midrule")
    for condition in ["no_defense", "prebunking"]:
        if condition not in ordered_conditions:
            continue
        summary = ordered_conditions[condition]
        metrics = summary["metrics"]
        lines.append(
            " & ".join(
                [
                    r"\textbf{Mean $\pm$ SD}",
                    rf"\textbf{{{condition_label(condition)}}}",
                    rf"\textbf{{{metrics['malicious_ir_pct']['mean']:.2f} $\pm$ {metrics['malicious_ir_pct']['std']:.2f}\%}}",
                    rf"\textbf{{{metrics['benign_support_pct']['mean']:.2f} $\pm$ {metrics['benign_support_pct']['std']:.2f}\%}}",
                    rf"\textbf{{{metrics['benign_disagreement_pct']['mean']:.2f} $\pm$ {metrics['benign_disagreement_pct']['std']:.2f}\%}}",
                ]
            )
            + r" \\"
        )

    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabularx}",
            r"\begin{tablenotes}[flushleft]",
            r"\footnotesize",
            r"\item Benign support counts distinct benign agents who liked, reposted, or agreed with benign root posts authored by ordinary benign users in the same run.",
            r"\item Benign disagreement counts distinct benign agents who disliked or publicly disagreed with those benign root posts.",
            r"\item Unlike the earlier lower-intensity sanity check, this table directly evaluates the headline full-coverage condition on the same five seeds as the main macro comparison. It still remains an in-simulator proxy rather than a matched external verified-news benchmark.",
            r"\end{tablenotes}",
            r"\end{threeparttable}",
            r"\end{table*}",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    run_root = Path(args.run_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    rows_by_condition: dict[str, list[dict[str, object]]] = {}

    for condition in args.conditions:
        condition_rows = load_condition_rows(run_root, condition)
        raw_rows.extend(condition_rows)
        rows_by_condition[condition] = condition_rows
        summaries.append(
            {
                "condition": condition,
                "n": len(condition_rows),
                "metrics": summarize(condition_rows),
            }
        )

    raw_rows.sort(key=lambda row: (int(row["seed"]) if row["seed"] is not None else 10**9, str(row["condition"])))
    summary_by_condition = {summary["condition"]: summary for summary in summaries}
    ordered_summaries = [summary_by_condition[condition] for condition in args.conditions if condition in summary_by_condition]

    paired_summaries: dict[str, dict[str, object]] = {}
    reference_rows = rows_by_condition.get("no_defense", [])
    for condition in args.conditions:
        if condition == "no_defense" or condition not in rows_by_condition:
            continue
        paired_summaries[condition] = paired_delta(reference_rows, rows_by_condition[condition])

    raw_csv_path = output_dir / f"{args.label}_raw_seeds.csv"
    summary_csv_path = output_dir / f"{args.label}_summary.csv"
    summary_json_path = output_dir / f"{args.label}_summary.json"
    summary_md_path = output_dir / f"{args.label}_summary.md"
    table_tex_path = output_dir / f"{args.label}_table.tex"

    write_raw_csv(raw_csv_path, raw_rows)
    write_summary_csv(summary_csv_path, ordered_summaries)
    summary_json_path.write_text(
        json.dumps(
            {
                "label": args.label,
                "raw_rows": raw_rows,
                "conditions": ordered_summaries,
                "paired_deltas": paired_summaries,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    summary_md_path.write_text(
        build_markdown(args.label, raw_rows, ordered_summaries, paired_summaries),
        encoding="utf-8",
    )
    table_tex_path.write_text(
        build_latex_table(raw_rows, ordered_summaries),
        encoding="utf-8",
    )

    print(json.dumps(
        {
            "raw_csv": str(raw_csv_path),
            "summary_csv": str(summary_csv_path),
            "summary_json": str(summary_json_path),
            "summary_md": str(summary_md_path),
            "table_tex": str(table_tex_path),
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
