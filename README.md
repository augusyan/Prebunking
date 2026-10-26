# Prebunking in Simulated Social Networks

## Anonymous Research Artifact for The Web Conference 2027 (WWW 2027)

This repository accompanies an anonymous research paper submitted to The Web Conference 2027 (WWW 2027). It provides the simulation code, input data, experiment configurations, and collected summaries for reviewing the paper's experiments. Author-identifying information and manuscript source files are intentionally omitted for double-blind review.

The work studies a Web-related research question: how preventive prebunking and reactive debunking affect misinformation propagation and agent responses in a simulated social-media environment. The artifact supports controlled comparisons of no defense, debunking, and prebunking, together with ablations and studies of intervention timing and content. These experiments concern information integrity and intervention design on the social Web. Results describe the configured simulations and do not, by themselves, establish effects on real platform users.

> **Content warning:** This research artifact contains false medical and political claims as labeled benchmark inputs, plus simulated malicious-agent prompts. They are included to evaluate misinformation defenses, are not endorsed as true, and must not be used as medical advice or deployed against real users.

## What Is Included

- `oasis/`, `generator/`: the core multi-agent simulation framework used by the paper.
- `scripts/twitter_simulation/align_with_real_world/`: the paper-facing simulation and analysis entry points.
- `experiments/paper_runs/`: orchestration scripts for the main comparison, multiseed runs, timing studies, ablations, and annotation utilities.
- `data/`: lightweight input data required by the paper pipelines, including the 500-agent seed CSV and tweet pools.
- `artifacts/experiment/paper_runs/`: curated experiment outputs that stay small enough for Git tracking, such as configs, CSV inputs, JSON metrics, Markdown summaries, and LaTeX tables.
- `artifacts/human_annotation/blind_comment_zh/`: public annotation sheets and judged outputs used by the blind-comment analysis.
- `docs/raw_artifacts_manifest.csv`: an inventory of the heavier raw `.db` and `.npy` artifacts intentionally excluded from the Git-tracked export.

## Reviewer Guide and Reproducibility

Start with `artifacts/experiment/paper_runs/main_500_multiseed/summary/main_500_multiseed_summary.md` for the main comparison. The neighboring CSV, JSON, and LaTeX files provide machine-readable summaries and tables. The ablation, timing, and content-variant summary directories are listed below. Reading the bundled summaries requires no API credentials or simulation reruns.

Heavy raw SQLite databases (`.db`) and NumPy dumps (`.npy`) are excluded from this review package; `docs/raw_artifacts_manifest.csv` records the omitted artifacts. The package therefore supports inspection of the included results and aggregation of the included metrics, but analyses that consume raw databases or NumPy dumps require regenerating those files first. The manifest is an inventory, not a download service.

## Environment Setup

Use Python 3.10 or 3.11, Poetry, Conda, and a Bash-compatible shell. The main pipeline currently invokes `conda run --no-capture-output -n mac python`, so its dependencies must be installed into the Conda environment named `mac`.

Run from the repository root, with Poetry installed and available:

```bash
conda create -n mac python=3.10 -y
conda activate mac
poetry install
```

Ensure Poetry uses the active `mac` environment rather than a separate virtual environment, because the pipeline invokes Conda's Python directly. Dependencies and their pinned versions are recorded in `pyproject.toml` and `poetry.lock`.

## Reproduce the Main Experiments

Supply `OPENAI_API_KEY` through your environment before running simulations. For an OpenAI-compatible custom endpoint, also set `OPENAI_BASE_URL`. Never commit credentials. Check the model and simulation settings in `scripts/twitter_simulation/align_with_real_world/gpt_example.yaml` before launching.

```bash
bash experiments/paper_runs/run_main_500_multiseed_pipeline.sh
```

By default, this pipeline runs 500 agents for 10 timesteps, with seeds `42 52 62 72 82`, for `no_defense`, `debunking`, and `prebunking`. It writes configurations, resolved inputs, raw simulation outputs, metrics, and summaries under `artifacts/experiment/paper_runs/main_500_multiseed/`, with intermediate NumPy outputs also written under `results/`. Existing per-run files may be moved to timestamped backups by the pipeline.

Simulation reruns require model API access and may incur charges. Model availability, service behavior, and stochastic generation can affect reproduced values; fixed seeds do not guarantee identical hosted-model responses.

To regenerate aggregate tables from the bundled metrics without model API calls, use Python 3.10 or 3.11:

```bash
python experiments/paper_runs/aggregate_main_500_multiseed.py \
  --metrics-dir artifacts/experiment/paper_runs/main_500_multiseed/metrics \
  --output-dir artifacts/experiment/paper_runs/main_500_multiseed/recomputed_summary \
  --label main_500_multiseed
```

After regenerating the main simulation databases, the separate blind-comment model-judge analysis can be run with:

```bash
python experiments/paper_runs/run_blind_comment_judge.py
```

This analysis also requires API credentials. It is an automated judging step, distinct from the human annotation materials included in the package.

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
