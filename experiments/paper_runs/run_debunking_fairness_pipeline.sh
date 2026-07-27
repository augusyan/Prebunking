#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUEST_ROOT="${QUEST_ROOT:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
REPO_ROOT="${REPO_ROOT:-${QUEST_ROOT}}"
MAIN_RUN_ROOT="${MAIN_RUN_ROOT:-${QUEST_ROOT}/artifacts/experiment/paper_runs/main_500}"
RUN_ROOT="${RUN_ROOT:-${QUEST_ROOT}/artifacts/experiment/paper_runs/debunking_fairness_500}"
BASE_CONFIG="${BASE_CONFIG:-${REPO_ROOT}/scripts/twitter_simulation/align_with_real_world/gpt_example.yaml}"
PREP_SCRIPT="${PREP_SCRIPT:-${REPO_ROOT}/scripts/twitter_simulation/align_with_real_world/prepare_paper_experiment.py}"
ANALYZE_SCRIPT="${ANALYZE_SCRIPT:-${REPO_ROOT}/scripts/twitter_simulation/align_with_real_world/analyze_paper_metrics.py}"
SIM_SCRIPT="${SIM_SCRIPT:-${REPO_ROOT}/scripts/twitter_simulation/align_with_real_world/twitter_simulation_large.py}"
SOURCE_CSV="${SOURCE_CSV:-${REPO_ROOT}/data/our_twitter_sim/test_500_good_bad_random_bernoulli_.csv}"
RESULTS_DIR="${RESULTS_DIR:-${REPO_ROOT}/results}"
PYTHON_PREFIX=(conda run --no-capture-output -n mac python)

NUM_AGENTS="${NUM_AGENTS:-500}"
NUM_TIMESTEPS="${NUM_TIMESTEPS:-10}"
CASE_SPECS="${CASE_SPECS:-debunking_t5_postcov100:5:1.0}"
SUMMARY_CASE_SPECS="${SUMMARY_CASE_SPECS:-${CASE_SPECS}}"

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
  local debunking_timestep="$2"
  local debunking_coverage="$3"
  local resolved_csv="${RUN_ROOT}/csv/${label}.csv"
  local output_config="${RUN_ROOT}/configs/${label}.yaml"
  local db_path="${RUN_ROOT}/db/${label}.db"

  archive_if_exists "${resolved_csv}"
  archive_if_exists "${output_config}"
  archive_if_exists "${db_path}"
  archive_if_exists "${RUN_ROOT}/metrics/${label}_metrics.json"
  archive_if_exists "${RUN_ROOT}/metrics/${label}_metrics.md"

  echo "[$(timestamp)] preparing ${label} (t=${debunking_timestep}, post_coverage=${debunking_coverage})"
  "${PYTHON_PREFIX[@]}" "${PREP_SCRIPT}" \
    --base-config "${BASE_CONFIG}" \
    --condition debunking \
    --source-csv "${SOURCE_CSV}" \
    --resolved-csv "${resolved_csv}" \
    --output-config "${output_config}" \
    --db-path "${db_path}" \
    --num-agents "${NUM_AGENTS}" \
    --num-timesteps "${NUM_TIMESTEPS}" \
    --debunking-timestep "${debunking_timestep}" \
    --debunking-threshold "${debunking_coverage}" \
    --debunking-coverage "${debunking_coverage}" \
    --force-copy-csv
}

run_case() {
  local label="$1"
  local debunking_timestep="$2"
  local debunking_coverage="$3"
  local resolved_csv="${RUN_ROOT}/csv/${label}.csv"
  local output_config="${RUN_ROOT}/configs/${label}.yaml"
  local db_path="${RUN_ROOT}/db/${label}.db"
  local stats_dir="${RUN_ROOT}/stats_inputs/${label}"
  local latest_npy=""
  local candidate_dir

  mkdir -p "${stats_dir}"
  prepare_case "${label}" "${debunking_timestep}" "${debunking_coverage}"

  echo "[$(timestamp)] running ${label}"
  (
    cd "${REPO_ROOT}"
    "${PYTHON_PREFIX[@]}" "${SIM_SCRIPT}" --config_path "${output_config}"
  )

  for candidate_dir in "${RESULTS_DIR}" "${REPO_ROOT}/results"; do
    [[ -d "${candidate_dir}" ]] || continue
    latest_npy="$(ls -1t "${candidate_dir}/post_stats_data_${label}_"*.npy 2>/dev/null | head -n 1 || true)"
    if [[ -n "${latest_npy}" ]]; then
      break
    fi
  done
  if [[ -z "${latest_npy}" ]]; then
    echo "No post_stats_data file found for ${label}" >&2
    exit 1
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

write_summary() {
  local summary_md="${RUN_ROOT}/metrics/debunking_fairness_summary.md"
  local summary_json="${RUN_ROOT}/metrics/debunking_fairness_summary.json"
  local main_debunk_json="${MAIN_RUN_ROOT}/metrics/main_500_debunking_metrics.json"
  local main_prebunk_json="${MAIN_RUN_ROOT}/metrics/main_500_prebunking_metrics.json"

  "${PYTHON_PREFIX[@]}" - "${RUN_ROOT}" "${SUMMARY_CASE_SPECS}" "${main_debunk_json}" "${main_prebunk_json}" "${summary_md}" "${summary_json}" <<'PY'
import json
import sys
from pathlib import Path

run_root = Path(sys.argv[1])
case_specs = [spec for spec in sys.argv[2].split() if spec]
main_debunk_json = Path(sys.argv[3])
main_prebunk_json = Path(sys.argv[4])
summary_md = Path(sys.argv[5])
summary_json = Path(sys.argv[6])


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def row_from_metrics(name: str, metrics: dict) -> dict:
    macro = metrics["macro"]
    micro = metrics["micro"]
    time_series = metrics.get("time_series", {})
    return {
        "condition": name,
        "infection_pct": round(macro["infection_rate_pct"], 4),
        "resistance_pct": round(macro["resistance_rate_pct"], 4),
        "agree_pct": round(micro["stance_comment_pct"]["agree_true"], 4),
        "disagree_pct": round(micro["stance_comment_pct"]["agree_false"], 4),
        "peak_infection_value": float(time_series.get("peak_infection_proxy_value", 0.0)),
        "peak_resistance_value": float(time_series.get("peak_resistance_value", 0.0)),
    }


baseline_debunk = load(main_debunk_json)
baseline_prebunk = load(main_prebunk_json)
rows = [
    row_from_metrics("main_500_debunking", baseline_debunk),
    row_from_metrics("main_500_prebunking", baseline_prebunk),
]

for spec in case_specs:
    label, _, _ = spec.split(":")
    metrics_path = run_root / "metrics" / f"{label}_metrics.json"
    rows.append(row_from_metrics(label, load(metrics_path)))

baseline_infection = rows[0]["infection_pct"]
baseline_prebunk_infection = rows[1]["infection_pct"]
for row in rows[2:]:
    row["delta_vs_main_debunking"] = round(row["infection_pct"] - baseline_infection, 4)
    row["delta_vs_main_prebunking"] = round(row["infection_pct"] - baseline_prebunk_infection, 4)

summary = {
    "baseline_debunking": rows[0],
    "baseline_prebunking": rows[1],
    "fairness_cases": rows[2:],
}
summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

lines = [
    "# debunking_fairness_summary",
    "",
    "## Outcome and stance",
    "| Condition | Infection % | Resistance % | Agree % | Disagree % | Peak Infection Value | Peak Resistance Value | Δ Infection vs main debunking | Δ Infection vs main prebunking |",
    "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
]
for row in rows[:2]:
    lines.append(
        f"| {row['condition']} | {row['infection_pct']:.2f} | {row['resistance_pct']:.2f} | "
        f"{row['agree_pct']:.2f} | {row['disagree_pct']:.2f} | {row['peak_infection_value']:.2f} | "
        f"{row['peak_resistance_value']:.2f} |  |  |"
    )
for row in rows[2:]:
    lines.append(
        f"| {row['condition']} | {row['infection_pct']:.2f} | {row['resistance_pct']:.2f} | "
        f"{row['agree_pct']:.2f} | {row['disagree_pct']:.2f} | {row['peak_infection_value']:.2f} | "
        f"{row['peak_resistance_value']:.2f} | {row['delta_vs_main_debunking']:+.2f} | "
        f"{row['delta_vs_main_prebunking']:+.2f} |"
    )

if rows[2:]:
    best_case = min(rows[2:], key=lambda row: row["infection_pct"])
    lines.extend(
        [
            "",
            "## Takeaway",
            (
                f"- Best strengthened reactive case: {best_case['condition']} with "
                f"{best_case['infection_pct']:.2f}% infection and {best_case['resistance_pct']:.2f}% resistance."
            ),
            (
                f"- Gap vs main prebunking: "
                f"{best_case['infection_pct'] - baseline_prebunk_infection:+.2f} infection points."
            ),
        ]
    )

summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

mkdir -p \
  "${RUN_ROOT}/configs" \
  "${RUN_ROOT}/csv" \
  "${RUN_ROOT}/db" \
  "${RUN_ROOT}/metrics" \
  "${RUN_ROOT}/stats_inputs" \
  "${RUN_ROOT}/logs" \
  "${RESULTS_DIR}"

echo "[$(timestamp)] debunking fairness pipeline start"
hydrate_openai_env

read -r -a case_specs_arr <<< "${CASE_SPECS}"
for spec in "${case_specs_arr[@]}"; do
  IFS=":" read -r label debunking_timestep debunking_coverage <<< "${spec}"
  run_case "${label}" "${debunking_timestep}" "${debunking_coverage}"
done

write_summary
echo "[$(timestamp)] debunking fairness pipeline completed"
