#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUEST_ROOT="${QUEST_ROOT:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
MAIN_SUMMARY="${MAIN_SUMMARY:-${QUEST_ROOT}/artifacts/experiment/paper_runs/main_500_multiseed/summary/main_500_multiseed_summary.json}"
VARIANT_SUMMARY="${VARIANT_SUMMARY:-${QUEST_ROOT}/artifacts/experiment/paper_runs/prebunking_variant_multiseed/summary/main_500_prebunking_variant_multiseed_summary.json}"
VARIANT_PIPELINE="${VARIANT_PIPELINE:-${QUEST_ROOT}/experiments/paper_runs/run_prebunking_variant_multiseed_pipeline.sh}"
POLL_SECONDS="${POLL_SECONDS:-120}"

timestamp() {
  date +"%Y-%m-%d %H:%M:%S"
}

echo "[$(timestamp)] waiting for main multi-seed summary at ${MAIN_SUMMARY}"

while [[ ! -s "${MAIN_SUMMARY}" ]]; do
  sleep "${POLL_SECONDS}"
done

if pgrep -f "bash ${VARIANT_PIPELINE}" >/dev/null 2>&1; then
  echo "[$(timestamp)] variant pipeline is already running; nothing to do"
  exit 0
fi

if [[ -s "${VARIANT_SUMMARY}" ]]; then
  echo "[$(timestamp)] variant summary already exists at ${VARIANT_SUMMARY}; nothing to do"
  exit 0
fi

echo "[$(timestamp)] main summary detected; launching variant pipeline"
bash "${VARIANT_PIPELINE}"
