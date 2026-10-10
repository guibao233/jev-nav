#!/usr/bin/env bash
set -euo pipefail
cd /data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav
# Run inside habitat-gs with OPENROUTER_API_KEY configured. Three real API evaluations.
for mode in numeric semantic none; do
  depth_input=mesh
  depth_format="$mode"
  if [ "$mode" = none ]; then
    depth_input=none
    depth_format=numeric
  fi
  CUDA_VISIBLE_DEVICES=7 python run.py --config config.single-gpu.json run \
    --tasks tasks/extended-clearance-aligned-20261008-01/tasks.json \
    --episode extended-000 \
    --out "runs/jev-extended-rgbgs-${mode}-20261008-02" \
    --rgb gs --max-steps 500 \
    --depth-input "$depth_input" --depth-format "$depth_format"
done
