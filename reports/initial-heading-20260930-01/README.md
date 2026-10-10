# 初始朝向对齐：实现与验证（2026-09-30）

按本轮确认，只实现“初始朝向对准第一个局部目标”，从既有居中路线生成独立任务。没有加入运行中视野约束、自动转向、提示词改写或动作屏蔽。尚未运行真实 Jev 实验。

## 实现

[prepare_initial_heading.py](../../prepare_initial_heading.py) 调用全新的 `RoutePreview`，与运行器初始化后的首次 `state()` 使用相同参数和拐角规则，获取 yaw=0 时首目标的 bearing 作为世界 yaw，并归一化至 [-180°,180°)。采用已有 bearing 字段的 0.01° 精度，转后重新核对 bearing≈0°、forward>0，不复制另一套目标选择规则。起终点、pitch、path、shortest_path、geodesic_m 和全部其他原字段保持，仅修改 yaw_deg，新增初始对齐记录及来源/源码哈希。

现有环境 reset 本就读取任务 yaw，因此 run.py/core.py/environment.py/jev.py 无需修改。旧的居中生成来源字段保留，新来源记录使用 initial_heading_source_tasks，避免混淆规划来源与朝向变体。旧 config_at_generation 仍是原任务生成配置，新的目标选择参数记录在 task.initial_heading.selection_config；运行若改变这些参数需重新生成。

不需要 GPU 或 API key，不安装依赖。省略 --episode 可处理全部，重复指定可选择多条，已有输出目录会在读取来源/加载配置前拒绝覆盖。

## 本次变体

[任务文件](../../tasks/challenge-clearance-aligned-20260930-01/tasks.json) 从 tasks/challenge-clearance-20260929-01/tasks.json 的 turn-000 派生：

| 项目 | 原居中任务 | 对齐任务 |
|---|---:|---:|
| 初始 yaw | 112.704310° | −90.390000° |
| 初始局部目标方位 | +156.90° | 0.00° |
| 初始局部目标距离 | 0.708 m | 0.708 m |
| 参考路径长度 | 11.710970 m | 11.710970 m |
| 原最短距离基准 | 9.797690 m | 9.797690 m |

这是一种较容易的初始条件，不能与随机朝向任务合并统计为相同分布。只保证初始化时局部目标水平方向对齐；不保证地面点落在相机画面内、无视觉遮挡或全程可见。初始化不消耗动作预算，转弯、偏离路线和脱困仍由原闭环处理。

## 验证

- [63 项测试输出](tests.txt)，新增 6 项用于朝向转换、拐角/短路线、来源和覆盖保护，原 57 项通过。
- [独立验证结果](verification.json) / [验证脚本](verify.py)：原字段只变化 yaw；全 12 条原 challenge 路线可生成首目标对齐；确定性重生成、来源哈希与 113 个受保护文件检查通过。
- [生成控制台](generation.txt)、[受保护文件原哈希](protected-before.json)、[改动](implementation.patch)。
- [实际 mesh 冒烟回放](../../runs/smoke-initial-heading-20260930-01/index.html) / [控制台](smoke.txt) / [进程记录](smoke-process.json)：CUDA_VISIBLE_DEVICES=7、内部 gpu_id=0，mesh 初始化约 0.9 s；实际姿态与请求目标一致。两步预设动作 move_forward,stop，前进 0.25 m、0 碰撞、0 无效，预期 early_stop，退出码 0。
- 冒烟子进程移除了 API 密钥，provider=scripted_smoke，不是 Jev 导航结果。

## 用户复测

```bash
CUDA_VISIBLE_DEVICES=7 python run.py --config config.single-gpu.json run \
  --tasks tasks/challenge-clearance-aligned-20260930-01/tasks.json --episode turn-000 \
  --out runs/jev-challenge-turn-000-clearance-aligned-01 --rgb gs --max-steps 250
python visualize.py --run runs/jev-challenge-turn-000-clearance-aligned-01 --serve --port 8765
```

显存紧张可用 --rgb mesh。与原居中路线任务保持相同动作预算，重点比较开局转向、转角附近停滞和最终到达；不把居中路线和朝向的改变混为一个因素。

复用工具：

```bash
python prepare_initial_heading.py --config config.single-gpu.json \
  --tasks tasks/challenge-clearance-20260929-01/tasks.json --episode turn-000 \
  --out tasks/my-aligned-variant
```
