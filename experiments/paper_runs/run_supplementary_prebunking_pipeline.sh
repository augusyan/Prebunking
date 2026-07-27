#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUEST_ROOT="${QUEST_ROOT:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
REPO_ROOT="${REPO_ROOT:-${QUEST_ROOT}}"
RUN_ROOT="${RUN_ROOT:-${QUEST_ROOT}/artifacts/experiment/paper_runs/supplementary_prebunking}"
BASE_CONFIG="${BASE_CONFIG:-${REPO_ROOT}/scripts/twitter_simulation/align_with_real_world/gpt_example.yaml}"
PREP_SCRIPT="${PREP_SCRIPT:-${REPO_ROOT}/scripts/twitter_simulation/align_with_real_world/prepare_paper_experiment.py}"
ANALYZE_SCRIPT="${ANALYZE_SCRIPT:-${REPO_ROOT}/scripts/twitter_simulation/align_with_real_world/analyze_paper_metrics.py}"
SIM_SCRIPT="${SIM_SCRIPT:-${REPO_ROOT}/scripts/twitter_simulation/align_with_real_world/twitter_simulation_large.py}"
SOURCE_CSV="${SOURCE_CSV:-${REPO_ROOT}/data/our_twitter_sim/test_500_good_bad_random_bernoulli_.csv}"
RESULTS_DIR="${RESULTS_DIR:-${REPO_ROOT}/results}"
PYTHON_PREFIX=(conda run --no-capture-output -n mac python)

NUM_AGENTS="${NUM_AGENTS:-500}"
NUM_TIMESTEPS="${NUM_TIMESTEPS:-10}"
RUN_TIMING_SWEEP="${RUN_TIMING_SWEEP:-1}"
RUN_CONTENT_SWEEP="${RUN_CONTENT_SWEEP:-1}"
RUN_RANDOM_ABLATION="${RUN_RANDOM_ABLATION:-1}"
TIMING_STEPS="${TIMING_STEPS:-1 3 6}"
CONTENT_VARIANTS="${CONTENT_VARIANTS:-fact logic technical emotional}"

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

prepare_case() {
  local label="$1"
  local condition="$2"
  local variant="$3"
  local timestep="$4"
  local recsys_type="$5"
  local resolved_csv="${RUN_ROOT}/csv/${label}.csv"
  local output_config="${RUN_ROOT}/configs/${label}.yaml"
  local db_path="${RUN_ROOT}/db/${label}.db"

  archive_if_exists "${resolved_csv}"
  archive_if_exists "${output_config}"
  archive_if_exists "${db_path}"
  archive_if_exists "${RUN_ROOT}/metrics/${label}_metrics.json"
  archive_if_exists "${RUN_ROOT}/metrics/${label}_metrics.md"

  local prep_cmd=(
    "${PYTHON_PREFIX[@]}" "${PREP_SCRIPT}"
    --base-config "${BASE_CONFIG}"
    --condition "${condition}"
    --source-csv "${SOURCE_CSV}"
    --resolved-csv "${resolved_csv}"
    --output-config "${output_config}"
    --db-path "${db_path}"
    --num-agents "${NUM_AGENTS}"
    --num-timesteps "${NUM_TIMESTEPS}"
    --force-copy-csv
  )

  if [[ "${condition}" == "prebunking" ]]; then
    prep_cmd+=(--prebunking-variant "${variant}")
    if [[ -n "${timestep}" ]]; then
      prep_cmd+=(--prebunking-timestep "${timestep}")
    fi
  fi

  if [[ -n "${recsys_type}" ]]; then
    prep_cmd+=(--recsys-type "${recsys_type}")
  fi

  echo "[$(timestamp)] preparing ${label}"
  "${prep_cmd[@]}"
}

run_case() {
  local label="$1"
  local condition="$2"
  local variant="$3"
  local timestep="$4"
  local recsys_type="$5"
  local resolved_csv="${RUN_ROOT}/csv/${label}.csv"
  local output_config="${RUN_ROOT}/configs/${label}.yaml"
  local db_path="${RUN_ROOT}/db/${label}.db"
  local stats_dir="${RUN_ROOT}/stats_inputs/${label}"
  local latest_npy
  local source_results_dir
  local candidate_dir

  mkdir -p "${stats_dir}"
  prepare_case "${label}" "${condition}" "${variant}" "${timestep}" "${recsys_type}"

  echo "[$(timestamp)] running ${label}"
  (
    cd "${REPO_ROOT}"
    "${PYTHON_PREFIX[@]}" "${SIM_SCRIPT}" --config_path "${output_config}"
  )

  latest_npy=""
  source_results_dir=""
  for candidate_dir in "${RESULTS_DIR}" "${REPO_ROOT}/results"; do
    [[ -d "${candidate_dir}" ]] || continue
    latest_npy="$(ls -1t "${candidate_dir}/post_stats_data_${label}_"*.npy 2>/dev/null | head -n 1 || true)"
    if [[ -n "${latest_npy}" ]]; then
      source_results_dir="${candidate_dir}"
      break
    fi
  done
  if [[ -z "${latest_npy}" ]]; then
    echo "No post_stats_data file found for ${label}" >&2
    exit 1
  fi

  if [[ "${source_results_dir}" != "${RESULTS_DIR}" ]]; then
    echo "[$(timestamp)] found ${label} post_stats_data under ${source_results_dir}; copying into ${RESULTS_DIR}"
    cp "${latest_npy}" "${RESULTS_DIR}/"
  fi

  cp "${latest_npy}" "${stats_dir}/"

  echo "[$(timestamp)] analyzing ${label}"
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

echo "[$(timestamp)] supplementary prebunking pipeline start"
hydrate_openai_env

if [[ "${RUN_TIMING_SWEEP}" == "1" ]]; then
  read -r -a timing_steps_arr <<< "${TIMING_STEPS}"
  for step in "${timing_steps_arr[@]}"; do
    run_case "supp_prebunking_t${step}" "prebunking" "generic" "${step}" ""
  done
fi

if [[ "${RUN_CONTENT_SWEEP}" == "1" ]]; then
  read -r -a content_variants_arr <<< "${CONTENT_VARIANTS}"
  for variant in "${content_variants_arr[@]}"; do
    run_case "supp_prebunking_${variant}" "prebunking" "${variant}" "" ""
  done
fi

if [[ "${RUN_RANDOM_ABLATION}" == "1" ]]; then
  run_case "supp_prebunking_random_feed" "prebunking" "generic" "" "random"
fi

echo "[$(timestamp)] supplementary prebunking pipeline completed"
