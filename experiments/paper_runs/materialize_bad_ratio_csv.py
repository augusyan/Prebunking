from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROLE_FIELDS = ("user_type", "description", "previous_tweets", "tweets_id", "user_char")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize a 500-agent CSV with a different bad-agent count while "
            "preserving the original graph and user identities."
        )
    )
    parser.add_argument("--source-csv", required=True, help="Baseline agent CSV.")
    parser.add_argument("--output-csv", required=True, help="Output CSV path.")
    parser.add_argument(
        "--target-bad-count",
        type=int,
        required=True,
        help="Desired number of bad agents in the output CSV.",
    )
    return parser.parse_args()


def load_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        fieldnames = reader.fieldnames
    if fieldnames is None:
        raise ValueError(f"CSV has no header: {path}")
    return fieldnames, rows


def user_id(row: dict[str, str]) -> int:
    return int(row["user_id"])


def is_bad(row: dict[str, str]) -> bool:
    return "bad" in row["user_type"]


def apply_role_fields(
    row: dict[str, str], donor: dict[str, str], target_user_type: str
) -> None:
    for field in ROLE_FIELDS:
        if field == "user_type":
            row[field] = target_user_type
            continue
        row[field] = donor[field]


def take_boundary_rows(rows: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    if count <= 0:
        return []
    return sorted(rows, key=user_id)[-count:]


def donor_cycle(
    donor_pool: list[dict[str, str]], count: int
) -> list[dict[str, str]]:
    if count <= 0:
        return []
    if not donor_pool:
        raise ValueError("Cannot sample donor rows from an empty pool.")
    donors: list[dict[str, str]] = []
    sorted_pool = sorted(donor_pool, key=user_id)
    for idx in range(count):
        donors.append(sorted_pool[idx % len(sorted_pool)])
    return donors


def main() -> None:
    args = parse_args()
    source_csv = Path(args.source_csv).resolve()
    output_csv = Path(args.output_csv).resolve()

    fieldnames, rows = load_rows(source_csv)
    if args.target_bad_count < 0 or args.target_bad_count > len(rows):
        raise ValueError(
            f"target_bad_count={args.target_bad_count} is outside valid range 0..{len(rows)}"
        )

    rows_by_id = {user_id(row): dict(row) for row in rows}
    good_rows = sorted((row for row in rows if not is_bad(row)), key=user_id)
    bad_rows = sorted((row for row in rows if is_bad(row)), key=user_id)

    baseline_bad_count = len(bad_rows)
    target_bad_count = args.target_bad_count

    promoted_ids: list[int] = []
    demoted_ids: list[int] = []

    if target_bad_count > baseline_bad_count:
        promote_count = target_bad_count - baseline_bad_count
        promote_rows = take_boundary_rows(good_rows, promote_count)
        donor_rows = donor_cycle(bad_rows, promote_count)
        for target_row, donor_row in zip(promote_rows, donor_rows):
            apply_role_fields(
                rows_by_id[user_id(target_row)],
                donor_row,
                target_user_type="bad",
            )
            promoted_ids.append(user_id(target_row))
    elif target_bad_count < baseline_bad_count:
        demote_count = baseline_bad_count - target_bad_count
        demote_rows = take_boundary_rows(bad_rows, demote_count)
        donor_rows = donor_cycle(good_rows, demote_count)
        for target_row, donor_row in zip(demote_rows, donor_rows):
            apply_role_fields(
                rows_by_id[user_id(target_row)],
                donor_row,
                target_user_type="good",
            )
            demoted_ids.append(user_id(target_row))

    output_rows = [rows_by_id[user_id(row)] for row in rows]
    final_bad_count = sum(1 for row in output_rows if is_bad(row))
    if final_bad_count != target_bad_count:
        raise RuntimeError(
            f"Expected {target_bad_count} bad rows, but materialized {final_bad_count}."
        )

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    total_agents = len(output_rows)
    print(
        json.dumps(
            {
                "source_csv": str(source_csv),
                "output_csv": str(output_csv),
                "total_agents": total_agents,
                "baseline_bad_count": baseline_bad_count,
                "target_bad_count": target_bad_count,
                "target_bad_ratio_pct": round(100.0 * target_bad_count / total_agents, 4),
                "promoted_ids": promoted_ids,
                "demoted_ids": demoted_ids,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
