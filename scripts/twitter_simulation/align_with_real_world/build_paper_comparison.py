from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


PREFERRED_EMOTION_ORDER = (
    "skepticism",
    "vigilance",
    "anger",
    "panic",
    "fanaticism",
    "confusion",
    "sarcasm",
    "neutral",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build paper-facing comparison tables from per-run metrics JSON files."
    )
    parser.add_argument(
        "--metrics-dir",
        required=True,
        help="Directory containing *_metrics.json files.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for the comparison CSV / Markdown outputs.",
    )
    parser.add_argument(
        "--label",
        required=True,
        help="Output label prefix, e.g. pilot_30 or main_500.",
    )
    parser.add_argument(
        "--conditions",
        nargs="+",
        default=["no_defense", "debunking", "prebunking"],
        help="Ordered condition list to load and render.",
    )
    return parser.parse_args()


def pct(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return 100.0 * count / total


def find_metrics_json(metrics_dir: Path, condition: str) -> Path:
    candidates = sorted(
        metrics_dir.glob(f"*{condition}_metrics.json"),
        key=lambda item: item.stat().st_mtime,
    )
    if not candidates:
        raise FileNotFoundError(
            f"No metrics JSON found for condition '{condition}' in {metrics_dir}"
        )
    return candidates[-1]


def extract_emotion_pct(metrics: dict, emotion: str) -> float:
    micro = metrics.get("micro", {})
    representative = micro.get("representative_emotions", {})
    if emotion in representative:
        return float(representative[emotion]["pct"])

    all_emotions = micro.get("all_emotions", {})
    comment_count = int(micro.get("comment_count", 0))
    return round(pct(int(all_emotions.get(emotion, 0)), comment_count), 4)


def load_row(metrics_path: Path, condition: str) -> dict[str, object]:
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    macro = metrics["macro"]
    micro = metrics["micro"]
    time_series = metrics.get("time_series", {})

    return {
        "condition": condition,
        "label": metrics.get("label", condition),
        "source_json": str(metrics_path),
        "infection_rate_pct": float(macro["infection_rate_pct"]),
        "resistance_rate_pct": float(macro["resistance_rate_pct"]),
        "infection_user_count": int(macro["infection_user_count"]),
        "resistance_user_count": int(macro["resistance_user_count"]),
        "agree_comment_pct": float(micro["stance_comment_pct"]["agree_true"]),
        "disagree_comment_pct": float(micro["stance_comment_pct"]["agree_false"]),
        "agree_comment_count": int(micro["stance_comment_counts"]["agree_true"]),
        "disagree_comment_count": int(micro["stance_comment_counts"]["agree_false"]),
        "comment_count": int(micro["comment_count"]),
        "peak_infection_proxy_step": int(
            time_series.get("peak_infection_proxy_step", 0) or 0
        ),
        "peak_infection_proxy_value": float(
            time_series.get("peak_infection_proxy_value", 0.0) or 0.0
        ),
        "peak_resistance_step": int(time_series.get("peak_resistance_step", 0) or 0),
        "peak_resistance_value": float(
            time_series.get("peak_resistance_value", 0.0) or 0.0
        ),
        "_metrics": metrics,
    }


def discover_emotions(rows: list[dict[str, object]]) -> list[str]:
    present: set[str] = set()
    for row in rows:
        metrics = row["_metrics"]  # type: ignore[index]
        all_emotions = metrics.get("micro", {}).get("all_emotions", {})  # type: ignore[assignment]
        present.update(str(key) for key in all_emotions.keys())

    ordered = [emotion for emotion in PREFERRED_EMOTION_ORDER if emotion in present]
    ordered.extend(sorted(present - set(ordered)))
    return ordered


def markdown_table(headers: list[str], aligns: list[str], rows: list[list[str]]) -> str:
    divider = []
    for align in aligns:
        if align == "right":
            divider.append("---:")
        elif align == "center":
            divider.append(":---:")
        else:
            divider.append("---")
    body = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(divider) + " |",
    ]
    body.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(body)


def format_pct(value: float) -> str:
    return f"{value:.2f}"


def build_markdown(
    label: str, rows: list[dict[str, object]], emotions: list[str]
) -> str:
    outcome_headers = [
        "Condition",
        "Infection %",
        "Resistance %",
        "Agree %",
        "Disagree %",
        "Peak Infection Step",
        "Peak Infection Value",
        "Peak Resistance Step",
        "Peak Resistance Value",
    ]
    outcome_rows = [
        [
            str(row["condition"]),
            format_pct(float(row["infection_rate_pct"])),
            format_pct(float(row["resistance_rate_pct"])),
            format_pct(float(row["agree_comment_pct"])),
            format_pct(float(row["disagree_comment_pct"])),
            str(row["peak_infection_proxy_step"]),
            format_pct(float(row["peak_infection_proxy_value"])),
            str(row["peak_resistance_step"]),
            format_pct(float(row["peak_resistance_value"])),
        ]
        for row in rows
    ]

    emotion_headers = ["Condition"] + [
        emotion.replace("_", " ").title() + " %" for emotion in emotions
    ]
    emotion_rows = []
    for row in rows:
        metrics = row["_metrics"]  # type: ignore[index]
        emotion_rows.append(
            [str(row["condition"])]
            + [format_pct(extract_emotion_pct(metrics, emotion)) for emotion in emotions]
        )

    note_lines = [
        "- Infection: benign users who liked or reposted bad-user posts.",
        "- Resistance: benign users who disliked or left disagree comments on bad-user posts.",
        "- Emotion percentages are computed over benign comments on bad-user posts.",
    ]

    sections = [
        f"# {label} comparison",
        "",
        "## Outcome and stance",
        markdown_table(
            outcome_headers,
            ["left"] + ["right"] * (len(outcome_headers) - 1),
            outcome_rows,
        ),
        "",
        "## Emotion change",
        markdown_table(
            emotion_headers,
            ["left"] + ["right"] * (len(emotion_headers) - 1),
            emotion_rows,
        ),
        "",
        "## Notes",
        *note_lines,
    ]
    return "\n".join(sections) + "\n"


def write_csv(output_path: Path, rows: list[dict[str, object]], emotions: list[str]) -> None:
    fieldnames = [
        "condition",
        "infection_rate_pct",
        "resistance_rate_pct",
        "infection_user_count",
        "resistance_user_count",
        "agree_comment_pct",
        "disagree_comment_pct",
        "agree_comment_count",
        "disagree_comment_count",
        "comment_count",
        "peak_infection_proxy_step",
        "peak_infection_proxy_value",
        "peak_resistance_step",
        "peak_resistance_value",
        *[f"{emotion}_pct" for emotion in emotions],
        "source_json",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            metrics = row["_metrics"]  # type: ignore[index]
            flat = {key: row[key] for key in fieldnames if key in row}
            for emotion in emotions:
                flat[f"{emotion}_pct"] = round(extract_emotion_pct(metrics, emotion), 4)
            writer.writerow(flat)


def main() -> None:
    args = parse_args()
    metrics_dir = Path(args.metrics_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = [
        load_row(find_metrics_json(metrics_dir, condition), condition)
        for condition in args.conditions
    ]
    emotions = discover_emotions(rows)

    csv_path = output_dir / f"{args.label}_comparison.csv"
    md_path = output_dir / f"{args.label}_comparison.md"

    write_csv(csv_path, rows, emotions)
    md_path.write_text(build_markdown(args.label, rows, emotions), encoding="utf-8")

    print(
        json.dumps(
            {
                "csv": str(csv_path),
                "markdown": str(md_path),
                "conditions": args.conditions,
                "emotions": emotions,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
