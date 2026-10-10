#!/usr/bin/env bash
# Explicit local deployment only: never download, install, choose GPU or call cloud.
set -euo pipefail
nav_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "${1:-}" == --help ]]; then
  echo 'Usage: MODEL_GPU=<physical-card> [ONEJEV_PORT=8011] bash scripts/serve_onejev.sh'
  exit 0
fi
if (( $# )); then echo 'Only --help is accepted.' >&2; exit 2; fi
: "${MODEL_GPU:?Set MODEL_GPU to your allocated physical GPU index or UUID}"
[[ "$MODEL_GPU" =~ ^[0-9]+$ || "$MODEL_GPU" =~ ^GPU-[[:xdigit:]-]+$ ]] || { echo 'MODEL_GPU must identify one physical GPU.' >&2; exit 2; }
nav_port="${ONEJEV_PORT:-8011}"
[[ "$nav_port" =~ ^[0-9]+$ ]] && (( nav_port>=1 && nav_port<=65535 )) || { echo 'Invalid ONEJEV_PORT.' >&2; exit 2; }
cd "$nav_root"
nav_deploy="$nav_root/local_models/onejev-4b"
nav_python="$nav_deploy/env/bin/python"
[[ -x "$nav_python" ]] || { echo 'OneJev environment is missing.' >&2; exit 2; }
export CUDA_VISIBLE_DEVICES="$MODEL_GPU"
export HF_HOME="$nav_deploy/cache/huggingface"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 QEV_DEBIAS=1 PYTHONUNBUFFERED=1
"$nav_python" "$nav_root/scripts/check_onejev_deployment.py" --port "$nav_port"
nav_log="$nav_deploy/logs/service-$(date +%Y%m%d-%H%M%S)-$$.log"
echo "Service: http://127.0.0.1:$nav_port ; log: $nav_log"
"$nav_deploy/env/bin/qev" serve \
  --model "$nav_deploy/weights" --name OmniJev/OneJev-4B \
  --device cuda:0 --dtype bfloat16 --head-dtype float32 \
  --host 127.0.0.1 --port "$nav_port" \
  --no-cuda-graphs --no-gpu-preprocess \
  --max-branch-tokens 8192 --max-request-tokens 8192 2>&1 | tee "$nav_log"
