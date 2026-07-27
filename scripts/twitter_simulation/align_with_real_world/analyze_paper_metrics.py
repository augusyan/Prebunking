from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Iterable

import numpy as np


REPRESENTATIVE_EMOTIONS = ("skepticism", "vigilance", "anger", "neutral")
PROFILE_NOTE_MARKER = "[PREBUNKING MESSAGE EXPOSURE]"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate paper-facing metrics from a simulation database."
    )
    parser.add_argument("--db-path", required=True, help="Path to the SQLite DB.")
    parser.add_argument("--csv-path", required=True, help="Path to the agent CSV.")
    parser.add_argument(
        "--results-dir",
        default=None,
        help="Optional results directory that contains post_stats_data_*.npy.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for JSON and Markdown summaries.",
    )
    parser.add_argument(
        "--label",
        default=None,
        help="Label prefix for output files. Defaults to DB stem.",
    )
    return parser.parse_args()


def load_user_groups(
    csv_path: Path, conn: sqlite3.Connection
) -> tuple[set[int], set[int], set[int], set[int]]:
    csv_rows: list[dict[str, str]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        csv_rows = list(reader)

    csv_user_ids = [int(row["user_id"]) for row in csv_rows]
    db_user_rows = conn.execute(
        "SELECT user_id, user_name, name FROM user ORDER BY user_id"
    ).fetchall()
    db_user_ids = {int(row[0]) for row in db_user_rows}

    if set(csv_user_ids).issubset(db_user_ids):
        user_id_mapping = {user_id: user_id for user_id in csv_user_ids}
    else:
        if len(csv_rows) != len(db_user_rows):
            raise RuntimeError(
                "CSV user ids do not match database user ids, and row-count fallback "
                "cannot be applied safely."
            )

        mismatches: list[str] = []
        user_id_mapping: dict[int, int] = {}
        for csv_row, db_row in zip(csv_rows, db_user_rows):
            csv_username = csv_row.get("username", "")
            csv_name = csv_row.get("name", "")
            db_username = db_row[1] or ""
            db_name = db_row[2] or ""
            if csv_username != db_username or csv_name != db_name:
                mismatches.append(
                    f"csv=({csv_username}, {csv_name}) db=({db_username}, {db_name})"
                )
                if len(mismatches) >= 3:
                    break
            user_id_mapping[int(csv_row["user_id"])] = int(db_row[0])

        if mismatches:
            mismatch_preview = "; ".join(mismatches)
            raise RuntimeError(
                "CSV user ids do not match database user ids, and row-order fallback "
                f"could not be validated: {mismatch_preview}"
            )

    benign_users: set[int] = set()
    bad_users: set[int] = set()
    treated_benign_users: set[int] = set()
    for row in csv_rows:
        mapped_user_id = user_id_mapping[int(row["user_id"])]
        user_type = row["user_type"]
        if "bad" in user_type:
            bad_users.add(mapped_user_id)
        else:
            benign_users.add(mapped_user_id)
            if user_type != "good" or PROFILE_NOTE_MARKER in (row.get("user_char") or ""):
                treated_benign_users.add(mapped_user_id)
    untreated_benign_users = benign_users - treated_benign_users
    return benign_users, bad_users, treated_benign_users, untreated_benign_users


def fetch_rows(
    conn: sqlite3.Connection, query: str, params: Iterable[object]
) -> list[tuple]:
    return conn.execute(query, tuple(params)).fetchall()


def fetch_scalar(
    conn: sqlite3.Connection, query: str, params: Iterable[object]
) -> int | float | str | None:
    row = conn.execute(query, tuple(params)).fetchone()
    if row is None:
        return None
    return row[0]


def placeholder_list(size: int) -> str:
    return ",".join("?" for _ in range(size))


def distinct_user_ids(conn: sqlite3.Connection, query: str, params: list[object]) -> set[int]:
    return {int(row[0]) for row in fetch_rows(conn, query, params)}


def summarize_user_response_metrics(
    conn: sqlite3.Connection,
    user_ids: set[int],
    bad_post_ids: list[int],
) -> dict[str, object]:
    user_count = len(user_ids)
    if user_count == 0:
        return {
            "user_count": 0,
            "infection_user_count": 0,
            "resistance_user_count": 0,
            "infection_rate_pct": 0.0,
            "resistance_rate_pct": 0.0,
            "infection_components": {
                "like_user_count": 0,
                "repost_user_count": 0,
            },
            "resistance_components": {
                "dislike_user_count": 0,
                "disagree_comment_user_count": 0,
            },
        }

    user_placeholders = placeholder_list(user_count)
    user_params = sorted(user_ids)

    infection_like_users = distinct_user_ids(
        conn,
        (
            f'SELECT DISTINCT user_id FROM "like" '
            f"WHERE user_id IN ({user_placeholders}) "
            f"AND post_id IN ({placeholder_list(len(bad_post_ids))})"
        ),
        user_params + bad_post_ids,
    )
    infection_repost_users = distinct_user_ids(
        conn,
        (
            f"SELECT DISTINCT user_id FROM post "
            f"WHERE user_id IN ({user_placeholders}) "
            f"AND original_post_id IN ({placeholder_list(len(bad_post_ids))})"
        ),
        user_params + bad_post_ids,
    )
    infection_users = infection_like_users | infection_repost_users

    resistance_dislike_users = distinct_user_ids(
        conn,
        (
            f'SELECT DISTINCT user_id FROM "dislike" '
            f"WHERE user_id IN ({user_placeholders}) "
            f"AND post_id IN ({placeholder_list(len(bad_post_ids))})"
        ),
        user_params + bad_post_ids,
    )
    resistance_comment_users = distinct_user_ids(
        conn,
        (
            f"SELECT DISTINCT user_id FROM comment "
            f"WHERE user_id IN ({user_placeholders}) "
            f"AND post_id IN ({placeholder_list(len(bad_post_ids))}) "
            f"AND agree = 0"
        ),
        user_params + bad_post_ids,
    )
    resistance_users = resistance_dislike_users | resistance_comment_users

    return {
        "user_count": user_count,
        "infection_user_count": len(infection_users),
        "resistance_user_count": len(resistance_users),
        "infection_rate_pct": round(pct(len(infection_users), user_count), 4),
        "resistance_rate_pct": round(pct(len(resistance_users), user_count), 4),
        "infection_components": {
            "like_user_count": len(infection_like_users),
            "repost_user_count": len(infection_repost_users),
        },
        "resistance_components": {
            "dislike_user_count": len(resistance_dislike_users),
            "disagree_comment_user_count": len(resistance_comment_users),
        },
    }


def find_latest_stats(results_dir: Path, csv_path: Path) -> Path | None:
    stem = csv_path.stem
    candidates = sorted(
        results_dir.glob(f"post_stats_data_{stem}_*.npy"),
        key=lambda item: item.stat().st_mtime,
    )
    return candidates[-1] if candidates else None


def pct(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return 100.0 * numerator / denominator


def main() -> None:
    args = parse_args()
    db_path = Path(args.db_path).resolve()
    csv_path = Path(args.csv_path).resolve()
    output_dir = Path(args.output_dir).resolve()
    label = args.label or db_path.stem
    results_dir = Path(args.results_dir).resolve() if args.results_dir else None

    if not db_path.exists():
        raise FileNotFoundError(db_path)
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    benign_users, bad_users, treated_benign_users, untreated_benign_users = load_user_groups(csv_path, conn)
    benign_count = len(benign_users)

    bad_user_placeholders = placeholder_list(len(bad_users))
    benign_user_placeholders = placeholder_list(len(benign_users))

    bad_post_rows = fetch_rows(
        conn,
        f"SELECT post_id FROM post WHERE user_id IN ({bad_user_placeholders})",
        sorted(bad_users),
    )
    bad_post_ids = [int(row[0]) for row in bad_post_rows]
    if not bad_post_ids:
        raise RuntimeError("No bad-user posts found in the database.")

    bad_post_placeholders = placeholder_list(len(bad_post_ids))
    benign_params = sorted(benign_users)

    infection_like_users = distinct_user_ids(
        conn,
        (
            f'SELECT DISTINCT user_id FROM "like" '
            f"WHERE user_id IN ({benign_user_placeholders}) "
            f"AND post_id IN ({bad_post_placeholders})"
        ),
        benign_params + bad_post_ids,
    )
    infection_repost_users = distinct_user_ids(
        conn,
        (
            f"SELECT DISTINCT user_id FROM post "
            f"WHERE user_id IN ({benign_user_placeholders}) "
            f"AND original_post_id IN ({bad_post_placeholders})"
        ),
        benign_params + bad_post_ids,
    )
    infection_users = infection_like_users | infection_repost_users

    resistance_dislike_users = distinct_user_ids(
        conn,
        (
            f'SELECT DISTINCT user_id FROM "dislike" '
            f"WHERE user_id IN ({benign_user_placeholders}) "
            f"AND post_id IN ({bad_post_placeholders})"
        ),
        benign_params + bad_post_ids,
    )
    resistance_comment_users = distinct_user_ids(
        conn,
        (
            f"SELECT DISTINCT user_id FROM comment "
            f"WHERE user_id IN ({benign_user_placeholders}) "
            f"AND post_id IN ({bad_post_placeholders}) "
            f"AND agree = 0"
        ),
        benign_params + bad_post_ids,
    )
    resistance_users = resistance_dislike_users | resistance_comment_users

    comment_rows = fetch_rows(
        conn,
        (
            f"SELECT agree, emotion FROM comment "
            f"WHERE user_id IN ({benign_user_placeholders}) "
            f"AND post_id IN ({bad_post_placeholders})"
        ),
        benign_params + bad_post_ids,
    )
    total_comments = len(comment_rows)
    agree_comments = sum(1 for row in comment_rows if int(row[0]) == 1)
    disagree_comments = total_comments - agree_comments
    emotion_counter = Counter((row[1] or "neutral").lower() for row in comment_rows)

    metrics: dict[str, object] = {
        "label": label,
        "db_path": str(db_path),
        "csv_path": str(csv_path),
        "benign_user_count": benign_count,
        "bad_user_count": len(bad_users),
        "treated_benign_user_count": len(treated_benign_users),
        "untreated_benign_user_count": len(untreated_benign_users),
        "bad_post_count": len(bad_post_ids),
        "macro": {
            "infection_user_count": len(infection_users),
            "resistance_user_count": len(resistance_users),
            "infection_rate_pct": round(pct(len(infection_users), benign_count), 4),
            "resistance_rate_pct": round(pct(len(resistance_users), benign_count), 4),
            "infection_components": {
                "like_user_count": len(infection_like_users),
                "repost_user_count": len(infection_repost_users),
            },
            "resistance_components": {
                "dislike_user_count": len(resistance_dislike_users),
                "disagree_comment_user_count": len(resistance_comment_users),
            },
        },
        "group_macro": {
            "treated_benign": summarize_user_response_metrics(
                conn,
                treated_benign_users,
                bad_post_ids,
            ),
            "untreated_benign": summarize_user_response_metrics(
                conn,
                untreated_benign_users,
                bad_post_ids,
            ),
        },
        "micro": {
            "comment_count": total_comments,
            "stance_comment_counts": {
                "agree_true": agree_comments,
                "agree_false": disagree_comments,
            },
            "stance_comment_pct": {
                "agree_true": round(pct(agree_comments, total_comments), 4),
                "agree_false": round(pct(disagree_comments, total_comments), 4),
            },
            "representative_emotions": {
                emotion: {
                    "count": emotion_counter.get(emotion, 0),
                    "pct": round(
                        pct(emotion_counter.get(emotion, 0), total_comments), 4
                    ),
                }
                for emotion in REPRESENTATIVE_EMOTIONS
            },
            "all_emotions": dict(sorted(emotion_counter.items())),
        },
    }

    if results_dir is not None and results_dir.exists():
        stats_path = find_latest_stats(results_dir, csv_path)
        if stats_path is not None:
            stats = np.load(stats_path)
            infection_proxy = stats[:, 0] + stats[:, 1] + stats[:, 2]
            resistance_proxy = stats[:, 3]
            metrics["time_series"] = {
                "stats_path": str(stats_path),
                "columns": [
                    "good_like_count",
                    "good_repost_count",
                    "agree_comment_count",
                    "disagree_comment_count",
                ],
                "peak_infection_proxy_step": int(np.argmax(infection_proxy) + 1),
                "peak_infection_proxy_value": float(np.max(infection_proxy)),
                "peak_resistance_step": int(np.argmax(resistance_proxy) + 1),
                "peak_resistance_value": float(np.max(resistance_proxy)),
                "series": stats.tolist(),
            }

    conn.close()

    json_path = output_dir / f"{label}_metrics.json"
    md_path = output_dir / f"{label}_metrics.md"
    json_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    representative_lines = []
    for emotion in REPRESENTATIVE_EMOTIONS:
        item = metrics["micro"]["representative_emotions"][emotion]  # type: ignore[index]
        representative_lines.append(
            f"- {emotion}: {item['count']} comments ({item['pct']:.2f}%)"
        )

    markdown = "\n".join(
        [
            f"# {label}",
            "",
            "## Macro",
            (
                f"- Infection Rate: {metrics['macro']['infection_rate_pct']:.2f}% "
                f"({metrics['macro']['infection_user_count']} / {benign_count})"
            ),
            (
                f"- Resistance Rate: {metrics['macro']['resistance_rate_pct']:.2f}% "
                f"({metrics['macro']['resistance_user_count']} / {benign_count})"
            ),
            (
                f"- Infection components: likes={metrics['macro']['infection_components']['like_user_count']}, "
                f"reposts={metrics['macro']['infection_components']['repost_user_count']}"
            ),
            (
                f"- Resistance components: dislikes={metrics['macro']['resistance_components']['dislike_user_count']}, "
                f"disagree_comments={metrics['macro']['resistance_components']['disagree_comment_user_count']}"
            ),
            (
                f"- Treated benigns: {metrics['treated_benign_user_count']} "
                f"(IR {metrics['group_macro']['treated_benign']['infection_rate_pct']:.2f}%, "
                f"RR {metrics['group_macro']['treated_benign']['resistance_rate_pct']:.2f}%)"
            ),
            (
                f"- Untreated benigns: {metrics['untreated_benign_user_count']} "
                f"(IR {metrics['group_macro']['untreated_benign']['infection_rate_pct']:.2f}%, "
                f"RR {metrics['group_macro']['untreated_benign']['resistance_rate_pct']:.2f}%)"
            ),
            "",
            "## Micro",
            (
                f"- Agree stance: {metrics['micro']['stance_comment_counts']['agree_true']} comments "
                f"({metrics['micro']['stance_comment_pct']['agree_true']:.2f}%)"
            ),
            (
                f"- Disagree stance: {metrics['micro']['stance_comment_counts']['agree_false']} comments "
                f"({metrics['micro']['stance_comment_pct']['agree_false']:.2f}%)"
            ),
            "- Representative emotions:",
            *representative_lines,
        ]
    )
    md_path.write_text(markdown + "\n", encoding="utf-8")

    print(json.dumps({"json": str(json_path), "markdown": str(md_path)}, indent=2))


if __name__ == "__main__":
    main()
