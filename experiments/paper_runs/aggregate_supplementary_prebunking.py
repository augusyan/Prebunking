from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate supplementary prebunking metrics into CSV and Markdown tables."
    )
    parser.add_argument(
        "--metrics-dir",
        required=True,
        help="Directory containing *_metrics.json files.",
    )
    parser.add_argument(
        "--output-prefix",
        required=True,
        help="Output path prefix. Writes <prefix>.csv and <prefix>.md.",
    )
    parser.add_argument(
        "--title",
        default="supplementary_prebunking",
        help="Section title used in the Markdown report.",
    )
    parser.add_argument(
        "--extra-json",
        action="append",
        default=[],
        help="Optional extra metrics JSON paths to include (for example the main prebunking baseline).",
    )
    return parser.parse_args()


def load_metrics(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def emotion_pct(
    emotion_payload: dict[str, object], emotion: str, comment_count: int
) -> float:
    value = emotion_payload.get(emotion, 0.0)
    if isinstance(value, dict):
        return float(value.get("pct", 0.0))
    if comment_count <= 0:
        return 0.0
    return 100.0 * float(value) / float(comment_count)


def extract_row(path: Path) -> dict[str, object]:
    data = load_metrics(path)
    macro = data["macro"]
    micro = data["micro"]
    time_series = data.get("time_series", {})
    representative = micro["representative_emotions"]
    stance_pct = micro["stance_comment_pct"]
    stance_counts = micro["stance_comment_counts"]
    all_emotions = micro.get("all_emotions", {})
    comment_count = int(micro["comment_count"])

    return {
        "condition": data["label"],
        "infection_rate_pct": macro["infection_rate_pct"],
        "resistance_rate_pct": macro["resistance_rate_pct"],
        "infection_user_count": macro["infection_user_count"],
        "resistance_user_count": macro["resistance_user_count"],
        "agree_comment_pct": stance_pct["agree_true"],
        "disagree_comment_pct": stance_pct["agree_false"],
        "agree_comment_count": stance_counts["agree_true"],
        "disagree_comment_count": stance_counts["agree_false"],
        "comment_count": comment_count,
        "peak_infection_proxy_step": time_series.get("peak_infection_proxy_step", ""),
        "peak_infection_proxy_value": time_series.get("peak_infection_proxy_value", ""),
        "peak_resistance_step": time_series.get("peak_resistance_step", ""),
        "peak_resistance_value": time_series.get("peak_resistance_value", ""),
        "skepticism_pct": representative.get("skepticism", {}).get("pct", 0.0),
        "vigilance_pct": representative.get("vigilance", {}).get("pct", 0.0),
        "anger_pct": representative.get("anger", {}).get("pct", 0.0),
        "panic_pct": emotion_pct(all_emotions, "panic", comment_count),
        "fanaticism_pct": emotion_pct(all_emotions, "fanaticism", comment_count),
        "confusion_pct": emotion_pct(all_emotions, "confusion", comment_count),
        "neutral_pct": representative.get("neutral", {}).get("pct", 0.0),
        "source_json": str(path.resolve()),
    }


def sort_key(condition: str) -> tuple[int, int, str]:
    if condition.startswith("supp_prebunking_t"):
        match = re.match(r"supp_prebunking_t(\d+)", condition)
        if match:
            return (0, int(match.group(1)), condition)
    content_order = {
        "supp_prebunking_fact": 0,
        "supp_prebunking_logic": 1,
        "supp_prebunking_technical": 2,
        "supp_prebunking_emotional": 3,
    }
    if condition in content_order:
        return (1, content_order[condition], condition)
    if condition == "supp_prebunking_random_feed":
        return (2, 0, condition)
    if condition == "main_500_prebunking":
        return (3, 0, condition)
    return (4, 0, condition)


def fmt(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def write_csv(rows: list[dict[str, object]], output_path: Path) -> None:
    fieldnames = list(rows[0].keys())
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict[str, object]], title: str, output_path: Path) -> None:
    lines = [
        f"# {title}",
        "",
        "## Outcome and stance",
        "| Condition | Infection % | Resistance % | Agree % | Disagree % | Peak Infection Step | Peak Infection Value | Peak Resistance Step | Peak Resistance Value |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| {condition} | {infection_rate_pct} | {resistance_rate_pct} | {agree_comment_pct} | "
            "{disagree_comment_pct} | {peak_infection_proxy_step} | {peak_infection_proxy_value} | "
            "{peak_resistance_step} | {peak_resistance_value} |".format(
                condition=row["condition"],
                infection_rate_pct=fmt(row["infection_rate_pct"]),
                resistance_rate_pct=fmt(row["resistance_rate_pct"]),
                agree_comment_pct=fmt(row["agree_comment_pct"]),
                disagree_comment_pct=fmt(row["disagree_comment_pct"]),
                peak_infection_proxy_step=fmt(row["peak_infection_proxy_step"]),
                peak_infection_proxy_value=fmt(row["peak_infection_proxy_value"]),
                peak_resistance_step=fmt(row["peak_resistance_step"]),
                peak_resistance_value=fmt(row["peak_resistance_value"]),
            )
        )

    lines.extend(
        [
            "",
            "## Emotion change",
            "| Condition | Skepticism % | Vigilance % | Anger % | Panic % | Fanaticism % | Confusion % | Neutral % |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in rows:
        lines.append(
            "| {condition} | {skepticism_pct} | {vigilance_pct} | {anger_pct} | {panic_pct} | "
            "{fanaticism_pct} | {confusion_pct} | {neutral_pct} |".format(
                condition=row["condition"],
                skepticism_pct=fmt(row["skepticism_pct"]),
                vigilance_pct=fmt(row["vigilance_pct"]),
                anger_pct=fmt(row["anger_pct"]),
                panic_pct=fmt(row["panic_pct"]),
                fanaticism_pct=fmt(row["fanaticism_pct"]),
                confusion_pct=fmt(row["confusion_pct"]),
                neutral_pct=fmt(row["neutral_pct"]),
            )
        )

    lines.extend(
        [
            "",
            "## Notes",
            "- Infection: benign users who liked or reposted bad-user posts.",
            "- Resistance: benign users who disliked or left disagree comments on bad-user posts.",
            "- Emotion percentages are computed over benign comments on bad-user posts.",
            "- The paper-facing summary uses a 7-dimensional emotion view: skepticism, vigilance, anger, panic, fanaticism, confusion, and neutral.",
            "- A single out-of-schema `alarm` token appears once in the raw t=3 aggregation (0.12%) and is treated as an edge case rather than a stable modeled dimension.",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    metrics_dir = Path(args.metrics_dir).resolve()
    output_prefix = Path(args.output_prefix).resolve()

    json_paths = sorted(metrics_dir.glob("*_metrics.json"))
    json_paths.extend(Path(item).resolve() for item in args.extra_json)
    json_paths = sorted(set(json_paths), key=lambda item: sort_key(item.stem.removesuffix("_metrics")))
    if not json_paths:
        raise FileNotFoundError(f"No *_metrics.json files found in {metrics_dir}")

    rows = [extract_row(path) for path in json_paths]
    rows.sort(key=lambda row: sort_key(str(row["condition"])))

    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    write_csv(rows, output_prefix.with_suffix(".csv"))
    write_markdown(rows, args.title, output_prefix.with_suffix(".md"))


if __name__ == "__main__":
    main()
