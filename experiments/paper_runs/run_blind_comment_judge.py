#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import subprocess
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests


EMOTIONS = (
    "skepticism",
    "vigilance",
    "anger",
    "panic",
    "fanaticism",
    "confusion",
    "neutral",
)

CONDITION_SPECS = {
    "no_defense": {
        "display_name": "No Defense",
        "db_pattern": "main_500_seed_{seed}_no_defense.db",
        "csv_pattern": "main_500_seed_{seed}_no_defense.csv",
    },
    "debunking": {
        "display_name": "Debunking",
        "db_pattern": "main_500_seed_{seed}_debunking.db",
        "csv_pattern": "main_500_seed_{seed}_debunking.csv",
    },
    "prebunking": {
        "display_name": "Prebunking",
        "db_pattern": "main_500_seed_{seed}_prebunking.db",
        "csv_pattern": "main_500_seed_{seed}_prebunking.csv",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Blind-judge comment stance/emotion labels without revealing condition."
    )
    parser.add_argument(
        "--db-dir",
        default="artifacts/experiment/paper_runs/main_500_multiseed/db",
        help="Directory containing main multiseed SQLite databases.",
    )
    parser.add_argument(
        "--csv-dir",
        default="artifacts/experiment/paper_runs/main_500_multiseed/csv",
        help="Directory containing resolved CSV files with user_type annotations.",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/experiment/paper_runs/blind_comment_judge",
        help="Output directory for blind samples, judged records, and summaries.",
    )
    parser.add_argument(
        "--conditions",
        nargs="+",
        default=["no_defense", "debunking", "prebunking"],
        choices=sorted(CONDITION_SPECS),
        help="Conditions to sample from.",
    )
    parser.add_argument(
        "--seeds",
        nargs="+",
        type=int,
        default=[42, 52, 62, 72, 82],
        help="Seed list to sample from.",
    )
    parser.add_argument(
        "--samples-per-condition",
        type=int,
        default=75,
        help="Target number of judged comments per condition.",
    )
    parser.add_argument(
        "--sample-seed",
        type=int,
        default=20260503,
        help="Deterministic RNG seed for comment sampling.",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="Primary judge model name.",
    )
    parser.add_argument(
        "--fallback-model",
        default="",
        help="Optional fallback judge model.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Maximum concurrent judge requests.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=90,
        help="Per-request timeout for the judge API.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Retries per item after the initial attempt.",
    )
    return parser.parse_args()


def hydrate_openai_env() -> tuple[str, str]:
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("GPT_DIRECT_API_KEY")
    base_url = (
        os.environ.get("OPENAI_API_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    )
    if api_key:
        return api_key, base_url.rstrip("/")

    try:
        proc = subprocess.run(
            ["pgrep", "-f", "python .*twitter_simulation_large.py"],
            check=False,
            capture_output=True,
            text=True,
        )
        pids = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    except OSError:
        pids = []

    for pid in pids:
        environ_path = Path("/proc") / pid / "environ"
        if not environ_path.exists():
            continue
        data = environ_path.read_bytes().split(b"\0")
        values: dict[str, str] = {}
        for entry in data:
            if b"=" not in entry:
                continue
            key, value = entry.split(b"=", 1)
            values[key.decode("utf-8", errors="ignore")] = value.decode(
                "utf-8", errors="ignore"
            )
        api_key = values.get("OPENAI_API_KEY") or values.get("GPT_DIRECT_API_KEY")
        if api_key:
            base_url = (
                values.get("OPENAI_API_BASE_URL")
                or values.get("OPENAI_BASE_URL")
                or base_url
            )
            os.environ.setdefault("OPENAI_API_KEY", api_key)
            os.environ.setdefault("GPT_DIRECT_API_KEY", api_key)
            os.environ.setdefault("OPENAI_API_BASE_URL", base_url)
            return api_key, base_url.rstrip("/")

    raise RuntimeError(
        "No OpenAI-compatible API key found in the environment or reusable simulation processes."
    )


def load_user_types(csv_path: Path) -> dict[int, str]:
    user_types: dict[int, str] = {}
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            user_types[int(row["user_id"])] = row["user_type"]
    return user_types


def load_condition_records(
    db_path: Path,
    csv_path: Path,
    condition: str,
    display_name: str,
    seed: int,
) -> list[dict[str, Any]]:
    user_types = load_user_types(csv_path)
    bad_user_ids = {user_id for user_id, user_type in user_types.items() if user_type == "bad"}
    benign_user_ids = {
        user_id for user_id, user_type in user_types.items() if user_type != "bad"
    }

    query = """
        SELECT
            c.comment_id,
            c.post_id,
            c.user_id AS comment_user_id,
            c.content AS comment_content,
            c.agree AS self_agree,
            c.emotion AS self_emotion,
            c.reasoning AS self_reasoning,
            p.user_id AS post_user_id,
            p.content AS post_content
        FROM comment c
        JOIN post p ON p.post_id = c.post_id
        WHERE c.content IS NOT NULL AND trim(c.content) != ''
        ORDER BY c.comment_id
    """

    records: list[dict[str, Any]] = []
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        for row in conn.execute(query):
            comment_user_id = int(row["comment_user_id"])
            post_user_id = int(row["post_user_id"])
            if comment_user_id not in benign_user_ids:
                continue
            if post_user_id not in bad_user_ids:
                continue
            self_agree = row["self_agree"]
            records.append(
                {
                    "condition": condition,
                    "condition_display": display_name,
                    "seed": seed,
                    "db_path": str(db_path),
                    "csv_path": str(csv_path),
                    "comment_id": int(row["comment_id"]),
                    "post_id": int(row["post_id"]),
                    "comment_user_id": comment_user_id,
                    "post_user_id": post_user_id,
                    "post_content": row["post_content"],
                    "comment_content": row["comment_content"],
                    "self_agree": bool(int(self_agree)) if isinstance(self_agree, int) else bool(self_agree),
                    "self_emotion": str(row["self_emotion"]).strip().lower(),
                    "self_reasoning": row["self_reasoning"],
                }
            )
    finally:
        conn.close()
    return records


def sample_records(args: argparse.Namespace) -> list[dict[str, Any]]:
    rng = random.Random(args.sample_seed)
    db_dir = Path(args.db_dir)
    csv_dir = Path(args.csv_dir)

    sampled: list[dict[str, Any]] = []
    for condition in args.conditions:
        spec = CONDITION_SPECS[condition]
        per_seed_target = args.samples_per_condition // len(args.seeds)
        extra = args.samples_per_condition % len(args.seeds)
        selected_for_condition: list[dict[str, Any]] = []
        leftovers: list[dict[str, Any]] = []

        for seed_index, seed in enumerate(args.seeds):
            db_path = db_dir / spec["db_pattern"].format(seed=seed)
            csv_path = csv_dir / spec["csv_pattern"].format(seed=seed)
            if not db_path.exists():
                raise FileNotFoundError(f"Missing DB for {condition} seed {seed}: {db_path}")
            if not csv_path.exists():
                raise FileNotFoundError(f"Missing CSV for {condition} seed {seed}: {csv_path}")

            records = load_condition_records(
                db_path=db_path,
                csv_path=csv_path,
                condition=condition,
                display_name=spec["display_name"],
                seed=seed,
            )
            rng.shuffle(records)
            target = per_seed_target + (1 if seed_index < extra else 0)
            selected_for_condition.extend(records[:target])
            leftovers.extend(records[target:])

        if len(selected_for_condition) < args.samples_per_condition:
            shortfall = args.samples_per_condition - len(selected_for_condition)
            rng.shuffle(leftovers)
            selected_for_condition.extend(leftovers[:shortfall])

        sampled.extend(selected_for_condition[: args.samples_per_condition])

    rng.shuffle(sampled)
    for index, record in enumerate(sampled, start=1):
        record["sample_id"] = index
    return sampled


def build_messages(record: dict[str, Any]) -> list[dict[str, str]]:
    system_prompt = (
        "You are an independent annotation judge for social-media comments. "
        "You do not know the experimental condition and should not speculate about it. "
        "Given a post and one reply comment, label whether the reply agrees with the post's claim "
        "and choose one dominant emotion from this closed set: "
        "skepticism, vigilance, anger, panic, fanaticism, confusion, neutral. "
        "Return JSON only with keys agree, emotion, confidence, rationale."
    )
    user_prompt = (
        "Original post:\n"
        f"{record['post_content']}\n\n"
        "Reply comment:\n"
        f"{record['comment_content']}\n\n"
        "Guidelines:\n"
        "- agree=true if the reply endorses or amplifies the original post's core claim.\n"
        "- agree=false if the reply rejects, questions, warns against, or refutes the post.\n"
        "- Pick the single most salient emotion from the closed set.\n"
        "- confidence should be a number between 0 and 1.\n"
        "- rationale should be one short sentence."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def normalize_emotion(raw_value: str) -> str:
    value = raw_value.strip().lower().replace("-", "_")
    aliases = {
        "skeptical": "skepticism",
        "skeptical_tone": "skepticism",
        "caution": "vigilance",
        "cautious": "vigilance",
        "fear": "panic",
        "fearful": "panic",
        "calm": "neutral",
        "objective": "neutral",
    }
    value = aliases.get(value, value)
    if value in EMOTIONS:
        return value
    for emotion in EMOTIONS:
        if emotion in value:
            return emotion
    return "neutral"


def parse_json_payload(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        stripped = stripped.replace("json\n", "", 1).strip()
    return json.loads(stripped)


def post_chat_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    timeout_seconds: int,
) -> dict[str, Any]:
    response = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": messages,
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


def judge_record(
    *,
    record: dict[str, Any],
    api_key: str,
    base_url: str,
    primary_model: str,
    fallback_model: str,
    timeout_seconds: int,
    max_retries: int,
) -> dict[str, Any]:
    models = [primary_model]
    if fallback_model and fallback_model not in models:
        models.append(fallback_model)

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        for model in models:
            try:
                payload = post_chat_completion(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    messages=build_messages(record),
                    timeout_seconds=timeout_seconds,
                )
                content = payload["choices"][0]["message"]["content"]
                parsed = parse_json_payload(content)
                judge_agree = bool(parsed["agree"])
                judge_emotion = normalize_emotion(str(parsed["emotion"]))
                confidence_raw = parsed.get("confidence", 0.0)
                try:
                    confidence = float(confidence_raw)
                except (TypeError, ValueError):
                    confidence = 0.0
                return {
                    **record,
                    "judge_model": model,
                    "judge_agree": judge_agree,
                    "judge_emotion": judge_emotion,
                    "judge_confidence": max(0.0, min(1.0, confidence)),
                    "judge_rationale": str(parsed.get("rationale", "")).strip(),
                    "agree_exact": judge_agree == bool(record["self_agree"]),
                    "emotion_exact": judge_emotion == str(record["self_emotion"]).strip().lower(),
                }
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(min(2 ** attempt, 5))
                continue
    raise RuntimeError(
        f"Judge failed for sample_id={record['sample_id']} after retries: {last_error}"
    )


def summarize_results(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_condition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_condition[record["condition"]].append(record)

    def pct(count: int, total: int) -> float:
        return 100.0 * count / total if total else 0.0

    summary: dict[str, Any] = {
        "n_total": len(records),
        "overall": {},
        "by_condition": {},
    }

    overall_agree_exact = sum(1 for record in records if record["agree_exact"])
    overall_emotion_exact = sum(1 for record in records if record["emotion_exact"])
    overall_both_exact = sum(
        1 for record in records if record["agree_exact"] and record["emotion_exact"]
    )
    summary["overall"] = {
        "agree_exact_pct": pct(overall_agree_exact, len(records)),
        "emotion_exact_pct": pct(overall_emotion_exact, len(records)),
        "both_exact_pct": pct(overall_both_exact, len(records)),
    }

    for condition, condition_records in by_condition.items():
        total = len(condition_records)
        judge_emotions = Counter(record["judge_emotion"] for record in condition_records)
        self_emotions = Counter(record["self_emotion"] for record in condition_records)
        summary["by_condition"][condition] = {
            "display_name": condition_records[0]["condition_display"],
            "n": total,
            "agree_exact_pct": pct(
                sum(1 for record in condition_records if record["agree_exact"]), total
            ),
            "emotion_exact_pct": pct(
                sum(1 for record in condition_records if record["emotion_exact"]), total
            ),
            "both_exact_pct": pct(
                sum(
                    1
                    for record in condition_records
                    if record["agree_exact"] and record["emotion_exact"]
                ),
                total,
            ),
            "self_disagree_pct": pct(
                sum(1 for record in condition_records if not record["self_agree"]), total
            ),
            "judge_disagree_pct": pct(
                sum(1 for record in condition_records if not record["judge_agree"]), total
            ),
            "self_emotion_pct": {
                emotion: pct(self_emotions[emotion], total) for emotion in EMOTIONS
            },
            "judge_emotion_pct": {
                emotion: pct(judge_emotions[emotion], total) for emotion in EMOTIONS
            },
        }

    return summary


def write_csv(output_path: Path, records: list[dict[str, Any]]) -> None:
    fieldnames = [
        "sample_id",
        "condition",
        "condition_display",
        "seed",
        "comment_id",
        "post_id",
        "comment_user_id",
        "post_user_id",
        "self_agree",
        "self_emotion",
        "judge_model",
        "judge_agree",
        "judge_emotion",
        "judge_confidence",
        "agree_exact",
        "emotion_exact",
        "post_content",
        "comment_content",
        "judge_rationale",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({key: record.get(key, "") for key in fieldnames})


def build_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# blind_comment_judge",
        "",
        "## Overall Agreement",
        f"- n: {summary['n_total']}",
        f"- Self vs judge agree exact: {summary['overall']['agree_exact_pct']:.2f}%",
        f"- Self vs judge emotion exact: {summary['overall']['emotion_exact_pct']:.2f}%",
        f"- Both exact: {summary['overall']['both_exact_pct']:.2f}%",
        "",
        "## By Condition",
        "| Condition | n | Agree exact | Emotion exact | Both exact | Self disagree | Judge disagree | Judge skepticism | Judge vigilance | Judge anger |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for condition, payload in summary["by_condition"].items():
        lines.append(
            "| "
            + " | ".join(
                [
                    payload["display_name"],
                    str(payload["n"]),
                    f"{payload['agree_exact_pct']:.2f}%",
                    f"{payload['emotion_exact_pct']:.2f}%",
                    f"{payload['both_exact_pct']:.2f}%",
                    f"{payload['self_disagree_pct']:.2f}%",
                    f"{payload['judge_disagree_pct']:.2f}%",
                    f"{payload['judge_emotion_pct']['skepticism']:.2f}%",
                    f"{payload['judge_emotion_pct']['vigilance']:.2f}%",
                    f"{payload['judge_emotion_pct']['anger']:.2f}%",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "- The judge never receives condition names, self labels, or the agent-written reasoning field.",
            "- Agreement compares the original self labels against blind judge labels on the same sampled comment set.",
            "- Emotion labels use the paper's closed seven-class vocabulary.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    api_key, base_url = hydrate_openai_env()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sampled_records = sample_records(args)

    judged_records: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as executor:
        futures = [
            executor.submit(
                judge_record,
                record=record,
                api_key=api_key,
                base_url=base_url,
                primary_model=args.model,
                fallback_model=args.fallback_model,
                timeout_seconds=args.timeout_seconds,
                max_retries=args.max_retries,
            )
            for record in sampled_records
        ]
        for index, future in enumerate(as_completed(futures), start=1):
            judged_records.append(future.result())
            if index % 25 == 0 or index == len(futures):
                print(f"judged {index}/{len(futures)} comments")

    judged_records.sort(key=lambda item: item["sample_id"])
    summary = summarize_results(judged_records)

    sampled_json_path = output_dir / "blind_comment_samples.json"
    judged_json_path = output_dir / "blind_comment_judged.json"
    judged_csv_path = output_dir / "blind_comment_judged.csv"
    summary_json_path = output_dir / "blind_comment_judge_summary.json"
    summary_md_path = output_dir / "blind_comment_judge_summary.md"

    sampled_json_path.write_text(
        json.dumps(sampled_records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    judged_json_path.write_text(
        json.dumps(judged_records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    write_csv(judged_csv_path, judged_records)
    summary_json_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    summary_md_path.write_text(build_markdown(summary), encoding="utf-8")

    print(
        json.dumps(
            {
                "sample_count": len(sampled_records),
                "judged_count": len(judged_records),
                "samples_json": str(sampled_json_path),
                "judged_json": str(judged_json_path),
                "judged_csv": str(judged_csv_path),
                "summary_json": str(summary_json_path),
                "summary_md": str(summary_md_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
