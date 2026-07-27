#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path


METRIC_PATHS = {
    "infection_rate_pct": ("macro", "infection_rate_pct"),
    "resistance_rate_pct": ("macro", "resistance_rate_pct"),
    "treated_infection_rate_pct": ("group_macro", "treated_benign", "infection_rate_pct"),
    "treated_resistance_rate_pct": ("group_macro", "treated_benign", "resistance_rate_pct"),
    "untreated_infection_rate_pct": ("group_macro", "untreated_benign", "infection_rate_pct"),
    "untreated_resistance_rate_pct": ("group_macro", "untreated_benign", "resistance_rate_pct"),
    "treated_benign_user_count": ("treated_benign_user_count",),
    "untreated_benign_user_count": ("untreated_benign_user_count",),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate multi-seed prebunking ablation metrics."
    )
    parser.add_argument("--metrics-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--label",
        default="main_500_prebunking_ablation_multiseed",
        help="Output label prefix.",
    )
    parser.add_argument(
        "--cases",
        nargs="+",
        required=True,
        help="Ordered ablation case keys to aggregate.",
    )
    return parser.parse_args()


def nested_get(obj: dict, path: tuple[str, ...]) -> float | None:
    current = obj
    for key in path:
        if key not in current:
            return None
        current = current[key]
    return float(current)


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


def format_stat(stat: dict[str, float | int | None]) -> str:
    if stat["mean"] is None:
        return "n/a"
    return f"{stat['mean']:.2f} ± {stat['std']:.2f} (CI ± {stat['ci95']:.2f})"


def case_label(case_key: str) -> str:
    return case_key.replace("_", " ").title()


def load_case_rows(metrics_dir: Path, case_key: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for metrics_path in sorted(metrics_dir.glob(f"*ablation_{case_key}_seed_*_metrics.json")):
        payload = json.loads(metrics_path.read_text(encoding="utf-8"))
        row: dict[str, object] = {
            "path": str(metrics_path),
            "seed": parse_seed(metrics_path),
        }
        for metric_name, metric_path in METRIC_PATHS.items():
            row[metric_name] = nested_get(payload, metric_path)
        rows.append(row)
    return rows


def summarize(rows: list[dict[str, object]]) -> dict[str, dict[str, float | int | None]]:
    summary: dict[str, dict[str, float | int | None]] = {}
    for metric_name in METRIC_PATHS:
        values = [
            float(value)
            for row in rows
            if (value := row.get(metric_name)) is not None and not math.isnan(float(value))
        ]
        if values:
            summary[metric_name] = {
                "mean": mean(values),
                "std": sample_std(values),
                "ci95": ci95(values),
                "n_valid": len(values),
            }
        else:
            summary[metric_name] = {
                "mean": None,
                "std": None,
                "ci95": None,
                "n_valid": 0,
            }
    return summary


def write_csv(output_path: Path, summaries: list[dict[str, object]]) -> None:
    fieldnames = ["case", "n"]
    for metric_name in METRIC_PATHS:
        fieldnames.extend(
            [
                f"{metric_name}_mean",
                f"{metric_name}_std",
                f"{metric_name}_ci95",
                f"{metric_name}_n_valid",
            ]
        )

    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for summary in summaries:
            row = {"case": summary["case"], "n": summary["n"]}
            metric_summary = summary["metrics"]
            for metric_name in METRIC_PATHS:
                stat = metric_summary[metric_name]
                row[f"{metric_name}_mean"] = "" if stat["mean"] is None else f"{stat['mean']:.4f}"
                row[f"{metric_name}_std"] = "" if stat["std"] is None else f"{stat['std']:.4f}"
                row[f"{metric_name}_ci95"] = "" if stat["ci95"] is None else f"{stat['ci95']:.4f}"
                row[f"{metric_name}_n_valid"] = stat["n_valid"]
            writer.writerow(row)


def build_markdown(label: str, summaries: list[dict[str, object]]) -> str:
    headers = [
        "Case",
        "n",
        "IR %",
        "RR %",
        "Treated IR %",
        "Untreated IR %",
        "Treated RR %",
        "Untreated RR %",
    ]
    divider = "| " + " | ".join(["---"] + [":---:" for _ in headers[1:]]) + " |"
    lines = [
        f"# {label}",
        "",
        "| " + " | ".join(headers) + " |",
        divider,
    ]
    for summary in summaries:
        metrics = summary["metrics"]
        lines.append(
            "| "
            + " | ".join(
                [
                    str(summary["case"]),
                    str(summary["n"]),
                    format_stat(metrics["infection_rate_pct"]),
                    format_stat(metrics["resistance_rate_pct"]),
                    format_stat(metrics["treated_infection_rate_pct"]),
                    format_stat(metrics["untreated_infection_rate_pct"]),
                    format_stat(metrics["treated_resistance_rate_pct"]),
                    format_stat(metrics["untreated_resistance_rate_pct"]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Notes",
            "- Each cell reports mean ± sample std with a normal-approximation 95% confidence interval half-width.",
            "- Treated/untreated metrics are computed from the agent CSV: role-rewritten benign agents and benign agents marked with the prebunking exposure tag count as treated.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    metrics_dir = Path(args.metrics_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    summaries: list[dict[str, object]] = []
    for case_key in args.cases:
        rows = load_case_rows(metrics_dir, case_key)
        summaries.append(
            {
                "case": case_label(case_key),
                "case_key": case_key,
                "n": len(rows),
                "rows": rows,
                "metrics": summarize(rows),
            }
        )

    json_path = output_dir / f"{args.label}_summary.json"
    csv_path = output_dir / f"{args.label}_summary.csv"
    md_path = output_dir / f"{args.label}_summary.md"

    json_path.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    write_csv(csv_path, summaries)
    md_path.write_text(build_markdown(args.label, summaries), encoding="utf-8")

    print(
        json.dumps(
            {
                "json": str(json_path),
                "csv": str(csv_path),
                "markdown": str(md_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
