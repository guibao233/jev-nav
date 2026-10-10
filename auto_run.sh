cd /share/guiyuanze/code/habitat-gs/jev_nav

for format in numeric semantic; do
  CUDA_VISIBLE_DEVICES=7 python run.py --config config.single-gpu.json run \
    --tasks tasks/debug-10.json --episode episode-000 \
    --out "runs/jev-simple-rgbgs-${format}-20261008-01" \
    --rgb gs --max-steps 100 \
    --depth-input mesh --depth-format "$format"
done

for format in numeric semantic; do
  CUDA_VISIBLE_DEVICES=7 python run.py --config config.single-gpu.json run \
    --tasks tasks/challenge-clearance-aligned-20260930-01/tasks.json \
    --episode turn-000 \
    --out "runs/jev-complex-rgbgs-${format}-20261008-01" \
    --rgb gs --max-steps 250 \
    --depth-input mesh --depth-format "$format"
done