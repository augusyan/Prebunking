from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate bad-ratio supplementary prebunking metrics."
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
        default="supplementary_bad_ratio_prebunking",
        help="Section title used in the Markdown report.",
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
    representative = micro["representative_emotions"]
    stance_pct = micro["stance_comment_pct"]
    all_emotions = micro.get("all_emotions", {})
    comment_count = int(micro["comment_count"])
    benign_count = int(data["benign_user_count"])
    bad_count = int(data["bad_user_count"])
    total_agents = benign_count + bad_count

    return {
        "condition": data["label"],
        "bad_user_count": bad_count,
        "bad_ratio_pct": round(100.0 * bad_count / total_agents, 4),
        "infection_rate_pct": macro["infection_rate_pct"],
        "resistance_rate_pct": macro["resistance_rate_pct"],
        "agree_comment_pct": stance_pct["agree_true"],
        "disagree_comment_pct": stance_pct["agree_false"],
        "skepticism_pct": representative.get("skepticism", {}).get("pct", 0.0),
        "vigilance_pct": representative.get("vigilance", {}).get("pct", 0.0),
        "anger_pct": representative.get("anger", {}).get("pct", 0.0),
        "panic_pct": emotion_pct(all_emotions, "panic", comment_count),
        "fanaticism_pct": emotion_pct(all_emotions, "fanaticism", comment_count),
        "confusion_pct": emotion_pct(all_emotions, "confusion", comment_count),
        "neutral_pct": representative.get("neutral", {}).get("pct", 0.0),
        "source_json": str(path.resolve()),
    }


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
        "| Condition | Bad Agents | Bad Ratio % | Infection % | Resistance % | Agree % | Disagree % |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| {condition} | {bad_user_count} | {bad_ratio_pct} | {infection_rate_pct} | "
            "{resistance_rate_pct} | {agree_comment_pct} | {disagree_comment_pct} |".format(
                condition=row["condition"],
                bad_user_count=fmt(row["bad_user_count"]),
                bad_ratio_pct=fmt(row["bad_ratio_pct"]),
                infection_rate_pct=fmt(row["infection_rate_pct"]),
                resistance_rate_pct=fmt(row["resistance_rate_pct"]),
                agree_comment_pct=fmt(row["agree_comment_pct"]),
                disagree_comment_pct=fmt(row["disagree_comment_pct"]),
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
            "| {condition} | {skepticism_pct} | {vigilance_pct} | {anger_pct} | "
            "{panic_pct} | {fanaticism_pct} | {confusion_pct} | {neutral_pct} |".format(
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
            "- All rows use the same 500-agent graph skeleton and the same prebunking setup.",
            "- Only the bad-agent share is changed across rows.",
            "- Infection: benign users who liked or reposted bad-user posts.",
            "- Resistance: benign users who disliked or left disagree comments on bad-user posts.",
            "- Emotion percentages are computed over benign comments on bad-user posts.",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    metrics_dir = Path(args.metrics_dir).resolve()
    output_prefix = Path(args.output_prefix).resolve()

    json_paths = sorted(metrics_dir.glob("*_metrics.json"))
    if not json_paths:
        raise FileNotFoundError(f"No *_metrics.json files found in {metrics_dir}")

    rows = [extract_row(path) for path in json_paths]
    rows.sort(key=lambda row: (float(row["bad_ratio_pct"]), str(row["condition"])))

    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    write_csv(rows, output_prefix.with_suffix(".csv"))
    write_markdown(rows, args.title, output_prefix.with_suffix(".md"))


if __name__ == "__main__":
    main()
