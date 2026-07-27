# Repository Map

## Core Framework

- `oasis/`: simulation engine, agent logic, recommendation system, database layer, and post statistics.
- `generator/`: helper utilities for generator-specific data preparation.

## Paper Pipelines

- `scripts/twitter_simulation/align_with_real_world/`: paper-specific simulation, metric extraction, and comparison builders.
- `experiments/paper_runs/`: shell and Python wrappers that organize the paper's main run, multiseed experiments, and supplementary studies.

## Inputs And Outputs

- `data/`: lightweight source data that is safe to keep in Git.
- `artifacts/experiment/paper_runs/`: lightweight tracked outputs.
- `docs/raw_artifacts_manifest.csv`: omitted raw outputs that should live in release assets or Git LFS instead of normal Git history.
