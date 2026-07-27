from __future__ import annotations

import argparse
import csv
import json
import random
from copy import deepcopy
from pathlib import Path

from yaml import safe_dump, safe_load


PREBUNKING_VARIANT_TO_USER_TYPE = {
    None: "good_prebunking",
    "generic": "good_prebunking",
    "fact": "good_prebunking_fact",
    "logic": "good_prebunking_logic",
    "technical": "good_prebunking_technical",
    "emotional": "good_prebunking_emotional",
    "counter": "good_prebunking_counter",
}

PREBUNKING_VARIANT_TO_PROFILE_NOTE = {
    None: (
        "You recently saw a short prebunking message reminding you to slow down "
        "before amplifying uncertain claims, verify the source, and watch for "
        "emotionally manipulative or weakly supported content."
    ),
    "generic": (
        "You recently saw a short prebunking message reminding you to slow down "
        "before amplifying uncertain claims, verify the source, and watch for "
        "emotionally manipulative or weakly supported content."
    ),
    "fact": (
        "You recently saw a short prebunking message reminding you to check for "
        "verifiable numbers, named institutions, and concrete evidence before "
        "sharing a claim."
    ),
    "logic": (
        "You recently saw a short prebunking message reminding you to look for "
        "contradictions, false causality, and leaps from anecdote to certainty "
        "before reacting to a claim."
    ),
    "technical": (
        "You recently saw a short prebunking message reminding you to be careful "
        "with screenshots, charts, and scientific-sounding language that may be "
        "misused or fabricated."
    ),
    "emotional": (
        "You recently saw a short prebunking message reminding you that fear, "
        "outrage, and urgency can be used manipulatively, so you should pause "
        "and verify before sharing."
    ),
    "counter": (
        "You recently saw a short prebunking message reminding you that if a "
        "claim looks misleading or weakly supported, you can visibly disagree "
        "and warn others not to amplify it."
    ),
}

PROFILE_NOTE_MARKER = "[PREBUNKING MESSAGE EXPOSURE]"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare paper-facing experiment configs from a base YAML."
    )
    parser.add_argument("--base-config", required=True, help="Path to the base YAML.")
    parser.add_argument(
        "--condition",
        required=True,
        choices=["no_defense", "debunking", "prebunking"],
        help="Experiment condition to materialize.",
    )
    parser.add_argument(
        "--source-csv", required=True, help="Source CSV used for this condition."
    )
    parser.add_argument(
        "--resolved-csv",
        required=True,
        help="Path to the CSV that the generated config should use.",
    )
    parser.add_argument(
        "--output-config", required=True, help="Path to the generated YAML config."
    )
    parser.add_argument("--db-path", required=True, help="SQLite DB path for the run.")
    parser.add_argument("--num-agents", type=int, required=True, help="Agent count.")
    parser.add_argument(
        "--num-timesteps",
        type=int,
        default=None,
        help="Override the timestep count from the base config.",
    )
    parser.add_argument(
        "--model-random-seed",
        type=int,
        default=None,
        help="Override the model random seed from the base config.",
    )
    parser.add_argument(
        "--debunking-timestep",
        type=int,
        default=5,
        help="Debunking insertion step for the debunking condition.",
    )
    parser.add_argument(
        "--debunking-threshold",
        type=float,
        default=0.5,
        help="Debunking intervention threshold.",
    )
    parser.add_argument(
        "--debunking-coverage",
        type=float,
        default=None,
        help=(
            "Explicit share of bad-actor posts that receive reactive debunking. "
            "Defaults to the debunking threshold for backward compatibility."
        ),
    )
    parser.add_argument(
        "--prebunking-variant",
        choices=["generic", "fact", "logic", "technical", "emotional", "counter"],
        default="generic",
        help="Prebunking content variant for prebunking experiments.",
    )
    parser.add_argument(
        "--prebunking-delivery",
        choices=["role_rewrite", "message_exposure"],
        default="role_rewrite",
        help=(
            "How prebunking should be materialized: rewrite the benign user role "
            "or keep the original role and append an exposure message."
        ),
    )
    parser.add_argument(
        "--prebunking-user-type",
        default=None,
        help=(
            "Explicit target user_type for role-rewrite prebunking. "
            "Defaults to the value implied by --prebunking-variant."
        ),
    )
    parser.add_argument(
        "--prebunking-coverage",
        type=float,
        default=1.0,
        help="Fraction of benign agents to treat for prebunking-style interventions.",
    )
    parser.add_argument(
        "--treatment-seed",
        type=int,
        default=None,
        help=(
            "Seed used to deterministically choose which benign agents receive "
            "a partial-coverage treatment."
        ),
    )
    parser.add_argument(
        "--prebunking-timestep",
        type=int,
        default=None,
        help=(
            "Inject prebunking during the simulation at this timestep. "
            "When omitted, prebunking is applied from the start via CSV rewrite."
        ),
    )
    parser.add_argument(
        "--recsys-type",
        default=None,
        help="Override the recommender setting in the generated simulation config.",
    )
    parser.add_argument(
        "--reflection",
        action="store_true",
        help="Enable per-agent reflection in the generated simulation config.",
    )
    parser.add_argument(
        "--shared-reflection",
        action="store_true",
        help="Enable shared reflection in the generated simulation config.",
    )
    parser.add_argument(
        "--force-copy-csv",
        action="store_true",
        help="Copy the source CSV even when no type rewrite is needed.",
    )
    return parser.parse_args()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def resolve_prebunking_user_type(
    prebunking_variant: str,
    explicit_user_type: str | None,
) -> str:
    if explicit_user_type:
        return explicit_user_type
    return PREBUNKING_VARIANT_TO_USER_TYPE[prebunking_variant]


def resolve_prebunking_profile_note(prebunking_variant: str) -> str:
    return PREBUNKING_VARIANT_TO_PROFILE_NOTE[prebunking_variant]


def select_treated_row_indexes(
    rows: list[dict[str, str]],
    coverage: float,
    treatment_seed: int | None,
) -> list[int]:
    if not 0.0 <= coverage <= 1.0:
        raise ValueError(f"prebunking coverage must be between 0 and 1, got {coverage}")

    benign_indexes = [
        idx
        for idx, row in enumerate(rows)
        if "good" in row.get("user_type", "") and "bad" not in row.get("user_type", "")
    ]
    if not benign_indexes or coverage <= 0.0:
        return []
    if coverage >= 1.0:
        return benign_indexes

    treated_count = int(round(len(benign_indexes) * coverage))
    treated_count = max(1, min(len(benign_indexes), treated_count))
    rng = random.Random(0 if treatment_seed is None else treatment_seed)
    return sorted(rng.sample(benign_indexes, treated_count))


def append_profile_note(row: dict[str, str], note: str) -> None:
    existing = row.get("user_char", "") or ""
    tagged_note = f"{PROFILE_NOTE_MARKER} {note}"
    if tagged_note in existing:
        return
    row["user_char"] = f"{existing}\n\n{tagged_note}".strip()


def materialize_csv(
    source_csv: Path,
    resolved_csv: Path,
    condition: str,
    force_copy_csv: bool,
    prebunking_variant: str,
    prebunking_delivery: str,
    prebunking_user_type: str | None,
    prebunking_coverage: float,
    prebunking_timestep: int | None,
    treatment_seed: int | None,
) -> Path:
    apply_prebunking_from_start = (
        condition == "prebunking"
        and (prebunking_timestep is None or prebunking_timestep <= 0)
    )

    if not apply_prebunking_from_start and not force_copy_csv:
        return source_csv.resolve()

    ensure_parent(resolved_csv)
    with source_csv.open("r", encoding="utf-8", newline="") as src:
        reader = csv.DictReader(src)
        rows = list(reader)
        fieldnames = reader.fieldnames

    if fieldnames is None:
        raise ValueError(f"CSV has no header: {source_csv}")

    if apply_prebunking_from_start:
        treated_indexes = select_treated_row_indexes(
            rows=rows,
            coverage=prebunking_coverage,
            treatment_seed=treatment_seed,
        )
        if prebunking_delivery == "role_rewrite":
            target_user_type = resolve_prebunking_user_type(
                prebunking_variant=prebunking_variant,
                explicit_user_type=prebunking_user_type,
            )
            for idx in treated_indexes:
                rows[idx]["user_type"] = target_user_type
        else:
            profile_note = resolve_prebunking_profile_note(prebunking_variant)
            for idx in treated_indexes:
                append_profile_note(rows[idx], profile_note)

    with resolved_csv.open("w", encoding="utf-8", newline="") as dst:
        writer = csv.DictWriter(dst, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return resolved_csv.resolve()


def build_config(
    base_config: dict,
    condition: str,
    resolved_csv: Path,
    db_path: Path,
    num_agents: int,
    num_timesteps: int | None,
    model_random_seed: int | None,
    debunking_timestep: int,
    debunking_threshold: float,
    debunking_coverage: float | None,
    prebunking_variant: str,
    prebunking_delivery: str,
    prebunking_user_type: str | None,
    prebunking_coverage: float,
    prebunking_timestep: int | None,
    treatment_seed: int | None,
    recsys_type: str | None,
    reflection: bool,
    shared_reflection: bool,
) -> dict:
    cfg = deepcopy(base_config)
    cfg.setdefault("data", {})
    cfg.setdefault("simulation", {})
    cfg.setdefault("model", {})

    cfg["data"]["csv_path"] = str(resolved_csv.resolve())
    cfg["data"]["db_path"] = str(db_path.resolve())
    cfg["model"]["num_agents"] = num_agents
    for model_cfg in cfg["model"].get("cfgs", []):
        model_cfg["num"] = num_agents
    if num_timesteps is not None:
        cfg["simulation"]["num_timesteps"] = num_timesteps
    if model_random_seed is not None:
        cfg["model"]["model_random_seed"] = model_random_seed
    if recsys_type is not None:
        cfg["simulation"]["recsys_type"] = recsys_type
    if reflection:
        cfg["simulation"]["reflection"] = True
    if shared_reflection:
        cfg["simulation"]["shared_reflection"] = True

    if condition == "debunking":
        resolved_debunking_coverage = (
            debunking_threshold if debunking_coverage is None else debunking_coverage
        )
        if not 0.0 <= resolved_debunking_coverage <= 1.0:
            raise ValueError(
                "debunking coverage must be between 0 and 1, "
                f"got {resolved_debunking_coverage}"
            )
        cfg["defense"] = {
            "strategy": "debunking",
            "timestep": debunking_timestep,
            "threshold": debunking_threshold,
            "coverage": resolved_debunking_coverage,
        }
    elif condition == "prebunking" and prebunking_timestep is not None and prebunking_timestep > 0:
        cfg["defense"] = {
            "strategy": "prebunking",
            "timestep": prebunking_timestep,
            "variant": prebunking_variant,
            "delivery": prebunking_delivery,
            "coverage": prebunking_coverage,
        }
        if prebunking_user_type is not None:
            cfg["defense"]["target_user_type"] = prebunking_user_type
        if treatment_seed is not None:
            cfg["defense"]["treatment_seed"] = treatment_seed
    else:
        cfg.pop("defense", None)

    return cfg


def main() -> None:
    args = parse_args()

    base_config_path = Path(args.base_config).resolve()
    source_csv = Path(args.source_csv).resolve()
    resolved_csv = Path(args.resolved_csv).resolve()
    output_config = Path(args.output_config).resolve()
    db_path = Path(args.db_path).resolve()

    if not base_config_path.exists():
        raise FileNotFoundError(base_config_path)
    if not source_csv.exists():
        raise FileNotFoundError(source_csv)

    with base_config_path.open("r", encoding="utf-8") as fh:
        base_cfg = safe_load(fh)

    treatment_seed = (
        args.treatment_seed
        if args.treatment_seed is not None
        else args.model_random_seed
    )
    resolved_csv = materialize_csv(
        source_csv=source_csv,
        resolved_csv=resolved_csv,
        condition=args.condition,
        force_copy_csv=args.force_copy_csv,
        prebunking_variant=args.prebunking_variant,
        prebunking_delivery=args.prebunking_delivery,
        prebunking_user_type=args.prebunking_user_type,
        prebunking_coverage=args.prebunking_coverage,
        prebunking_timestep=args.prebunking_timestep,
        treatment_seed=treatment_seed,
    )
    ensure_parent(output_config)
    ensure_parent(db_path)

    cfg = build_config(
        base_config=base_cfg,
        condition=args.condition,
        resolved_csv=resolved_csv,
        db_path=db_path,
        num_agents=args.num_agents,
        num_timesteps=args.num_timesteps,
        model_random_seed=args.model_random_seed,
        debunking_timestep=args.debunking_timestep,
        debunking_threshold=args.debunking_threshold,
        debunking_coverage=args.debunking_coverage,
        prebunking_variant=args.prebunking_variant,
        prebunking_delivery=args.prebunking_delivery,
        prebunking_user_type=args.prebunking_user_type,
        prebunking_coverage=args.prebunking_coverage,
        prebunking_timestep=args.prebunking_timestep,
        treatment_seed=treatment_seed,
        recsys_type=args.recsys_type,
        reflection=args.reflection,
        shared_reflection=args.shared_reflection,
    )

    with output_config.open("w", encoding="utf-8") as fh:
        safe_dump(cfg, fh, sort_keys=False)

    print(
        json.dumps(
            {
                "condition": args.condition,
                "base_config": str(base_config_path),
                "source_csv": str(source_csv),
                "resolved_csv": str(resolved_csv),
                "output_config": str(output_config),
                "db_path": str(db_path),
                "num_agents": args.num_agents,
                "num_timesteps": cfg.get("simulation", {}).get("num_timesteps"),
                "model_random_seed": cfg.get("model", {}).get("model_random_seed"),
                "recsys_type": cfg.get("simulation", {}).get("recsys_type"),
                "debunking_timestep": args.debunking_timestep,
                "debunking_threshold": args.debunking_threshold,
                "debunking_coverage": cfg.get("defense", {}).get("coverage"),
                "prebunking_variant": args.prebunking_variant,
                "prebunking_delivery": args.prebunking_delivery,
                "prebunking_user_type": args.prebunking_user_type,
                "prebunking_coverage": args.prebunking_coverage,
                "prebunking_timestep": args.prebunking_timestep,
                "treatment_seed": treatment_seed,
                "reflection": cfg.get("simulation", {}).get("reflection", False),
                "shared_reflection": cfg.get("simulation", {}).get(
                    "shared_reflection", False
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
