#!/usr/bin/env python3

import argparse
import csv
import json
import math
import re
from pathlib import Path


METRICS = {
    "infection_rate_pct": ("macro", "infection_rate_pct"),
    "resistance_rate_pct": ("macro", "resistance_rate_pct"),
    "agree_comment_pct": ("micro", "stance_comment_pct", "agree_true"),
    "disagree_comment_pct": ("micro", "stance_comment_pct", "agree_false"),
    "peak_infection_proxy_value": ("time_series", "peak_infection_proxy_value"),
    "peak_resistance_value": ("time_series", "peak_resistance_value"),
}

PAIRWISE_METRICS = ("infection_rate_pct", "resistance_rate_pct")
MAIN_RUN_PATTERNS = (
    ("no_defense", "No Defense", "main_500_seed_*_no_defense_metrics.json"),
    (
        "main_debunking_t5_postcov50",
        "Debunking t=5 50% post coverage",
        "main_500_seed_*_debunking_metrics.json",
    ),
    ("prebunking_full", "Prebunking Full Coverage", "main_500_seed_*_prebunking_metrics.json"),
)
T_CRITICAL_95 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate multi-seed debunking fairness metrics with paired deltas."
    )
    parser.add_argument("--metrics-dir", required=True, help="Directory with fairness *_metrics.json files.")
    parser.add_argument("--output-dir", required=True, help="Directory for summary outputs.")
    parser.add_argument("--label", default="debunking_fairness_multiseed", help="Output label prefix.")
    parser.add_argument(
        "--case-specs",
        required=True,
        help="Whitespace-separated case specs in case_key:timestep:coverage format.",
    )
    parser.add_argument(
        "--main-metrics-dir",
        default=None,
        help="Optional main multiseed metrics directory for No Defense / main Debunking / Prebunking comparisons.",
    )
    return parser.parse_args()


def nested_get(obj: dict, path: tuple[str, ...]) -> float:
    current = obj
    for key in path:
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


def ci95_t(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    df = len(values) - 1
    critical = T_CRITICAL_95.get(df, 1.96)
    return critical * sample_std(values) / math.sqrt(len(values))


def cohen_dz(values: list[float]) -> float:
    std = sample_std(values)
    if len(values) <= 1 or std == 0.0:
        return 0.0
    return mean(values) / std


def format_stat(stat: dict[str, float]) -> str:
    return f"{stat['mean']:.2f} ± {stat['std']:.2f} (t-CI ± {stat['ci95_t']:.2f})"


def case_key_to_display(case_key: str) -> str:
    timestep_match = re.search(r"t(\d+)", case_key)
    coverage_match = re.search(r"postcov(\d+)", case_key)
    if timestep_match and coverage_match:
        return (
            f"Debunking t={timestep_match.group(1)} "
            f"{coverage_match.group(1)}% post coverage"
        )
    return case_key.replace("_", " ").title()


def load_rows_from_paths(paths: list[Path], condition_key: str, display_name: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for metrics_path in sorted(paths):
        payload = json.loads(metrics_path.read_text(encoding="utf-8"))
        row: dict[str, object] = {
            "condition_key": condition_key,
            "display_name": display_name,
            "path": str(metrics_path),
            "seed": parse_seed(metrics_path),
        }
        for metric_name, metric_path in METRICS.items():
            try:
                row[metric_name] = nested_get(payload, metric_path)
            except KeyError:
                row[metric_name] = 0.0
        rows.append(row)
    return rows


def summarize_condition(condition_key: str, display_name: str, rows: list[dict[str, object]]) -> dict[str, object]:
    metric_summary: dict[str, dict[str, float]] = {}
    for metric_name in METRICS:
        values = [float(row[metric_name]) for row in rows]
        metric_summary[metric_name] = {
            "mean": mean(values),
            "std": sample_std(values),
            "ci95_t": ci95_t(values),
        }
    return {
        "condition_key": condition_key,
        "display_name": display_name,
        "n": len(rows),
        "seeds": [row["seed"] for row in rows],
        "metrics": metric_summary,
    }


def build_paired_summary(
    reference_key: str,
    reference_display: str,
    reference_rows: list[dict[str, object]],
    target_key: str,
    target_display: str,
    target_rows: list[dict[str, object]],
) -> dict[str, object] | None:
    ref_by_seed = {int(row["seed"]): row for row in reference_rows if row["seed"] is not None}
    tgt_by_seed = {int(row["seed"]): row for row in target_rows if row["seed"] is not None}
    shared_seeds = sorted(set(ref_by_seed) & set(tgt_by_seed))
    if not shared_seeds:
        return None

    metric_summaries: dict[str, dict[str, float]] = {}
    for metric_name in PAIRWISE_METRICS:
        diffs = [
            float(tgt_by_seed[seed][metric_name]) - float(ref_by_seed[seed][metric_name])
            for seed in shared_seeds
        ]
        metric_summaries[metric_name] = {
            "delta_mean": mean(diffs),
            "delta_std": sample_std(diffs),
            "delta_ci95_t": ci95_t(diffs),
            "cohen_dz": cohen_dz(diffs),
        }

    return {
        "reference_key": reference_key,
        "reference_display": reference_display,
        "target_key": target_key,
        "target_display": target_display,
        "shared_n": len(shared_seeds),
        "shared_seeds": shared_seeds,
        "metrics": metric_summaries,
    }


def write_summary_csv(output_path: Path, summaries: list[dict[str, object]]) -> None:
    fieldnames = ["condition_key", "display_name", "n", "seeds"]
    for metric_name in METRICS:
        fieldnames.extend(
            [
                f"{metric_name}_mean",
                f"{metric_name}_std",
                f"{metric_name}_ci95_t",
            ]
        )

    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for summary in summaries:
            row = {
                "condition_key": summary["condition_key"],
                "display_name": summary["display_name"],
                "n": summary["n"],
                "seeds": " ".join(str(seed) for seed in summary["seeds"]),
            }
            for metric_name in METRICS:
                metric_summary = summary["metrics"][metric_name]
                row[f"{metric_name}_mean"] = f"{metric_summary['mean']:.4f}"
                row[f"{metric_name}_std"] = f"{metric_summary['std']:.4f}"
                row[f"{metric_name}_ci95_t"] = f"{metric_summary['ci95_t']:.4f}"
            writer.writerow(row)


def write_raw_seed_csv(output_path: Path, rows_by_condition: dict[str, list[dict[str, object]]]) -> None:
    fieldnames = ["condition_key", "display_name", "seed", *METRICS.keys()]
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for condition_rows in rows_by_condition.values():
            for row in condition_rows:
                out = {
                    "condition_key": row["condition_key"],
                    "display_name": row["display_name"],
                    "seed": row["seed"],
                }
                for metric_name in METRICS:
                    out[metric_name] = f"{float(row[metric_name]):.4f}"
                writer.writerow(out)


def write_paired_csv(output_path: Path, paired_summaries: list[dict[str, object]]) -> None:
    fieldnames = [
        "reference_key",
        "target_key",
        "metric",
        "shared_n",
        "shared_seeds",
        "delta_mean",
        "delta_std",
        "delta_ci95_t",
        "cohen_dz",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for summary in paired_summaries:
            for metric_name, metric_summary in summary["metrics"].items():
                writer.writerow(
                    {
                        "reference_key": summary["reference_key"],
                        "target_key": summary["target_key"],
                        "metric": metric_name,
                        "shared_n": summary["shared_n"],
                        "shared_seeds": " ".join(str(seed) for seed in summary["shared_seeds"]),
                        "delta_mean": f"{metric_summary['delta_mean']:.4f}",
                        "delta_std": f"{metric_summary['delta_std']:.4f}",
                        "delta_ci95_t": f"{metric_summary['delta_ci95_t']:.4f}",
                        "cohen_dz": f"{metric_summary['cohen_dz']:.4f}",
                    }
                )


def build_markdown(
    label: str,
    summaries: list[dict[str, object]],
    paired_summaries: list[dict[str, object]],
) -> str:
    lines = [
        f"# {label}",
        "",
        "## Condition Summary",
        "| Condition | n | Seeds | IR % | RR % | Agree % | Disagree % | Peak Infection | Peak Resistance |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for summary in summaries:
        metrics = summary["metrics"]
        lines.append(
            "| "
            + " | ".join(
                [
                    str(summary["display_name"]),
                    str(summary["n"]),
                    ", ".join(str(seed) for seed in summary["seeds"]),
                    format_stat(metrics["infection_rate_pct"]),
                    format_stat(metrics["resistance_rate_pct"]),
                    format_stat(metrics["agree_comment_pct"]),
                    format_stat(metrics["disagree_comment_pct"]),
                    format_stat(metrics["peak_infection_proxy_value"]),
                    format_stat(metrics["peak_resistance_value"]),
                ]
            )
            + " |"
        )

    if paired_summaries:
        lines.extend(
            [
                "",
                "## Paired Deltas",
                "| Comparison | n | IR Δ | RR Δ |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for summary in paired_summaries:
            ir = summary["metrics"]["infection_rate_pct"]
            rr = summary["metrics"]["resistance_rate_pct"]
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"{summary['target_display']} vs {summary['reference_display']}",
                        str(summary["shared_n"]),
                        (
                            f"{ir['delta_mean']:+.2f} ± {ir['delta_std']:.2f} "
                            f"(t-CI ± {ir['delta_ci95_t']:.2f}; dz={ir['cohen_dz']:+.2f})"
                        ),
                        (
                            f"{rr['delta_mean']:+.2f} ± {rr['delta_std']:.2f} "
                            f"(t-CI ± {rr['delta_ci95_t']:.2f}; dz={rr['cohen_dz']:+.2f})"
                        ),
                    ]
                )
                + " |"
            )

    lines.extend(
        [
            "",
            "## Notes",
            "- Summary cells report mean ± sample std with Student-t 95% confidence interval half-widths.",
            "- Paired deltas reuse the shared seed set between each comparison pair and report Cohen's dz over seed-level differences.",
            "- `post coverage` means the share of bad-actor posts that receive the reactive debunking intervention once the trigger timestep is reached.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    metrics_dir = Path(args.metrics_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows_by_condition: dict[str, list[dict[str, object]]] = {}
    display_names: dict[str, str] = {}
    case_keys: list[str] = []

    case_specs = [spec for spec in args.case_specs.split() if spec]
    for spec in case_specs:
        case_key, _, _ = spec.split(":")
        case_keys.append(case_key)
        display_name = case_key_to_display(case_key)
        display_names[case_key] = display_name
        pattern = f"main_500_debunking_fairness_{case_key}_seed_*_metrics.json"
        rows_by_condition[case_key] = load_rows_from_paths(
            list(metrics_dir.glob(pattern)),
            condition_key=case_key,
            display_name=display_name,
        )

    if args.main_metrics_dir:
        main_metrics_dir = Path(args.main_metrics_dir)
        if main_metrics_dir.exists():
            for condition_key, display_name, pattern in MAIN_RUN_PATTERNS:
                display_names[condition_key] = display_name
                rows_by_condition[condition_key] = load_rows_from_paths(
                    list(main_metrics_dir.glob(pattern)),
                    condition_key=condition_key,
                    display_name=display_name,
                )

    ordered_keys = [key for key, _, _ in MAIN_RUN_PATTERNS if key in rows_by_condition]
    ordered_keys.extend(key for key in case_keys if key in rows_by_condition)

    summaries = [
        summarize_condition(key, display_names[key], rows_by_condition[key])
        for key in ordered_keys
        if rows_by_condition.get(key)
    ]

    paired_summaries: list[dict[str, object]] = []
    baseline_key = "main_debunking_t5_postcov50"
    prebunking_key = "prebunking_full"
    for case_key in case_keys:
        case_rows = rows_by_condition.get(case_key, [])
        if not case_rows:
            continue
        if rows_by_condition.get(baseline_key):
            paired = build_paired_summary(
                baseline_key,
                display_names[baseline_key],
                rows_by_condition[baseline_key],
                case_key,
                display_names[case_key],
                case_rows,
            )
            if paired is not None:
                paired_summaries.append(paired)
        if rows_by_condition.get(prebunking_key):
            paired = build_paired_summary(
                prebunking_key,
                display_names[prebunking_key],
                rows_by_condition[prebunking_key],
                case_key,
                display_names[case_key],
                case_rows,
            )
            if paired is not None:
                paired_summaries.append(paired)

    payload = {
        "label": args.label,
        "summaries": summaries,
        "paired_deltas": paired_summaries,
    }
    (output_dir / f"{args.label}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_summary_csv(output_dir / f"{args.label}.csv", summaries)
    write_raw_seed_csv(output_dir / f"{args.label}_raw_seeds.csv", rows_by_condition)
    write_paired_csv(output_dir / f"{args.label}_paired_deltas.csv", paired_summaries)
    (output_dir / f"{args.label}.md").write_text(
        build_markdown(args.label, summaries, paired_summaries),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
