import argparse
import sqlite3


def main() -> None:
    parser = argparse.ArgumentParser(description="Count original posts above a user ID.")
    parser.add_argument("db_path", help="Path to the SQLite database.")
    parser.add_argument("--min-user-id", type=int, default=900)
    args = parser.parse_args()

    with sqlite3.connect(args.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM post "
            "WHERE original_post_id IS NULL AND user_id > ?",
            (args.min_user_id,),
        )
        count = cursor.fetchone()[0]

    print(f"Matching original posts: {count}")


if __name__ == "__main__":
    main()
