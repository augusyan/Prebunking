from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import re
import sqlite3
from pathlib import Path


METRICS = ("malicious_ir_pct", "benign_support_pct", "benign_disagreement_pct")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate benign-flow selectivity metrics across arbitrary condition file globs."
        )
    )
    parser.add_argument("--label", required=True, help="Output prefix label.")
    parser.add_argument(
        "--output-dir", required=True, help="Directory to write summary outputs."
    )
    parser.add_argument(
        "--reference-condition",
        default="no_defense",
        help="Condition key used as the paired-delta reference.",
    )
    parser.add_argument(
        "--condition",
        action="append",
        default=[],
        help=(
            "Condition spec in the form key=glob. "
            "The glob should match metrics JSON files ending in _metrics.json."
        ),
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


def load_condition_rows(condition: str, metrics_paths: list[Path]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for metrics_path in sorted(metrics_paths):
        stem = metrics_path.stem.removesuffix("_metrics")
        run_root = metrics_path.parent.parent
        csv_path = run_root / "csv" / f"{stem}.csv"
        db_path = run_root / "db" / f"{stem}.db"
        good_user_ids = load_good_user_ids(csv_path)
        benign_flow = compute_benign_flow(db_path, good_user_ids)
        rows.append(
            {
                "condition": condition,
                "seed": parse_seed(metrics_path),
                "label": stem,
                "metrics_path": str(metrics_path),
                "csv_path": str(csv_path),
                "db_path": str(db_path),
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
        "metrics_path",
        "csv_path",
        "db_path",
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


def build_markdown(
    label: str,
    raw_rows: list[dict[str, object]],
    summaries: list[dict[str, object]],
    paired_summaries: dict[str, dict[str, object]],
    reference_condition: str,
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
                    str(row["condition"]),
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
                    str(summary["condition"]),
                    str(summary["n"]),
                    f"{metrics['malicious_ir_pct']['mean']:.2f} ± {metrics['malicious_ir_pct']['std']:.2f}",
                    f"{metrics['benign_support_pct']['mean']:.2f} ± {metrics['benign_support_pct']['std']:.2f}",
                    f"{metrics['benign_disagreement_pct']['mean']:.2f} ± {metrics['benign_disagreement_pct']['std']:.2f}",
                ]
            )
            + " |"
        )

    lines.extend([f"", f"## Paired Deltas vs {reference_condition}", ""])
    for condition, payload in paired_summaries.items():
        metrics = payload["metrics"]
        lines.extend(
            [
                f"### {condition} vs {reference_condition}",
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


def parse_condition_specs(specs: list[str]) -> list[tuple[str, list[Path]]]:
    parsed: list[tuple[str, list[Path]]] = []
    for spec in specs:
        if "=" not in spec:
            raise ValueError(f"Invalid --condition spec: {spec}")
        name, pattern = spec.split("=", 1)
        matched = [Path(path) for path in sorted(glob.glob(pattern))]
        if not matched:
            raise ValueError(f"No files matched pattern for condition {name}: {pattern}")
        parsed.append((name, matched))
    return parsed


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    condition_specs = parse_condition_specs(args.condition)

    raw_rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    rows_by_condition: dict[str, list[dict[str, object]]] = {}

    for condition, metrics_paths in condition_specs:
        condition_rows = load_condition_rows(condition, metrics_paths)
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
    ordered_summaries = summaries

    paired_summaries: dict[str, dict[str, object]] = {}
    reference_rows = rows_by_condition.get(args.reference_condition, [])
    for condition, _metrics_paths in condition_specs:
        if condition == args.reference_condition:
            continue
        paired_summaries[condition] = paired_delta(reference_rows, rows_by_condition[condition])

    raw_csv_path = output_dir / f"{args.label}_raw_seeds.csv"
    summary_csv_path = output_dir / f"{args.label}_summary.csv"
    summary_json_path = output_dir / f"{args.label}_summary.json"
    summary_md_path = output_dir / f"{args.label}_summary.md"

    write_raw_csv(raw_csv_path, raw_rows)
    write_summary_csv(summary_csv_path, ordered_summaries)
    summary_json_path.write_text(
        json.dumps(
            {
                "label": args.label,
                "reference_condition": args.reference_condition,
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
        build_markdown(
            args.label,
            raw_rows,
            ordered_summaries,
            paired_summaries,
            args.reference_condition,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "raw_csv": str(raw_csv_path),
                "summary_csv": str(summary_csv_path),
                "summary_json": str(summary_json_path),
                "summary_md": str(summary_md_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
