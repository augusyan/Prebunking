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
    "skepticism_pct": ("micro", "representative_emotions", "skepticism", "pct"),
    "vigilance_pct": ("micro", "representative_emotions", "vigilance", "pct"),
    "anger_pct": ("micro", "representative_emotions", "anger", "pct"),
    "peak_infection_proxy_value": ("time_series", "peak_infection_proxy_value"),
    "peak_resistance_value": ("time_series", "peak_resistance_value"),
}

CONDITION_LABELS = {
    "no_defense": "No Defense",
    "debunking": "Debunking",
    "prebunking": "Prebunking",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate multi-seed main_500 metrics into mean/std/95% CI tables."
    )
    parser.add_argument("--metrics-dir", required=True, help="Directory with *_metrics.json files.")
    parser.add_argument("--output-dir", required=True, help="Directory for summary outputs.")
    parser.add_argument("--label", default="main_500_multiseed", help="Output label prefix.")
    parser.add_argument(
        "--conditions",
        nargs="+",
        default=["no_defense", "debunking", "prebunking"],
        help="Ordered condition list to aggregate.",
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


def condition_label(condition: str) -> str:
    return CONDITION_LABELS.get(condition, condition.replace("_", " ").title())


def load_condition_rows(metrics_dir: Path, condition: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for metrics_path in sorted(metrics_dir.glob(f"*_{condition}_metrics.json")):
        payload = json.loads(metrics_path.read_text(encoding="utf-8"))
        row = {
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


def write_csv(output_path: Path, summaries: list[dict[str, object]]) -> None:
    fieldnames = ["condition", "n"]
    for metric_name in METRICS:
        fieldnames.extend(
            [
                f"{metric_name}_mean",
                f"{metric_name}_std",
                f"{metric_name}_ci95",
            ]
        )

    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for summary in summaries:
            row = {"condition": summary["condition"], "n": summary["n"]}
            metric_summary = summary["metrics"]
            for metric_name in METRICS:
                row[f"{metric_name}_mean"] = f"{metric_summary[metric_name]['mean']:.4f}"
                row[f"{metric_name}_std"] = f"{metric_summary[metric_name]['std']:.4f}"
                row[f"{metric_name}_ci95"] = f"{metric_summary[metric_name]['ci95']:.4f}"
            writer.writerow(row)


def build_markdown(label: str, summaries: list[dict[str, object]]) -> str:
    headers = [
        "Condition",
        "n",
        "IR %",
        "RR %",
        "Agree %",
        "Disagree %",
        "Skepticism %",
        "Vigilance %",
        "Anger %",
        "Peak Infection",
        "Peak Resistance",
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
                    str(summary["condition"]),
                    str(summary["n"]),
                    format_stat(metrics["infection_rate_pct"]),
                    format_stat(metrics["resistance_rate_pct"]),
                    format_stat(metrics["agree_comment_pct"]),
                    format_stat(metrics["disagree_comment_pct"]),
                    format_stat(metrics["skepticism_pct"]),
                    format_stat(metrics["vigilance_pct"]),
                    format_stat(metrics["anger_pct"]),
                    format_stat(metrics["peak_infection_proxy_value"]),
                    format_stat(metrics["peak_resistance_value"]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Notes",
            "- Each cell reports mean ± sample std with a normal-approximation 95% confidence interval half-width.",
            "- IR/RR reuse the run-level behavioral proxy definitions from the paper-facing analysis scripts.",
        ]
    )
    return "\n".join(lines) + "\n"


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


def build_macro_latex_table(summaries: list[dict[str, object]]) -> str:
    rows: list[list[str]] = []
    for summary in summaries:
        metrics = summary["metrics"]
        rows.append(
            [
                condition_label(str(summary["condition"])),
                str(summary["n"]),
                latex_stat(metrics["infection_rate_pct"]),
                latex_stat(metrics["resistance_rate_pct"]),
                latex_stat(metrics["peak_infection_proxy_value"], decimals=1),
                latex_stat(metrics["peak_resistance_value"], decimals=1),
            ]
        )
    return build_latex_table(
        caption="Multi-seed macro-level propagation outcomes in the 500-agent main comparison.",
        label="tab:main_multiseed_macro_results",
        headers=[
            "Condition",
            "$n$",
            "IR $\\downarrow$",
            "RR $\\uparrow$",
            "Peak Infection $\\downarrow$",
            "Peak Resistance $\\uparrow$",
        ],
        rows=rows,
        note_lines=[
            "Each cell reports mean $\\pm$ sample std with the 95\\% confidence-interval half-width shown in parentheses.",
            "IR/RR reuse the same run-level behavioral proxy definitions as the main paper tables.",
        ],
    )


def build_proxy_latex_table(summaries: list[dict[str, object]]) -> str:
    rows: list[list[str]] = []
    for summary in summaries:
        metrics = summary["metrics"]
        rows.append(
            [
                condition_label(str(summary["condition"])),
                str(summary["n"]),
                latex_stat(metrics["agree_comment_pct"]),
                latex_stat(metrics["disagree_comment_pct"]),
                latex_stat(metrics["skepticism_pct"]),
                latex_stat(metrics["vigilance_pct"]),
                latex_stat(metrics["anger_pct"]),
            ]
        )
    return build_latex_table(
        caption="Multi-seed proxy stance and emotion summaries in the 500-agent main comparison.",
        label="tab:main_multiseed_proxy_results",
        headers=[
            "Condition",
            "$n$",
            "Agree $\\downarrow$",
            "Disagree $\\uparrow$",
            "Skepticism $\\uparrow$",
            "Vigilance",
            "Anger $\\downarrow$",
        ],
        rows=rows,
        note_lines=[
            "Each cell reports mean $\\pm$ sample std with the 95\\% confidence-interval half-width shown in parentheses.",
            "All values are percentages aggregated from the unified paper-facing parser.",
        ],
    )


def main() -> None:
    args = parse_args()
    metrics_dir = Path(args.metrics_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    summaries: list[dict[str, object]] = []
    for condition in args.conditions:
        rows = load_condition_rows(metrics_dir, condition)
        if not rows:
            raise FileNotFoundError(
                f"No *_metrics.json files found for condition '{condition}' in {metrics_dir}"
            )
        summaries.append(
            {
                "condition": condition,
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
    proxy_tex_path = output_dir / f"{args.label}_proxy_table.tex"

    json_path.write_text(json.dumps({"label": args.label, "conditions": summaries}, indent=2), encoding="utf-8")
    write_csv(csv_path, summaries)
    md_path.write_text(build_markdown(args.label, summaries), encoding="utf-8")
    macro_tex_path.write_text(build_macro_latex_table(summaries), encoding="utf-8")
    proxy_tex_path.write_text(build_proxy_latex_table(summaries), encoding="utf-8")

    print(
        json.dumps(
            {
                "json": str(json_path),
                "csv": str(csv_path),
                "markdown": str(md_path),
                "macro_tex": str(macro_tex_path),
                "proxy_tex": str(proxy_tex_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
