#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUEST_ROOT="${QUEST_ROOT:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
REPO_ROOT="${REPO_ROOT:-${QUEST_ROOT}}"
RUN_ROOT="${QUEST_ROOT}/artifacts/experiment/paper_runs/main_500"
BASE_CONFIG="${REPO_ROOT}/scripts/twitter_simulation/align_with_real_world/gpt_example.yaml"
PREP_SCRIPT="${REPO_ROOT}/scripts/twitter_simulation/align_with_real_world/prepare_paper_experiment.py"
ANALYZE_SCRIPT="${REPO_ROOT}/scripts/twitter_simulation/align_with_real_world/analyze_paper_metrics.py"
COMPARE_SCRIPT="${REPO_ROOT}/scripts/twitter_simulation/align_with_real_world/build_paper_comparison.py"
SIM_SCRIPT="${REPO_ROOT}/scripts/twitter_simulation/align_with_real_world/twitter_simulation_large.py"
SOURCE_CSV="${REPO_ROOT}/data/our_twitter_sim/test_500_good_bad_random_bernoulli_.csv"
RESULTS_DIR="${REPO_ROOT}/results"
NUM_AGENTS=500
NUM_TIMESTEPS=10
PYTHON_PREFIX=(conda run --no-capture-output -n mac python)
CONDITIONS=(no_defense debunking prebunking)

timestamp() {
  date +"%Y-%m-%d %H:%M:%S"
}

hydrate_openai_env() {
  if [[ -n "${OPENAI_API_KEY:-}" || -n "${GPT_DIRECT_API_KEY:-}" ]]; then
    return 0
  fi

  local pid entry
  while IFS= read -r pid; do
    [[ -r "/proc/${pid}/environ" ]] || continue
    while IFS= read -r entry; do
      case "${entry}" in
        OPENAI_API_KEY=*)
          export OPENAI_API_KEY="${entry#OPENAI_API_KEY=}"
          ;;
        GPT_DIRECT_API_KEY=*)
          export GPT_DIRECT_API_KEY="${entry#GPT_DIRECT_API_KEY=}"
          ;;
        OPENAI_BASE_URL=*)
          export OPENAI_BASE_URL="${entry#OPENAI_BASE_URL=}"
          ;;
        OPENAI_API_BASE_URL=*)
          export OPENAI_API_BASE_URL="${entry#OPENAI_API_BASE_URL=}"
          ;;
      esac
    done < <(tr '\0' '\n' < "/proc/${pid}/environ")

    if [[ -n "${OPENAI_API_KEY:-}" || -n "${GPT_DIRECT_API_KEY:-}" ]]; then
      break
    fi
  done < <(pgrep -f "python .*twitter_simulation_large.py" || true)

  if [[ -n "${OPENAI_API_KEY:-}" && -z "${GPT_DIRECT_API_KEY:-}" ]]; then
    export GPT_DIRECT_API_KEY="${OPENAI_API_KEY}"
  fi
  if [[ -n "${OPENAI_BASE_URL:-}" && -z "${OPENAI_API_BASE_URL:-}" ]]; then
    export OPENAI_API_BASE_URL="${OPENAI_BASE_URL}"
  fi

  if [[ -z "${OPENAI_API_KEY:-}" && -z "${GPT_DIRECT_API_KEY:-}" ]]; then
    echo "[$(timestamp)] missing OpenAI-compatible API key in the current environment and no reusable running process was found" >&2
    return 1
  fi

  echo "[$(timestamp)] OpenAI-compatible environment detected"
}

archive_if_exists() {
  local path="$1"
  if [[ -e "$path" ]]; then
    mv "$path" "${path}.bak.$(date +%Y%m%d_%H%M%S)"
  fi
}

prepare_condition() {
  local condition="$1"
  local label="main_500_${condition}"
  local resolved_csv="${RUN_ROOT}/csv/${label}.csv"
  local output_config="${RUN_ROOT}/configs/${label}.yaml"
  local db_path="${RUN_ROOT}/db/${label}.db"

  archive_if_exists "${resolved_csv}"
  archive_if_exists "${output_config}"
  archive_if_exists "${db_path}"
  archive_if_exists "${RUN_ROOT}/metrics/${label}_metrics.json"
  archive_if_exists "${RUN_ROOT}/metrics/${label}_metrics.md"

  echo "[$(timestamp)] preparing ${condition}"
  "${PYTHON_PREFIX[@]}" "${PREP_SCRIPT}" \
    --base-config "${BASE_CONFIG}" \
    --condition "${condition}" \
    --source-csv "${SOURCE_CSV}" \
    --resolved-csv "${resolved_csv}" \
    --output-config "${output_config}" \
    --db-path "${db_path}" \
    --num-agents "${NUM_AGENTS}" \
    --num-timesteps "${NUM_TIMESTEPS}" \
    --force-copy-csv
}

run_condition() {
  local condition="$1"
  local label="main_500_${condition}"
  local resolved_csv="${RUN_ROOT}/csv/${label}.csv"
  local output_config="${RUN_ROOT}/configs/${label}.yaml"
  local db_path="${RUN_ROOT}/db/${label}.db"
  local stats_dir="${RUN_ROOT}/stats_inputs/${condition}"
  local latest_npy

  mkdir -p "${stats_dir}"

  echo "[$(timestamp)] running ${condition}"
  (
    cd "${REPO_ROOT}"
    "${PYTHON_PREFIX[@]}" "${SIM_SCRIPT}" --config_path "${output_config}"
  )

  latest_npy="$(ls -1t "${RESULTS_DIR}/post_stats_data_${label}_"*.npy | head -n 1)"
  if [[ -z "${latest_npy}" ]]; then
    echo "No post_stats_data file found for ${label}" >&2
    exit 1
  fi

  cp "${latest_npy}" "${stats_dir}/"

  echo "[$(timestamp)] analyzing ${condition}"
  "${PYTHON_PREFIX[@]}" "${ANALYZE_SCRIPT}" \
    --db-path "${db_path}" \
    --csv-path "${resolved_csv}" \
    --results-dir "${stats_dir}" \
    --output-dir "${RUN_ROOT}/metrics" \
    --label "${label}"
}

mkdir -p \
  "${RUN_ROOT}/configs" \
  "${RUN_ROOT}/csv" \
  "${RUN_ROOT}/db" \
  "${RUN_ROOT}/metrics" \
  "${RUN_ROOT}/stats_inputs" \
  "${RUN_ROOT}/logs" \
  "${RESULTS_DIR}"

echo "[$(timestamp)] main_500 pipeline start"
hydrate_openai_env
for condition in "${CONDITIONS[@]}"; do
  prepare_condition "${condition}"
  run_condition "${condition}"
done

echo "[$(timestamp)] building comparison tables"
"${PYTHON_PREFIX[@]}" "${COMPARE_SCRIPT}" \
  --metrics-dir "${RUN_ROOT}/metrics" \
  --output-dir "${RUN_ROOT}/metrics" \
  --label "main_500" \
  --conditions "${CONDITIONS[@]}"

echo "[$(timestamp)] main_500 pipeline completed"
