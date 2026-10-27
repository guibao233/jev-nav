#!/usr/bin/env bash
# Three fixed routes x three depth inputs, using one selected Decisions model.
# Usage: bash scripts/run_model_ablation.sh openai [batch-id] [--dry-run]
set -euo pipefail
nav_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$nav_root"
nav_model="${1:-openai}"
nav_batch="${2:-$(date +%Y%m%d-%H%M%S)}"
nav_dry_run=false
if [[ "${3:-}" == --dry-run ]]; then nav_dry_run=true; fi
if (( $# > 3 )) || [[ -n "${3:-}" && "${3:-}" != --dry-run ]]; then
  echo 'Usage: bash scripts/run_model_ablation.sh {openai|jev|onejev|omnijev} [batch-id] [--dry-run]' >&2
  exit 2
fi
case "$nav_model" in
  openai) nav_prefix=openai-decisions ;;
  jev) nav_prefix=jev ;;
  onejev) nav_prefix=onejev-local ;;
  omnijev) nav_prefix=omnijev-local ;;
  *) echo 'Model must be openai, jev, onejev or omnijev.' >&2; exit 2 ;;
esac
if [[ ! "$nav_batch" =~ ^[[:alnum:]][[:alnum:]_.-]*$ ]]; then
  echo 'Batch ID must contain only letters, digits, dot, dash, or underscore.' >&2; exit 2
fi
nav_python="${NAV_PYTHON:-python}"
nav_config="${NAV_CONFIG:-config.single-gpu.json}"
nav_rgb="${NAV_RGB:-gs}"
nav_rgb_input="${NAV_RGB_INPUT:-none}"
if [[ "$nav_model" == omnijev ]]; then nav_rgb_input="${NAV_RGB_INPUT:-target_marked}"; fi
if [[ ( "$nav_model" == onejev || "$nav_model" == omnijev ) && -z "${CUDA_VISIBLE_DEVICES:-}" ]]; then
  echo "Set CUDA_VISIBLE_DEVICES explicitly to your allocated rendering GPU." >&2; exit 2
fi
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-7}"
case "$nav_rgb" in gs|mesh|none) ;; *) echo 'NAV_RGB must be gs, mesh, or none.' >&2; exit 2 ;; esac
case "$nav_rgb_input" in
  none) ;;
  target_marked)
    [[ ( "$nav_model" == openai || "$nav_model" == onejev || "$nav_model" == omnijev ) && "$nav_rgb" != none ]] || { echo 'RGB input requires openai/onejev/omnijev and NAV_RGB=gs or mesh.' >&2; exit 2; }
    nav_prefix="${nav_prefix}-rgbtarget" ;;
  *) echo 'NAV_RGB_INPUT must be none or target_marked.' >&2; exit 2 ;;
esac
if [[ "$nav_model" == omnijev && "$nav_rgb_input" != target_marked ]]; then
  echo 'OmniJev v1.1 requires target_marked RGB input.' >&2; exit 2
fi
read -r -a nav_routes <<< "${ROUTES:-simple complex extended}"
read -r -a nav_modes <<< "${MODES:-numeric semantic none}"
[[ -f "$nav_config" ]] || { echo "Missing config: $nav_config" >&2; exit 2; }

build_command() {
  local route="$1" mode="$2" task episode budget depth_input=mesh depth_format="$2"
  case "$route" in
    simple) task=tasks/debug-10.json; episode=episode-000; budget=100 ;;
    complex) task=tasks/challenge-clearance-aligned-20260930-01/tasks.json; episode=turn-000; budget=250 ;;
    extended) task=tasks/extended-clearance-aligned-20261008-01/tasks.json; episode=extended-000; budget=500 ;;
    *) echo "Unknown route: $route" >&2; exit 2 ;;
  esac
  case "$mode" in
    numeric|semantic) ;;
    none) depth_input=none; depth_format=numeric ;;
    *) echo "Unknown input: $mode" >&2; exit 2 ;;
  esac
  [[ -f "$task" ]] || { echo "Missing task file: $task" >&2; exit 2; }
  nav_out="runs/${nav_prefix}-${route}-rgb${nav_rgb}-${mode}-${nav_batch}"
  nav_cmd=("$nav_python" run.py --config "$nav_config" run
    --tasks "$task" --episode "$episode" --out "$nav_out"
    --rgb "$nav_rgb" --max-steps "$budget" --decision-model "$nav_model"
    --depth-input "$depth_input" --depth-format "$depth_format")
  if [[ "$nav_rgb_input" != none ]]; then nav_cmd+=(--rgb-input "$nav_rgb_input"); fi
  if [[ "$nav_model" == onejev ]]; then
    nav_cmd+=(--onejev-url "${ONEJEV_BASE_URL:-http://127.0.0.1:8011}" --onejev-timeout-s "${ONEJEV_TIMEOUT_S:-30}")
  fi
  if [[ "$nav_model" == omnijev ]]; then
    nav_cmd+=(--omnijev-url "${OMNIJEV_BASE_URL:-http://127.0.0.1:8012}" --omnijev-timeout-s "${OMNIJEV_TIMEOUT_S:-60}")
  fi
}

# Check every output before starting the first paid request.
for nav_route in "${nav_routes[@]}"; do
  for nav_mode in "${nav_modes[@]}"; do
    build_command "$nav_route" "$nav_mode"
    if [[ -e "$nav_out" || -e "$nav_out.console.log" ]]; then
      echo "Output already exists; choose a new batch ID: $nav_out" >&2; exit 2
    fi
  done
done
if ! "$nav_dry_run"; then
  [[ "$nav_model" == onejev || "$nav_model" == omnijev || -n "${OPENROUTER_API_KEY:-}" ]] || { echo 'Configure OPENROUTER_API_KEY first.' >&2; exit 2; }
  mkdir -p runs
fi
for nav_route in "${nav_routes[@]}"; do
  for nav_mode in "${nav_modes[@]}"; do
    build_command "$nav_route" "$nav_mode"
    printf 'CUDA_VISIBLE_DEVICES=%q ' "$CUDA_VISIBLE_DEVICES"
    printf '%q ' "${nav_cmd[@]}"
    printf '\n'
    if ! "$nav_dry_run"; then
      "${nav_cmd[@]}" 2>&1 | tee "$nav_out.console.log"
    fi
  done
done
