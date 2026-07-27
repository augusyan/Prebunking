#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


MAIN_RUN_PATTERNS = (
    ("no_defense", "No Defense", "main_500_seed_*_no_defense_metrics.json"),
    ("debunking", "Debunking", "main_500_seed_*_debunking_metrics.json"),
    ("prebunking", "Prebunking", "main_500_seed_*_prebunking_metrics.json"),
)

FAIRNESS_RAW_KEY = "main_debunking_t5_postcov50"
FAIRNESS_CASE_LABELS = {
    "main_debunking_t5_postcov50": "Debunking t=5 50% post coverage",
    "strengthened_debunking_t3_postcov100": "Debunking t=3 100% post coverage",
    "prebunking_full": "Prebunking Full Coverage",
    "no_defense": "No Defense",
}

METRICS = {
    "infection_rate_pct": ("macro", "infection_rate_pct"),
    "resistance_rate_pct": ("macro", "resistance_rate_pct"),
}

PAIR_SPECS = (
    ("no_defense", "debunking"),
    ("no_defense", "prebunking"),
    ("debunking", "prebunking"),
    ("main_debunking_t5_postcov50", "strengthened_debunking_t3_postcov100"),
    ("strengthened_debunking_t3_postcov100", "prebunking"),
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
    13: 2.16,
    14: 2.145,
    15: 2.131,
    16: 2.12,
    17: 2.11,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.08,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.06,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build stronger t/bootstrap/permutation summaries for macro multiseed results."
    )
    parser.add_argument(
        "--main-metrics-dir",
        default="artifacts/experiment/paper_runs/main_500_multiseed/metrics",
        help="Directory with main multiseed *_metrics.json files.",
    )
    parser.add_argument(
        "--fairness-raw-seeds",
        default="artifacts/experiment/paper_runs/debunking_fairness_multiseed/summary/debunking_fairness_multiseed_raw_seeds.csv",
        help="CSV with fairness raw seeds.",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/experiment/paper_runs/multiseed_inference_bundle",
        help="Output directory for stronger statistical summaries.",
    )
    parser.add_argument(
        "--bootstrap-reps",
        type=int,
        default=10000,
        help="Bootstrap repetitions for percentile intervals.",
    )
    parser.add_argument(
        "--bootstrap-seed",
        type=int,
        default=20260503,
        help="Deterministic bootstrap seed.",
    )
    return parser.parse_args()


def nested_get(obj: dict[str, Any], path: tuple[str, ...]) -> float:
    current: Any = obj
    for key in path:
        current = current[key]
    return float(current)


def parse_seed(path_or_text: str) -> int | None:
    match = re.search(r"seed_(\d+)", path_or_text)
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
    critical = T_CRITICAL_95.get(len(values) - 1, 1.96)
    return critical * sample_std(values) / math.sqrt(len(values))


def percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    index = (len(sorted_values) - 1) * q
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return sorted_values[lower]
    weight = index - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def bootstrap_mean_ci(
    values: list[float],
    reps: int,
    rng: random.Random,
) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    if len(values) == 1:
        return values[0], values[0]
    means = []
    for _ in range(reps):
        sample = [values[rng.randrange(len(values))] for _ in range(len(values))]
        means.append(mean(sample))
    means.sort()
    return percentile(means, 0.025), percentile(means, 0.975)


def exact_signflip_pvalue(diffs: list[float]) -> float:
    if not diffs:
        return 1.0
    observed = abs(mean(diffs))
    count = 0
    extreme = 0
    for signs in itertools.product((-1.0, 1.0), repeat=len(diffs)):
        flipped = [sign * diff for sign, diff in zip(signs, diffs)]
        count += 1
        if abs(mean(flipped)) >= observed - 1e-12:
            extreme += 1
    return extreme / count if count else 1.0


def cohen_dz(diffs: list[float]) -> float:
    std = sample_std(diffs)
    if len(diffs) <= 1 or std == 0.0:
        return 0.0
    return mean(diffs) / std


def load_main_rows(metrics_dir: Path) -> dict[str, list[dict[str, Any]]]:
    rows_by_condition: dict[str, list[dict[str, Any]]] = {}
    for condition_key, display_name, pattern in MAIN_RUN_PATTERNS:
        rows: list[dict[str, Any]] = []
        for metrics_path in sorted(metrics_dir.glob(pattern)):
            payload = json.loads(metrics_path.read_text(encoding="utf-8"))
            row: dict[str, Any] = {
                "condition_key": condition_key,
                "display_name": display_name,
                "seed": parse_seed(metrics_path.name),
            }
            for metric_name, metric_path in METRICS.items():
                row[metric_name] = nested_get(payload, metric_path)
            rows.append(row)
        rows_by_condition[condition_key] = rows
    return rows_by_condition


def load_fairness_rows(raw_seed_csv: Path) -> dict[str, list[dict[str, Any]]]:
    rows_by_condition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if not raw_seed_csv.exists():
        return rows_by_condition
    with raw_seed_csv.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            condition_key = row["condition_key"]
            rows_by_condition[condition_key].append(
                {
                    "condition_key": condition_key,
                    "display_name": row["display_name"],
                    "seed": int(row["seed"]),
                    "infection_rate_pct": float(row["infection_rate_pct"]),
                    "resistance_rate_pct": float(row["resistance_rate_pct"]),
                }
            )
    return rows_by_condition


def summarize_condition(
    condition_key: str,
    display_name: str,
    rows: list[dict[str, Any]],
    reps: int,
    rng: random.Random,
) -> dict[str, Any]:
    summary_metrics: dict[str, dict[str, float]] = {}
    for metric_name in METRICS:
        values = [float(row[metric_name]) for row in rows]
        bootstrap_low, bootstrap_high = bootstrap_mean_ci(values, reps, rng)
        summary_metrics[metric_name] = {
            "mean": mean(values),
            "std": sample_std(values),
            "ci95_t": ci95_t(values),
            "bootstrap_low": bootstrap_low,
            "bootstrap_high": bootstrap_high,
        }
    return {
        "condition_key": condition_key,
        "display_name": display_name,
        "n": len(rows),
        "seeds": [int(row["seed"]) for row in rows],
        "metrics": summary_metrics,
    }


def paired_delta_summary(
    reference_key: str,
    target_key: str,
    rows_by_condition: dict[str, list[dict[str, Any]]],
    reps: int,
    rng: random.Random,
) -> dict[str, Any] | None:
    ref_rows = rows_by_condition.get(reference_key, [])
    tgt_rows = rows_by_condition.get(target_key, [])
    if not ref_rows or not tgt_rows:
        return None

    ref_by_seed = {int(row["seed"]): row for row in ref_rows}
    tgt_by_seed = {int(row["seed"]): row for row in tgt_rows}
    shared_seeds = sorted(set(ref_by_seed) & set(tgt_by_seed))
    if not shared_seeds:
        return None

    metric_payload: dict[str, dict[str, float]] = {}
    for metric_name in METRICS:
        diffs = [
            float(tgt_by_seed[seed][metric_name]) - float(ref_by_seed[seed][metric_name])
            for seed in shared_seeds
        ]
        bootstrap_low, bootstrap_high = bootstrap_mean_ci(diffs, reps, rng)
        metric_payload[metric_name] = {
            "delta_mean": mean(diffs),
            "delta_std": sample_std(diffs),
            "delta_ci95_t": ci95_t(diffs),
            "bootstrap_low": bootstrap_low,
            "bootstrap_high": bootstrap_high,
            "cohen_dz": cohen_dz(diffs),
            "signflip_p": exact_signflip_pvalue(diffs),
        }

    return {
        "reference_key": reference_key,
        "reference_display": rows_by_condition[reference_key][0]["display_name"],
        "target_key": target_key,
        "target_display": rows_by_condition[target_key][0]["display_name"],
        "shared_n": len(shared_seeds),
        "shared_seeds": shared_seeds,
        "metrics": metric_payload,
    }


def write_summary_csv(output_path: Path, summaries: list[dict[str, Any]]) -> None:
    fieldnames = ["condition_key", "display_name", "n", "seeds"]
    for metric_name in METRICS:
        fieldnames.extend(
            [
                f"{metric_name}_mean",
                f"{metric_name}_std",
                f"{metric_name}_ci95_t",
                f"{metric_name}_bootstrap_low",
                f"{metric_name}_bootstrap_high",
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
                row[f"{metric_name}_bootstrap_low"] = f"{metric_summary['bootstrap_low']:.4f}"
                row[f"{metric_name}_bootstrap_high"] = f"{metric_summary['bootstrap_high']:.4f}"
            writer.writerow(row)


def write_raw_seed_csv(output_path: Path, rows_by_condition: dict[str, list[dict[str, Any]]]) -> None:
    fieldnames = ["condition_key", "display_name", "seed", *METRICS.keys()]
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for rows in rows_by_condition.values():
            for row in rows:
                writer.writerow(
                    {
                        "condition_key": row["condition_key"],
                        "display_name": row["display_name"],
                        "seed": row["seed"],
                        "infection_rate_pct": f"{float(row['infection_rate_pct']):.4f}",
                        "resistance_rate_pct": f"{float(row['resistance_rate_pct']):.4f}",
                    }
                )


def write_paired_csv(output_path: Path, paired: list[dict[str, Any]]) -> None:
    fieldnames = [
        "reference_key",
        "target_key",
        "metric",
        "shared_n",
        "shared_seeds",
        "delta_mean",
        "delta_std",
        "delta_ci95_t",
        "bootstrap_low",
        "bootstrap_high",
        "cohen_dz",
        "signflip_p",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for summary in paired:
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
                        "bootstrap_low": f"{metric_summary['bootstrap_low']:.4f}",
                        "bootstrap_high": f"{metric_summary['bootstrap_high']:.4f}",
                        "cohen_dz": f"{metric_summary['cohen_dz']:.4f}",
                        "signflip_p": f"{metric_summary['signflip_p']:.6f}",
                    }
                )


def build_markdown(
    summaries: list[dict[str, Any]],
    paired_summaries: list[dict[str, Any]],
) -> str:
    lines = [
        "# multiseed_inference_bundle",
        "",
        "## Condition Summary",
        "| Condition | n | Seeds | IR mean | IR t-CI | IR bootstrap 95% | RR mean | RR t-CI | RR bootstrap 95% |",
        "| --- | ---: | --- | ---: | ---: | --- | ---: | ---: | --- |",
    ]
    for summary in summaries:
        ir = summary["metrics"]["infection_rate_pct"]
        rr = summary["metrics"]["resistance_rate_pct"]
        lines.append(
            "| "
            + " | ".join(
                [
                    summary["display_name"],
                    str(summary["n"]),
                    ", ".join(str(seed) for seed in summary["seeds"]),
                    f"{ir['mean']:.2f}",
                    f"± {ir['ci95_t']:.2f}",
                    f"[{ir['bootstrap_low']:.2f}, {ir['bootstrap_high']:.2f}]",
                    f"{rr['mean']:.2f}",
                    f"± {rr['ci95_t']:.2f}",
                    f"[{rr['bootstrap_low']:.2f}, {rr['bootstrap_high']:.2f}]",
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Paired Deltas",
            "| Comparison | n | Metric | Delta mean | t-CI | Bootstrap 95% | Cohen dz | Exact sign-flip p |",
            "| --- | ---: | --- | ---: | ---: | --- | ---: | ---: |",
        ]
    )
    for summary in paired_summaries:
        for metric_name, metric_summary in summary["metrics"].items():
            metric_label = "IR" if metric_name == "infection_rate_pct" else "RR"
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"{summary['target_display']} vs {summary['reference_display']}",
                        str(summary["shared_n"]),
                        metric_label,
                        f"{metric_summary['delta_mean']:+.2f}",
                        f"± {metric_summary['delta_ci95_t']:.2f}",
                        f"[{metric_summary['bootstrap_low']:.2f}, {metric_summary['bootstrap_high']:.2f}]",
                        f"{metric_summary['cohen_dz']:+.2f}",
                        f"{metric_summary['signflip_p']:.4f}",
                    ]
                )
                + " |"
            )

    lines.extend(
        [
            "",
            "## Notes",
            "- Condition summaries replace the old normal-approximation CI with Student-t intervals and bootstrap percentile intervals.",
            "- Paired comparisons are computed on the shared seed set and include Cohen's dz plus exact two-sided sign-flip p-values.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    rng = random.Random(args.bootstrap_seed)

    main_rows = load_main_rows(Path(args.main_metrics_dir))
    fairness_rows = load_fairness_rows(Path(args.fairness_raw_seeds))
    combined_rows = {**main_rows}
    for key, rows in fairness_rows.items():
        combined_rows[key] = rows

    summaries = []
    for condition_key in (
        "no_defense",
        "debunking",
        "prebunking",
        FAIRNESS_RAW_KEY,
        "strengthened_debunking_t3_postcov100",
    ):
        rows = combined_rows.get(condition_key, [])
        if not rows:
            continue
        display_name = rows[0]["display_name"]
        summaries.append(
            summarize_condition(
                condition_key=condition_key,
                display_name=display_name,
                rows=rows,
                reps=args.bootstrap_reps,
                rng=rng,
            )
        )

    paired_summaries = []
    for reference_key, target_key in PAIR_SPECS:
        paired = paired_delta_summary(
            reference_key=reference_key,
            target_key=target_key,
            rows_by_condition=combined_rows,
            reps=args.bootstrap_reps,
            rng=rng,
        )
        if paired is not None:
            paired_summaries.append(paired)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_csv = output_dir / "macro_condition_summary.csv"
    raw_seed_csv = output_dir / "macro_raw_seeds.csv"
    paired_csv = output_dir / "macro_paired_deltas.csv"
    summary_json = output_dir / "macro_inference_summary.json"
    summary_md = output_dir / "macro_inference_summary.md"

    write_summary_csv(summary_csv, summaries)
    write_raw_seed_csv(raw_seed_csv, combined_rows)
    write_paired_csv(paired_csv, paired_summaries)
    summary_json.write_text(
        json.dumps(
            {
                "summaries": summaries,
                "paired_deltas": paired_summaries,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    summary_md.write_text(build_markdown(summaries, paired_summaries), encoding="utf-8")

    print(
        json.dumps(
            {
                "summary_csv": str(summary_csv),
                "raw_seed_csv": str(raw_seed_csv),
                "paired_csv": str(paired_csv),
                "summary_json": str(summary_json),
                "summary_md": str(summary_md),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
