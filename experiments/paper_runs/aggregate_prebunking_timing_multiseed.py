from __future__ import annotations

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate multi-seed prebunking-timing metrics into summary tables."
    )
    parser.add_argument("--metrics-dir", required=True, help="Directory with *_metrics.json files.")
    parser.add_argument("--output-dir", required=True, help="Directory for summary outputs.")
    parser.add_argument(
        "--label",
        default="main_500_prebunking_timing_multiseed",
        help="Output label prefix.",
    )
    parser.add_argument(
        "--timing-steps",
        nargs="+",
        default=["1", "3", "6"],
        help="Ordered timing steps to aggregate.",
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


def step_label(step: str) -> str:
    return f"t={step}"


def load_step_rows(metrics_dir: Path, step: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for metrics_path in sorted(metrics_dir.glob(f"*timing_t{step}_seed_*_metrics.json")):
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
    fieldnames = ["timing_step", "n", "seeds"]
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
            row = {
                "timing_step": summary["timing_step"],
                "n": summary["n"],
                "seeds": ",".join(str(seed) for seed in summary["seeds"]),
            }
            metric_summary = summary["metrics"]
            for metric_name in METRICS:
                row[f"{metric_name}_mean"] = f"{metric_summary[metric_name]['mean']:.4f}"
                row[f"{metric_name}_std"] = f"{metric_summary[metric_name]['std']:.4f}"
                row[f"{metric_name}_ci95"] = f"{metric_summary[metric_name]['ci95']:.4f}"
            writer.writerow(row)


def build_markdown(label: str, summaries: list[dict[str, object]]) -> str:
    headers = [
        "Timing Window",
        "n",
        "Seeds",
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
                    step_label(str(summary["timing_step"])),
                    str(summary["n"]),
                    ", ".join(str(seed) for seed in summary["seeds"]),
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
            "- All rows use the same 500-agent protocol and the same prebunking wording; only the intervention timestep changes.",
            "- IR/RR reuse the run-level behavioral proxy definitions from the paper-facing analysis scripts.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_latex_table(summaries: list[dict[str, object]]) -> str:
    rows: list[list[str]] = []
    for summary in summaries:
        metrics = summary["metrics"]
        rows.append(
            [
                step_label(str(summary["timing_step"])),
                str(summary["n"]),
                latex_stat(metrics["infection_rate_pct"]),
                latex_stat(metrics["resistance_rate_pct"]),
                latex_stat(metrics["peak_infection_proxy_value"], decimals=1),
                latex_stat(metrics["peak_resistance_value"], decimals=1),
            ]
        )

    body_rows = [" & ".join(row) + r" \\" for row in rows]
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\small",
        r"\caption{Multi-seed timing-window comparison for prebunking in the 500-agent setting.}",
        r"\label{tab:prebunking_timing_multiseed_results}",
        r"\begin{threeparttable}",
        r"\begin{tabular}{lccccc}",
        r"\toprule",
        r"Timing Window & $n$ & IR $\downarrow$ & RR $\uparrow$ & Peak Infection $\downarrow$ & Peak Resistance $\uparrow$ \\",
        r"\midrule",
        *body_rows,
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}[flushleft]",
        r"\footnotesize",
        r"\item Each cell reports mean $\pm$ sample std with the 95\% confidence-interval half-width shown in parentheses.",
        r"\item All rows use the same prebunking wording and differ only in the intervention timestep.",
        r"\end{tablenotes}",
        r"\end{threeparttable}",
        r"\end{table*}",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    metrics_dir = Path(args.metrics_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    summaries: list[dict[str, object]] = []
    for step in args.timing_steps:
        rows = load_step_rows(metrics_dir, step)
        if not rows:
            continue
        seeds = [seed for seed in (row["seed"] for row in rows) if seed is not None]
        summaries.append(
            {
                "timing_step": step,
                "n": len(rows),
                "seeds": sorted(seeds),
                "rows": rows,
                "metrics": summarize(rows),
            }
        )

    if not summaries:
        raise FileNotFoundError(f"No timing multiseed metrics found in {metrics_dir}")

    csv_path = output_dir / f"{args.label}_summary.csv"
    md_path = output_dir / f"{args.label}_summary.md"
    json_path = output_dir / f"{args.label}_summary.json"
    tex_path = output_dir / f"{args.label}_table.tex"

    write_csv(csv_path, summaries)
    md_path.write_text(build_markdown(args.label, summaries), encoding="utf-8")
    json_path.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    tex_path.write_text(build_latex_table(summaries), encoding="utf-8")


if __name__ == "__main__":
    main()
