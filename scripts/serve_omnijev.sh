#!/usr/bin/env bash
# Only start an explicitly allocated GPU; never install/download or call cloud.
set -euo pipefail
nav_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "${1:-}" == --help ]]; then
  echo 'Usage: MODEL_GPU=<physical-card> [OMNIJEV_PORT=8012] bash scripts/serve_omnijev.sh'
  exit 0
fi
if (( $# )); then echo 'Only --help is accepted.' >&2; exit 2; fi
: "${MODEL_GPU:?Set MODEL_GPU to your allocated physical GPU index or UUID}"
[[ "$MODEL_GPU" =~ ^[0-9]+$ || "$MODEL_GPU" =~ ^GPU-[[:xdigit:]-]+$ ]] || { echo 'MODEL_GPU must identify one physical GPU.' >&2; exit 2; }
nav_port="${OMNIJEV_PORT:-8012}"
[[ "$nav_port" =~ ^[0-9]+$ ]] && (( nav_port>=1 && nav_port<=65535 )) || { echo 'Invalid OMNIJEV_PORT.' >&2; exit 2; }
cd "$nav_root"
nav_deploy="$nav_root/local_models/omnijev-4b"
nav_python="$nav_deploy/env/bin/python"
[[ -x "$nav_python" ]] || { echo 'OmniJev environment is missing.' >&2; exit 2; }
export CUDA_VISIBLE_DEVICES="$MODEL_GPU"
export HF_HOME="$nav_deploy/cache/huggingface"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
export MSO_FLA=0 MSO_BRANCH=2 MSO_STATE_CACHE=1 MSO_ATTN=sdpa
# Upstream requires a nonzero cache. Keep only the current image; no truncation.
"$nav_python" "$nav_root/scripts/check_omnijev_deployment.py" --port "$nav_port"
nav_log="$nav_deploy/logs/service-$(date +%Y%m%d-%H%M%S)-$$.log"
echo "Service: http://127.0.0.1:$nav_port ; log: $nav_log"
"$nav_python" "$nav_root/omnijev_server.py" --deploy "$nav_deploy" --port "$nav_port" 2>&1 | tee "$nav_log"
