#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path


MAIN_METRICS = {
    "infection_rate_pct": ("macro", "infection_rate_pct"),
    "resistance_rate_pct": ("macro", "resistance_rate_pct"),
    "agree_comment_pct": ("micro", "stance_comment_pct", "agree_true"),
    "disagree_comment_pct": ("micro", "stance_comment_pct", "agree_false"),
    "skepticism_pct": ("micro", "representative_emotions", "skepticism", "pct"),
    "vigilance_pct": ("micro", "representative_emotions", "vigilance", "pct"),
    "anger_pct": ("micro", "representative_emotions", "anger", "pct"),
    "peak_infection_proxy_value": ("time_series", "peak_infection_proxy_value"),
    "peak_resistance_value": ("time_series", "peak_resistance_value"),
}

MESO_METRICS = (
    "mean_disagree_share_engaged_pct",
    "median_first_disagree_step",
    "unique_benign_disagree_users",
)

VARIANT_LABELS = {
    "generic": "Generic",
    "counter": "Counter-Speech",
}

MESO_DISPLAY_LABELS = {
    "mean_disagree_share_engaged_pct": "Mean Disagree Share",
    "median_first_disagree_step": "First Disagree Step",
    "unique_benign_disagree_users": "Unique Counter-Speakers",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate multi-seed prebunking-variant metrics into mean/std/95% CI tables."
    )
    parser.add_argument("--metrics-dir", required=True)
    parser.add_argument("--meso-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--label",
        default="main_500_prebunking_variant_multiseed",
        help="Output label prefix.",
    )
    parser.add_argument(
        "--variants",
        nargs="+",
        default=["generic", "counter"],
        help="Ordered variant list to aggregate.",
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


def safe_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


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


def format_stat(stat: dict[str, float]) -> str:
    return f"{stat['mean']:.2f} ± {stat['std']:.2f} (CI ± {stat['ci95']:.2f})"


def latex_stat(stat: dict[str, float], decimals: int = 2) -> str:
    return (
        f"{stat['mean']:.{decimals}f} $\\pm$ {stat['std']:.{decimals}f} "
        f"(CI $\\pm$ {stat['ci95']:.{decimals}f})"
    )


def variant_label(variant: str) -> str:
    return VARIANT_LABELS.get(variant, variant.replace("_", " ").title())


def load_variant_rows(metrics_dir: Path, meso_dir: Path, variant: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for metrics_path in sorted(metrics_dir.glob(f"*variant_{variant}_seed_*_metrics.json")):
        payload = json.loads(metrics_path.read_text(encoding="utf-8"))
        stem = metrics_path.stem.removesuffix("_metrics")
        meso_path = meso_dir / f"{stem}_meso_summary.json"
        meso_payload = json.loads(meso_path.read_text(encoding="utf-8"))
        summary = meso_payload["condition"]
        row = {
            "path": str(metrics_path),
            "seed": parse_seed(metrics_path),
        }
        for metric_name, metric_path in MAIN_METRICS.items():
            try:
                row[metric_name] = nested_get(payload, metric_path)
            except KeyError:
                row[metric_name] = 0.0
        for metric_name in MESO_METRICS:
            row[metric_name] = safe_float(summary[metric_name])
        rows.append(row)
    return rows


def summarize(rows: list[dict[str, object]]) -> dict[str, dict[str, float]]:
    summary: dict[str, dict[str, float]] = {}
    for metric_name in [*MAIN_METRICS.keys(), *MESO_METRICS]:
        values = []
        for row in rows:
            value = row[metric_name]
            if value is None:
                continue
            numeric = float(value)
            if math.isnan(numeric):
                continue
            values.append(numeric)
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
    metric_names = [*MAIN_METRICS.keys(), *MESO_METRICS]
    fieldnames = ["variant", "n"]
    for metric_name in metric_names:
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
            row = {"variant": summary["variant"], "n": summary["n"]}
            metric_summary = summary["metrics"]
            for metric_name in metric_names:
                mean_value = metric_summary[metric_name]["mean"]
                std_value = metric_summary[metric_name]["std"]
                ci95_value = metric_summary[metric_name]["ci95"]
                row[f"{metric_name}_mean"] = (
                    "" if mean_value is None else f"{mean_value:.4f}"
                )
                row[f"{metric_name}_std"] = (
                    "" if std_value is None else f"{std_value:.4f}"
                )
                row[f"{metric_name}_ci95"] = (
                    "" if ci95_value is None else f"{ci95_value:.4f}"
                )
                row[f"{metric_name}_n_valid"] = metric_summary[metric_name]["n_valid"]
            writer.writerow(row)


def build_markdown(label: str, summaries: list[dict[str, object]]) -> str:
    headers = [
        "Variant",
        "n",
        "IR %",
        "RR %",
        "Disagree %",
        "Vigilance %",
        "Anger %",
        "Mean Disagree Share",
        "Median First Disagree Step",
        "Unique Counter-Speakers",
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
                    str(summary["variant"]),
                    str(summary["n"]),
                    format_stat(metrics["infection_rate_pct"]),
                    format_stat(metrics["resistance_rate_pct"]),
                    format_stat(metrics["disagree_comment_pct"]),
                    format_stat(metrics["vigilance_pct"]),
                    format_stat(metrics["anger_pct"]),
                    format_stat(metrics["mean_disagree_share_engaged_pct"]),
                    format_stat(metrics["median_first_disagree_step"]),
                    format_stat(metrics["unique_benign_disagree_users"]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Notes",
            "- Each cell reports mean ± sample std with a normal-approximation 95% confidence interval half-width.",
            "- Meso-level metrics come from per-run bad-post interaction summaries generated by export_condition_meso_metrics.py.",
        ]
    )
    lines.extend(
        f"- {note}" for note in build_missing_meso_notes(summaries)
    )
    return "\n".join(lines) + "\n"


def build_missing_meso_notes(summaries: list[dict[str, object]]) -> list[str]:
    notes: list[str] = []
    tracked_metrics = (
        "mean_disagree_share_engaged_pct",
        "median_first_disagree_step",
    )
    for summary in summaries:
        total_n = int(summary["n"])
        metric_summary = summary["metrics"]
        impacted = [
            MESO_DISPLAY_LABELS[metric_name]
            for metric_name in tracked_metrics
            if metric_summary[metric_name]["n_valid"] < total_n
        ]
        if not impacted:
            continue
        valid_n = min(metric_summary[metric_name]["n_valid"] for metric_name in tracked_metrics)
        missing_n = total_n - valid_n
        notes.append(
            f"{variant_label(str(summary['variant']))}: "
            f"{', '.join(impacted)} average over {valid_n}/{total_n} seeds because "
            f"{missing_n}/{total_n} seeds had zero engaged bad posts, leaving those meso metrics undefined."
        )
    return notes


def build_latex_table(
    caption: str,
    label: str,
    headers: list[str],
    rows: list[list[str]],
    note_lines: list[str],
) -> str:
    column_spec = "l" + ("c" * (len(headers) - 1))
    header_row = " & ".join(headers) + r" \\"
    body_rows = [" & ".join(row) + r" \\" for row in rows]

    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\small",
        rf"\caption{{{caption}}}",
        rf"\label{{{label}}}",
        r"\begin{threeparttable}",
        rf"\begin{{tabular}}{{{column_spec}}}",
        r"\toprule",
        header_row,
        r"\midrule",
        *body_rows,
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}[flushleft]",
        r"\footnotesize",
    ]
    lines.extend(rf"\item {note}" for note in note_lines)
    lines.extend(
        [
            r"\end{tablenotes}",
            r"\end{threeparttable}",
            r"\end{table*}",
            "",
        ]
    )
    return "\n".join(lines)


def build_variant_macro_latex_table(summaries: list[dict[str, object]]) -> str:
    rows: list[list[str]] = []
    for summary in summaries:
        metrics = summary["metrics"]
        rows.append(
            [
                variant_label(str(summary["variant"])),
                str(summary["n"]),
                latex_stat(metrics["infection_rate_pct"]),
                latex_stat(metrics["resistance_rate_pct"]),
                latex_stat(metrics["peak_infection_proxy_value"], decimals=1),
                latex_stat(metrics["peak_resistance_value"], decimals=1),
            ]
        )
    return build_latex_table(
        caption="Multi-seed comparison of prebunking message variants in the 500-agent setting.",
        label="tab:prebunking_variant_macro_results",
        headers=[
            "Variant",
            "$n$",
            "IR $\\downarrow$",
            "RR $\\uparrow$",
            "Peak Infection $\\downarrow$",
            "Peak Resistance $\\uparrow$",
        ],
        rows=rows,
        note_lines=[
            "Each cell reports mean $\\pm$ sample std with the 95\\% confidence-interval half-width shown in parentheses.",
            "All rows use the same prebunking-only protocol and differ only in the intervention wording variant.",
        ],
    )


def build_variant_meso_latex_table(summaries: list[dict[str, object]]) -> str:
    rows: list[list[str]] = []
    for summary in summaries:
        metrics = summary["metrics"]
        rows.append(
            [
                variant_label(str(summary["variant"])),
                str(summary["n"]),
                latex_stat(metrics["disagree_comment_pct"]),
                latex_stat(metrics["mean_disagree_share_engaged_pct"]),
                latex_stat(metrics["median_first_disagree_step"]),
                latex_stat(metrics["unique_benign_disagree_users"], decimals=1),
            ]
        )
    return build_latex_table(
        caption="Multi-seed public counter-speech signals across prebunking message variants.",
        label="tab:prebunking_variant_meso_results",
        headers=[
            "Variant",
            "$n$",
            "Disagree $\\uparrow$",
            "Mean Disagree Share $\\uparrow$",
            "First Disagree Step $\\downarrow$",
            "Unique Counter-Speakers $\\uparrow$",
        ],
        rows=rows,
        note_lines=[
            "Each cell reports mean $\\pm$ sample std with the 95\\% confidence-interval half-width shown in parentheses.",
            "Meso-level statistics are computed from per-run bad-post interaction summaries.",
            *build_missing_meso_notes(summaries),
        ],
    )


def main() -> None:
    args = parse_args()
    metrics_dir = Path(args.metrics_dir).resolve()
    meso_dir = Path(args.meso_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    summaries: list[dict[str, object]] = []
    for variant in args.variants:
        rows = load_variant_rows(metrics_dir, meso_dir, variant)
        if not rows:
            raise FileNotFoundError(
                f"No *_metrics.json files found for variant '{variant}' in {metrics_dir}"
            )
        summaries.append(
            {
                "variant": variant,
                "n": len(rows),
                "seeds": [row["seed"] for row in rows],
                "runs": [row["path"] for row in rows],
                "metrics": summarize(rows),
            }
        )

    json_path = output_dir / f"{args.label}_summary.json"
    csv_path = output_dir / f"{args.label}_summary.csv"
    md_path = output_dir / f"{args.label}_summary.md"
    macro_tex_path = output_dir / f"{args.label}_macro_table.tex"
    meso_tex_path = output_dir / f"{args.label}_meso_table.tex"

    json_path.write_text(
        json.dumps({"label": args.label, "variants": summaries}, indent=2),
        encoding="utf-8",
    )
    write_csv(csv_path, summaries)
    md_path.write_text(build_markdown(args.label, summaries), encoding="utf-8")
    macro_tex_path.write_text(build_variant_macro_latex_table(summaries), encoding="utf-8")
    meso_tex_path.write_text(build_variant_meso_latex_table(summaries), encoding="utf-8")

    print(
        json.dumps(
            {
                "json": str(json_path),
                "csv": str(csv_path),
                "markdown": str(md_path),
                "macro_tex": str(macro_tex_path),
                "meso_tex": str(meso_tex_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
