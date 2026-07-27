#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import statistics
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export meso-level per-post and summary metrics for one condition."
    )
    parser.add_argument("--condition-key", required=True)
    parser.add_argument("--condition-label", required=True)
    parser.add_argument("--csv-path", required=True)
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--per-post-output", required=True)
    parser.add_argument("--summary-output", required=True)
    return parser.parse_args()


def load_bad_users(csv_path: Path) -> set[int]:
    bad_users: set[int] = set()
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("user_type") == "bad":
                bad_users.add(int(row["user_id"]))
    if not bad_users:
        raise ValueError(f"No bad users found in {csv_path}")
    return bad_users


def step_of(created_at: int | None) -> int | None:
    if created_at is None:
        return None
    return int(created_at) // 3


def fmt_ratio(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0 / 0 (0.00%)"
    return f"{numerator} / {denominator} ({100.0 * numerator / denominator:.2f}%)"


def round_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 2)


def write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    if not rows:
        raise ValueError(f"No rows to write for {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_condition_metrics(
    condition_key: str, condition_label: str, csv_path: Path, db_path: Path
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    bad_users = load_bad_users(csv_path)
    bad_user_placeholders = ",".join("?" for _ in bad_users)

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()

        bad_post_rows = cursor.execute(
            f"""
            SELECT post_id, created_at
            FROM post
            WHERE user_id IN ({bad_user_placeholders})
            ORDER BY post_id
            """,
            [*bad_users],
        ).fetchall()
        bad_posts = {int(row["post_id"]): int(row["created_at"]) for row in bad_post_rows}
        if not bad_posts:
            raise ValueError(f"No bad-user posts found in {db_path}")

        post_placeholders = ",".join("?" for _ in bad_posts)
        comment_rows = cursor.execute(
            f"""
            SELECT comment_id, post_id, created_at, agree, user_id
            FROM comment
            WHERE post_id IN ({post_placeholders})
              AND user_id NOT IN ({bad_user_placeholders})
            ORDER BY post_id, created_at, comment_id
            """,
            [*bad_posts.keys(), *bad_users],
        ).fetchall()

    per_post_state: dict[int, dict[str, Any]] = {}
    for post_id, created_at in bad_posts.items():
        per_post_state[post_id] = {
            "bad_post_created_at": created_at,
            "agree_comments": 0,
            "disagree_comments": 0,
            "events": [],
            "benign_comment_users": set(),
            "benign_disagree_users": set(),
        }

    for row in comment_rows:
        post_state = per_post_state[int(row["post_id"])]
        created_at = int(row["created_at"])
        user_id = int(row["user_id"])
        agree_flag = bool(row["agree"])
        delta = 1 if agree_flag else -1
        post_state["events"].append((created_at, delta))
        post_state["benign_comment_users"].add(user_id)
        if agree_flag:
            post_state["agree_comments"] += 1
        else:
            post_state["disagree_comments"] += 1
            post_state["benign_disagree_users"].add(user_id)

    per_post_rows: list[dict[str, Any]] = []
    first_disagree_steps: list[int] = []
    flip_steps: list[int] = []
    disagree_share_pct: list[float] = []
    disagree_density: list[float] = []
    agree_density: list[float] = []
    unique_benign_comment_users: set[int] = set()
    unique_benign_disagree_users: set[int] = set()

    engaged_post_count = 0
    disagree_post_count = 0
    defensive_majority_count = 0

    for post_id in sorted(per_post_state):
        post_state = per_post_state[post_id]
        total_comments = post_state["agree_comments"] + post_state["disagree_comments"]
        unique_benign_comment_users |= post_state["benign_comment_users"]
        unique_benign_disagree_users |= post_state["benign_disagree_users"]

        first_comment_step: int | None = None
        first_disagree_step: int | None = None
        flip_step: int | None = None
        cumulative_agree = 0
        cumulative_disagree = 0
        for created_at, delta in post_state["events"]:
            if first_comment_step is None:
                first_comment_step = step_of(created_at)
            if delta > 0:
                cumulative_agree += 1
            else:
                cumulative_disagree += 1
                if first_disagree_step is None:
                    first_disagree_step = step_of(created_at)
            if flip_step is None and cumulative_disagree > cumulative_agree:
                flip_step = step_of(created_at)

        disagree_share = (
            100.0 * post_state["disagree_comments"] / total_comments if total_comments else None
        )
        defensive_majority = (
            total_comments > 0 and post_state["disagree_comments"] > post_state["agree_comments"]
        )
        if total_comments > 0:
            engaged_post_count += 1
            disagree_share_pct.append(disagree_share or 0.0)
            disagree_density.append(float(post_state["disagree_comments"]))
            agree_density.append(float(post_state["agree_comments"]))
            if defensive_majority:
                defensive_majority_count += 1
        if post_state["disagree_comments"] > 0:
            disagree_post_count += 1
            if first_disagree_step is not None:
                first_disagree_steps.append(first_disagree_step)
        if flip_step is not None:
            flip_steps.append(flip_step)

        per_post_rows.append(
            {
                "condition_key": condition_key,
                "condition_label": condition_label,
                "post_id": post_id,
                "bad_post_created_at": post_state["bad_post_created_at"],
                "bad_post_created_step": step_of(post_state["bad_post_created_at"]),
                "benign_comment_total": total_comments,
                "benign_agree_comments": post_state["agree_comments"],
                "benign_disagree_comments": post_state["disagree_comments"],
                "benign_disagree_share_pct": round_or_none(disagree_share),
                "first_benign_comment_step": first_comment_step,
                "first_disagree_step": first_disagree_step,
                "flip_step": flip_step,
                "defensive_majority": int(defensive_majority),
                "unique_benign_comment_users": len(post_state["benign_comment_users"]),
                "unique_benign_disagree_users": len(post_state["benign_disagree_users"]),
            }
        )

    total_bad_posts = len(per_post_rows)
    summary = {
        "condition_key": condition_key,
        "condition_label": condition_label,
        "bad_posts_total": total_bad_posts,
        "engaged_bad_posts": engaged_post_count,
        "engaged_bad_posts_ratio": fmt_ratio(engaged_post_count, total_bad_posts),
        "posts_with_any_disagree": disagree_post_count,
        "posts_with_any_disagree_ratio": fmt_ratio(disagree_post_count, total_bad_posts),
        "defensive_majority_posts": defensive_majority_count,
        "defensive_majority_ratio_all": fmt_ratio(defensive_majority_count, total_bad_posts),
        "defensive_majority_ratio_engaged": fmt_ratio(
            defensive_majority_count, engaged_post_count
        ),
        "mean_disagree_share_engaged_pct": round_or_none(
            statistics.mean(disagree_share_pct) if disagree_share_pct else None
        ),
        "median_first_disagree_step": round_or_none(
            statistics.median(first_disagree_steps) if first_disagree_steps else None
        ),
        "median_flip_step": round_or_none(
            statistics.median(flip_steps) if flip_steps else None
        ),
        "mean_disagree_comments_per_engaged_post": round_or_none(
            statistics.mean(disagree_density) if disagree_density else None
        ),
        "mean_agree_comments_per_engaged_post": round_or_none(
            statistics.mean(agree_density) if agree_density else None
        ),
        "unique_benign_disagree_users": len(unique_benign_disagree_users),
        "unique_benign_comment_users": len(unique_benign_comment_users),
    }
    return per_post_rows, summary


def main() -> None:
    args = parse_args()
    csv_path = Path(args.csv_path).resolve()
    db_path = Path(args.db_path).resolve()
    per_post_output = Path(args.per_post_output).resolve()
    summary_output = Path(args.summary_output).resolve()

    per_post_rows, summary = build_condition_metrics(
        condition_key=args.condition_key,
        condition_label=args.condition_label,
        csv_path=csv_path,
        db_path=db_path,
    )
    write_csv(per_post_rows, per_post_output)
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(
        json.dumps(
            {
                "condition": summary,
                "rows": per_post_rows,
                "csv_path": str(csv_path),
                "db_path": str(db_path),
                "per_post_output_path": str(per_post_output),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
