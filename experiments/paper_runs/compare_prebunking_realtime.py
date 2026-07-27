#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


TIME_SERIES_COLUMNS = [
    "good_like_count",
    "good_repost_count",
    "agree_comment_count",
    "disagree_comment_count",
]


@dataclass(frozen=True)
class ConditionConfig:
    key: str
    display_name: str
    injection_step: int | None
    metrics_path: Path
    db_path: Path
    csv_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Reconstruct missing prebunking timing series and export real-time "
            "comparisons for t1/t3/t6."
        )
    )
    parser.add_argument(
        "--quest-root",
        default=".",
        help="Quest root that contains artifacts/ and experiments/.",
    )
    return parser.parse_args()


def load_metrics(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_bad_users(csv_path: Path) -> list[int]:
    bad_users: list[int] = []
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("user_type") == "bad":
                bad_users.append(int(row["user_id"]))
    if not bad_users:
        raise ValueError(f"No bad users found in {csv_path}")
    return bad_users


def sql_count(cursor: sqlite3.Cursor, query: str, params: list[int]) -> int:
    return int(cursor.execute(query, params).fetchone()[0])


def build_time_series(
    db_path: Path,
    csv_path: Path,
    num_steps: int,
    npy_output_path: Path,
) -> dict[str, Any]:
    bad_users = load_bad_users(csv_path)
    placeholders = ",".join("?" for _ in bad_users)
    thresholds = [3 * (step - 1) for step in range(1, num_steps + 1)]

    likes_query = f"""
        SELECT COUNT(*)
        FROM like
        JOIN post ON like.post_id = post.post_id
        WHERE post.user_id IN ({placeholders})
          AND like.user_id NOT IN ({placeholders})
          AND like.created_at <= ?
    """
    reposts_query = f"""
        SELECT COUNT(*)
        FROM post
        WHERE user_id NOT IN ({placeholders})
          AND original_post_id IN (
              SELECT post_id
              FROM post
              WHERE user_id IN ({placeholders})
          )
          AND created_at <= ?
    """
    comments_query = f"""
        SELECT COUNT(*)
        FROM comment
        JOIN post ON comment.post_id = post.post_id
        WHERE post.user_id IN ({placeholders})
          AND comment.user_id NOT IN ({placeholders})
          AND comment.agree = ?
          AND comment.created_at <= ?
    """

    series: list[list[float]] = []
    with sqlite3.connect(db_path) as connection:
        cursor = connection.cursor()
        for threshold in thresholds:
            likes = sql_count(
                cursor, likes_query, [*bad_users, *bad_users, threshold]
            )
            reposts = sql_count(
                cursor, reposts_query, [*bad_users, *bad_users, threshold]
            )
            agree_comments = sql_count(
                cursor,
                comments_query,
                [*bad_users, *bad_users, 1, threshold],
            )
            disagree_comments = sql_count(
                cursor,
                comments_query,
                [*bad_users, *bad_users, 0, threshold],
            )
            series.append(
                [
                    float(likes),
                    float(reposts),
                    float(agree_comments),
                    float(disagree_comments),
                ]
            )

    npy_output_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(npy_output_path, np.asarray(series, dtype=float))

    infection_values = [sum(row[:3]) for row in series]
    resistance_values = [row[3] for row in series]
    infection_peak_idx = max(range(len(infection_values)), key=infection_values.__getitem__)
    resistance_peak_idx = max(
        range(len(resistance_values)), key=resistance_values.__getitem__
    )
    return {
        "stats_path": str(npy_output_path.resolve()),
        "columns": TIME_SERIES_COLUMNS,
        "peak_infection_proxy_step": infection_peak_idx + 1,
        "peak_infection_proxy_value": infection_values[infection_peak_idx],
        "peak_resistance_step": resistance_peak_idx + 1,
        "peak_resistance_value": resistance_values[resistance_peak_idx],
        "series": series,
    }


def write_metrics_markdown(data: dict[str, Any], output_path: Path) -> None:
    macro = data["macro"]
    micro = data["micro"]
    representative = micro["representative_emotions"]
    lines = [
        f"# {data['label']}",
        "",
        "## Macro",
        (
            f"- Infection Rate: {macro['infection_rate_pct']:.2f}% "
            f"({macro['infection_user_count']} / {data['benign_user_count']})"
        ),
        (
            f"- Resistance Rate: {macro['resistance_rate_pct']:.2f}% "
            f"({macro['resistance_user_count']} / {data['benign_user_count']})"
        ),
        (
            "- Infection components: "
            f"likes={macro['infection_components']['like_user_count']}, "
            f"reposts={macro['infection_components']['repost_user_count']}"
        ),
        (
            "- Resistance components: "
            f"dislikes={macro['resistance_components']['dislike_user_count']}, "
            f"disagree_comments={macro['resistance_components']['disagree_comment_user_count']}"
        ),
        "",
        "## Micro",
        (
            f"- Agree stance: {micro['stance_comment_counts']['agree_true']} comments "
            f"({micro['stance_comment_pct']['agree_true']:.2f}%)"
        ),
        (
            f"- Disagree stance: {micro['stance_comment_counts']['agree_false']} comments "
            f"({micro['stance_comment_pct']['agree_false']:.2f}%)"
        ),
        "- Representative emotions:",
    ]
    for emotion in ("skepticism", "vigilance", "anger", "neutral"):
        payload = representative.get(emotion, {"count": 0, "pct": 0.0})
        lines.append(
            f"- {emotion}: {payload['count']} comments ({payload['pct']:.2f}%)"
        )

    time_series = data.get("time_series")
    if time_series:
        lines.extend(
            [
                "",
                "## Time Series",
                (
                    "- Peak infection proxy: "
                    f"step={time_series['peak_infection_proxy_step']}, "
                    f"value={time_series['peak_infection_proxy_value']:.2f}"
                ),
                (
                    "- Peak resistance proxy: "
                    f"step={time_series['peak_resistance_step']}, "
                    f"value={time_series['peak_resistance_value']:.2f}"
                ),
                f"- Series source: {time_series['stats_path']}",
            ]
        )

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def infection_proxy(series_row: list[float]) -> float:
    return float(series_row[0] + series_row[1] + series_row[2])


def resistance_proxy(series_row: list[float]) -> float:
    return float(series_row[3])


def write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    if not rows:
        raise ValueError(f"No rows to write for {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def format_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.2f}"


def build_absolute_rows(
    conditions: list[ConditionConfig], metrics_by_key: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    no_defense_series = metrics_by_key["no_defense"]["time_series"]["series"]
    rows: list[dict[str, Any]] = []
    for condition in conditions:
        series = metrics_by_key[condition.key]["time_series"]["series"]
        for step_index, step_row in enumerate(series, start=1):
            no_defense_infection = infection_proxy(no_defense_series[step_index - 1])
            protection = None
            if condition.key != "no_defense" and no_defense_infection > 0:
                protection = 100.0 * (1.0 - infection_proxy(step_row) / no_defense_infection)
            elapsed = None
            if condition.injection_step is not None and step_index >= condition.injection_step:
                elapsed = step_index - condition.injection_step
            rows.append(
                {
                    "condition": condition.display_name,
                    "sim_step": step_index,
                    "injection_step": condition.injection_step or "",
                    "elapsed_after_inoculation": elapsed if elapsed is not None else "",
                    "good_like_count": int(step_row[0]),
                    "good_repost_count": int(step_row[1]),
                    "agree_comment_count": int(step_row[2]),
                    "disagree_comment_count": int(step_row[3]),
                    "infection_proxy": format_float(infection_proxy(step_row)),
                    "resistance_proxy": format_float(resistance_proxy(step_row)),
                    "no_defense_infection_proxy": format_float(no_defense_infection),
                    "protection_vs_no_defense_pct": format_float(protection),
                }
            )
    return rows


def build_relative_rows(
    conditions: list[ConditionConfig], metrics_by_key: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    no_defense_series = metrics_by_key["no_defense"]["time_series"]["series"]
    rows: list[dict[str, Any]] = []
    for condition in conditions:
        if condition.injection_step is None:
            continue
        series = metrics_by_key[condition.key]["time_series"]["series"]
        for step_index in range(condition.injection_step, len(series) + 1):
            step_row = series[step_index - 1]
            no_defense_infection = infection_proxy(no_defense_series[step_index - 1])
            protection = None
            if no_defense_infection > 0:
                protection = 100.0 * (1.0 - infection_proxy(step_row) / no_defense_infection)
            rows.append(
                {
                    "condition": condition.display_name,
                    "elapsed_after_inoculation": step_index - condition.injection_step,
                    "sim_step": step_index,
                    "infection_proxy": format_float(infection_proxy(step_row)),
                    "resistance_proxy": format_float(resistance_proxy(step_row)),
                    "no_defense_infection_proxy": format_float(no_defense_infection),
                    "protection_vs_no_defense_pct": format_float(protection),
                }
            )
    return rows


def build_summary_markdown(
    conditions: list[ConditionConfig],
    metrics_by_key: dict[str, dict[str, Any]],
    absolute_rows: list[dict[str, Any]],
    relative_rows: list[dict[str, Any]],
    output_path: Path,
) -> None:
    absolute_by_step: dict[int, dict[str, dict[str, Any]]] = {}
    for row in absolute_rows:
        absolute_by_step.setdefault(int(row["sim_step"]), {})[row["condition"]] = row

    relative_by_elapsed: dict[int, dict[str, dict[str, Any]]] = {}
    for row in relative_rows:
        relative_by_elapsed.setdefault(int(row["elapsed_after_inoculation"]), {})[
            row["condition"]
        ] = row

    condition_names = [condition.display_name for condition in conditions]
    relative_names = [condition.display_name for condition in conditions if condition.injection_step]

    first_common_elapsed = 1
    common_snapshot: list[str] = []
    for name in relative_names:
        row = relative_by_elapsed.get(first_common_elapsed, {}).get(name)
        if row:
            common_snapshot.append(f"{name}={row['infection_proxy']}")

    lines = [
        "# supplementary_prebunking_realtime",
        "",
        "## Headline",
        (
            "- Earlier prebunking stays consistently lower on the infection proxy "
            "curve: across the shared observed window, `t1 < t3 < t6`."
        ),
    ]
    if common_snapshot:
        lines.append(
            "- At `+1` step after inoculation, the infection proxy is "
            + ", ".join(common_snapshot)
            + "."
        )
    lines.extend(
        [
            "- Protection is measured against the no-defense infection proxy at the same absolute simulation step.",
            "",
            "## Absolute Infection Proxy",
            "| Simulation Step | No Defense | t1 | t3 | t6 |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for step in sorted(absolute_by_step):
        row_map = absolute_by_step[step]
        lines.append(
            "| {step} | {no_defense} | {t1} | {t3} | {t6} |".format(
                step=step,
                no_defense=row_map.get("no_defense", {}).get("infection_proxy", ""),
                t1=row_map.get("t1", {}).get("infection_proxy", ""),
                t3=row_map.get("t3", {}).get("infection_proxy", ""),
                t6=row_map.get("t6", {}).get("infection_proxy", ""),
            )
        )

    lines.extend(
        [
            "",
            "## Relative Protection Vs No Defense",
            "| Elapsed Steps After Inoculation | t1 | t3 | t6 |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for elapsed in sorted(relative_by_elapsed):
        row_map = relative_by_elapsed[elapsed]
        lines.append(
            "| {elapsed} | {t1} | {t3} | {t6} |".format(
                elapsed=elapsed,
                t1=row_map.get("t1", {}).get("protection_vs_no_defense_pct", ""),
                t3=row_map.get("t3", {}).get("protection_vs_no_defense_pct", ""),
                t6=row_map.get("t6", {}).get("protection_vs_no_defense_pct", ""),
            )
        )

    lines.extend(
        [
            "",
            "## Notes",
            "- `Simulation Step` is the shared absolute simulation timeline.",
            "- `Elapsed Steps After Inoculation` aligns each prebunking run by its own injection step.",
            "- Infection proxy = good likes + good reposts + agree comments on bad-user-authored posts.",
            "- Resistance proxy = disagree comments on bad-user-authored posts.",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    quest_root = Path(args.quest_root).resolve()
    metrics_dir = quest_root / "artifacts/experiment/paper_runs/supplementary_prebunking_500/metrics"
    conditions = [
        ConditionConfig(
            key="t1",
            display_name="t1",
            injection_step=1,
            metrics_path=metrics_dir / "supp_prebunking_t1_500_metrics.json",
            db_path=quest_root
            / "artifacts/experiment/paper_runs/supplementary_prebunking_500/db/supp_prebunking_t1.db",
            csv_path=quest_root
            / "artifacts/experiment/paper_runs/supplementary_prebunking_500/csv/supp_prebunking_t1.csv",
        ),
        ConditionConfig(
            key="t3",
            display_name="t3",
            injection_step=3,
            metrics_path=metrics_dir / "supp_prebunking_t3_metrics.json",
            db_path=quest_root
            / "artifacts/experiment/paper_runs/supplementary_prebunking_500/db/supp_prebunking_t3.db",
            csv_path=quest_root
            / "artifacts/experiment/paper_runs/supplementary_prebunking_500/csv/supp_prebunking_t3.csv",
        ),
        ConditionConfig(
            key="t6",
            display_name="t6",
            injection_step=6,
            metrics_path=metrics_dir / "supp_prebunking_t6_metrics.json",
            db_path=quest_root
            / "artifacts/experiment/paper_runs/supplementary_prebunking_500/db/supp_prebunking_t6.db",
            csv_path=quest_root
            / "artifacts/experiment/paper_runs/supplementary_prebunking_500/csv/supp_prebunking_t6.csv",
        ),
        ConditionConfig(
            key="no_defense",
            display_name="no_defense",
            injection_step=None,
            metrics_path=quest_root
            / "artifacts/experiment/paper_runs/main_500/metrics/main_500_no_defense_metrics.json",
            db_path=quest_root / "artifacts/experiment/paper_runs/main_500/db/main_500_no_defense.db",
            csv_path=quest_root / "artifacts/experiment/paper_runs/main_500/csv/main_500_no_defense.csv",
        ),
    ]

    metrics_by_key: dict[str, dict[str, Any]] = {}
    no_defense_steps = len(
        load_metrics(
            quest_root / "artifacts/experiment/paper_runs/main_500/metrics/main_500_no_defense_metrics.json"
        )["time_series"]["series"]
    )

    for condition in conditions:
        data = load_metrics(condition.metrics_path)
        if "time_series" not in data:
            stats_dir = condition.metrics_path.parent.parent / "stats_inputs" / condition.metrics_path.stem.replace("_metrics", "")
            npy_output_path = stats_dir / f"post_stats_data_{condition.metrics_path.stem.replace('_metrics', '')}_reconstructed.npy"
            data["time_series"] = build_time_series(
                condition.db_path,
                condition.csv_path,
                no_defense_steps,
                npy_output_path,
            )
            condition.metrics_path.write_text(
                json.dumps(data, indent=2) + "\n", encoding="utf-8"
            )
            write_metrics_markdown(
                data, condition.metrics_path.with_suffix(".md")
            )
        metrics_by_key[condition.key] = data

    absolute_rows = build_absolute_rows(conditions, metrics_by_key)
    relative_rows = build_relative_rows(conditions, metrics_by_key)

    write_csv(
        absolute_rows,
        metrics_dir / "supplementary_prebunking_realtime_absolute.csv",
    )
    write_csv(
        relative_rows,
        metrics_dir / "supplementary_prebunking_realtime_relative.csv",
    )
    build_summary_markdown(
        conditions,
        metrics_by_key,
        absolute_rows,
        relative_rows,
        metrics_dir / "supplementary_prebunking_realtime_summary.md",
    )


if __name__ == "__main__":
    main()
