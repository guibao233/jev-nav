# 在 habitat-gs 环境、jev_nav 目录运行。每条路线依次跑 numeric 和 semantic。
# 如果输出目录已存在，请改末尾编号；不会覆盖旧实验。

# 简单路线：原 debug episode-000，最短距离约 4.20 m，100 步预算。
for format in numeric semantic; do
  CUDA_VISIBLE_DEVICES=7 python run.py --config config.single-gpu.json run \
    --tasks tasks/debug-10.json --episode episode-000 \
    --out "runs/jev-simple-${format}-20261008-01" \
    --rgb mesh --max-steps 100 --depth-input mesh --depth-format "$format"
done

# 复杂路线：居中 + 初始身体朝向对齐的 turn-000，250 步预算。
for format in numeric semantic; do
  CUDA_VISIBLE_DEVICES=7 python run.py --config config.single-gpu.json run \
    --tasks tasks/challenge-clearance-aligned-20260930-01/tasks.json --episode turn-000 \
    --out "runs/jev-complex-${format}-20261008-01" \
    --rgb mesh --max-steps 250 --depth-input mesh --depth-format "$format"
done
