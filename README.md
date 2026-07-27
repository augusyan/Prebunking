# Anonymous Paper Artifact

This repository packages the code, data inputs, and experiment summaries used for the paper. It is prepared for anonymous peer review and intentionally omits author names, affiliations, contact details, private infrastructure addresses, local filesystem paths, and manuscript source files.

> **Content warning:** This research artifact contains false medical and political claims as labeled benchmark inputs, plus simulated malicious-agent prompts. They are included to evaluate misinformation defenses, are not endorsed as true, and must not be used as medical advice or deployed against real users.

## What Is Included

- `oasis/`, `generator/`: the core multi-agent simulation framework used by the paper.
- `scripts/twitter_simulation/align_with_real_world/`: the paper-facing simulation and analysis entry points.
- `experiments/paper_runs/`: orchestration scripts for the main comparison, multiseed runs, timing studies, ablations, and annotation utilities.
- `data/`: lightweight input data required by the paper pipelines, including the 500-agent seed CSV and tweet pools.
- `artifacts/experiment/paper_runs/`: curated experiment outputs that stay small enough for Git tracking, such as configs, CSV inputs, JSON metrics, Markdown summaries, and LaTeX tables.
- `artifacts/human_annotation/blind_comment_zh/`: public annotation sheets and judged outputs used by the blind-comment analysis.
- `docs/raw_artifacts_manifest.csv`: an inventory of the heavier raw `.db` and `.npy` artifacts intentionally excluded from the Git-tracked export.

## Why Heavy Raw Files Are Excluded

The original experiment workspace contains many SQLite databases and NumPy dumps. They are useful for archival and release attachments, but they make a GitHub repository unnecessarily heavy and harder to browse.

This export keeps the repository readable and pushable by tracking:

- runnable code
- lightweight experiment inputs
- metrics and summary tables

Use `docs/raw_artifacts_manifest.csv` when you want to prepare a separate release bundle or Git LFS package for the omitted raw artifacts.

## Quick Start

```bash
poetry install
bash experiments/paper_runs/run_main_500_multiseed_pipeline.sh
python experiments/paper_runs/run_blind_comment_judge.py
```

All paper run scripts in `experiments/paper_runs/` use repository-relative paths.

Set `OPENAI_API_KEY` when using OpenAI-hosted models. For a compatible custom endpoint, also set `OPENAI_BASE_URL`. Secrets must be supplied through environment variables and must not be committed to this repository.

## Directory Guide

- `data/our_twitter_sim/`: seed agent CSVs and CSV mutation helpers.
- `data/tweets/`: tweet pools sampled for the misinformation simulations.
- `artifacts/experiment/paper_runs/main_500_multiseed/summary/`: the main multi-seed summaries reported in the paper.
- `artifacts/experiment/paper_runs/prebunking_ablation_multiseed/summary/`: ablation summaries.
- `artifacts/experiment/paper_runs/prebunking_timing_multiseed/summary/`: timing-study summaries.
- `artifacts/experiment/paper_runs/prebunking_variant_multiseed/summary/`: content-variant summaries.

## Data, Ethics, and Responsible Use

- Names and handles in the agent profiles and simulation outputs are synthetic and are not accounts of real participants.
- The tweet pools contain benchmark claim text used to study misinformation defenses. Misinformation examples are research inputs, not factual or medical advice.
- No private social-media profiles, access tokens, API keys, annotator identities, or participant contact details are included.
- Source and citation information for third-party datasets is retained under `data/tweets/`. Users remain responsible for following the source datasets' licenses and platform terms.
- Third-party materials are not relicensed by this repository; see `docs/THIRD_PARTY_NOTICES.md`.
- The code includes an Apache-2.0-licensed OASIS-derived framework. Its upstream copyright and attribution notices are intentionally preserved.
- The malicious-agent prompts are included only to reproduce controlled safety experiments. Do not deploy them against real users or public services.

## Anonymous-Review Checklist

- Do not add author names, affiliations, acknowledgments, personal repository URLs, or non-anonymous issue/commit links during review.
- Create the public review repository from a fresh history under a neutral account or an anonymous-repository service.
- Before each upload, run `python scripts/audit_anonymity.py` from the repository root.
