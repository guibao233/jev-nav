# 居中参考路线实现与验证

已按用户选择的“长度 + 近障碍代价”方案实现独立任务变体，供同起终点对照。新路线更靠可通行区域内部；未运行新的真实 Jev 任务。

## 本轮日志核查

`jev-challenge-turn-000-reassociate-motion-01` 用尽 250 步，最终离终点 1.201 m，累计移动 26.583 m；仅 1 次碰撞，另有 31 次低头超限。第 34–137 步共 104 步无平移，停在首个转角附近，查询其到 NavMesh 边界的额外距离为 0。原最短路径的 7 个中间顶点也位于边界上。

原路径在连续 NavMesh 几何上可达，并不等于穿墙；缺少额外余量会使离散动作跟随更脆弱。居中路线改善参考几何，低头超限等模型行为没有在本次一起修改，不能保证所有失败随之消失。

## 方案与范围

新增 `clearance.py` 和 `prepare_clearance.py`，无需新依赖安装、GPU 或 API key。使用原 NavMesh 的距离查询构造连续代价，8 邻域网格 A* 的边代价为：

`integral(1 + weight * exp(-extra_navmesh_clearance / clearance_scale_m)) ds`

默认 grid_m=0.10、clearance_scale_m=0.20、weight=4、原路线包围盒外扩 2 m。网格边逐段通过原生运动过滤验证，禁止对角穿障碍；起终点用精确坐标连接，不吸附改变任务。代价为软惩罚，窄通道仍可使用，不额外侵蚀 NavMesh。0.20 m 是衰减尺度，并非硬性最小安全距离。

路径简化也检查 NavMesh 直连，替代部分的代价增加最多 1%、采样最低余量下降最多 0.005 m，避免简化后重新贴边。输出 8 个顶点而非逐个网格点，最短段 0.550 m。只支持高度跨度 ≤0.02 m 的平面路线；网格分辨率/搜索范围导致找不到路时明确报错，不悄悄退回原路线。

连续障碍代价场引导路线居中这一思想参考 [Nav2 官方调参说明](https://docs.nav2.org/rolling/configuration_and_development/tuning_guide/)。这里是本模块的独立 CPU 实现，没有引入 ROS/Nav2 运行环境。

## 数据与效果

[新任务](../../tasks/challenge-clearance-20260929-01/tasks.json)、[新旧计划对照图](../../tasks/challenge-clearance-20260929-01/index.html)、[单张 PNG](../../tasks/challenge-clearance-20260929-01/maps/turn-000.png)。蓝线是新参考，紫虚线是原最短路径。

| 指标 | 原最短路径 | 新参考路径 |
|---|---:|---:|
| 长度 | 9.798 m | 11.711 m |
| 采样最小额外 NavMesh 余量 | 0.000 m | 0.410 m |
| 采样中位额外余量 | 0.177 m | 0.599 m |
| 余量 <0.10 m 的样本比例 | 42.2% | 0% |

原路线以 0.025 m 间隔统计，新参考另以 0.01 m、1,173 个样本加密复核。新路线增加约 19.53% 长度；这些是规划几何指标，不是模型成功率。NavMesh 已计入约 0.10 m 的机器人半径，上表是相对 NavMesh 边界的额外留白，无法保证偏离路线的模型动作无碰撞。

## 任务和评估接口

保留原 turn-000 的起终点、yaw/pitch、geodesic_m 及其他原字段；只替换 path，新增 shortest_path、reference_path_kind、reference_path_length_m、reference_planner 和余量统计。继承的 geometry/采样分类字段仍描述原最短任务。必须改用新的 --tasks 文件才启用本变体。

运行器重新检查当前 NavMesh 的原最短距离，SPL 分母和成功判定继续使用该距离。reference_path_length_m 单独记录新路线长度。模型只收到新参考上的局部采样，没有把原最短路线作为额外答案送给模型。v5 提示词、七动作、重新关联和五步摘要、深度计算和 allow_sliding 均保持。

新回放蓝线表示本轮参考，紫线表示另存的原最短路径，橙线仍是实际运动；旧历史文件未重写。

## 验证证据

- [57 项测试](tests.txt)；[生成输出](generation.txt)。
- [独立验证](verification.json)、[验证脚本](verify.py)：7 段原生直连、119 个理想路径位置的目标可达与进度、基准和旧文件保护。
- [最终源码重生成及运行集成核对](integration-verification.json)：路径完全一致，生成器哈希经最终重生成核实；实际请求使用新路线，原最短距离保留，回放两条路线均出现。
- [实际 mesh 冒烟回放](../../runs/smoke-clearance-reference-20260929-01/index.html)、[控制台](smoke.txt)、[进程记录](smoke-process.json)。GPU 7，初始化约 0.8 s，脚本 stop 产生预期 early_stop，正常退出。移除了测试子进程 API 密钥，未调用模型。
- [94 个受保护文件哈希](protected-before.json)保持；配置、原任务、历史日志、core.py、environment.py、jev.py 均未修改。修改前运行/回放代码保存在 before/。

## 复测

在 habitat-gs 环境和 jev_nav 目录运行：

```bash
CUDA_VISIBLE_DEVICES=7 python run.py --config config.single-gpu.json run \
  --tasks tasks/challenge-clearance-20260929-01/tasks.json --episode turn-000 \
  --out runs/jev-challenge-turn-000-clearance-01 --rgb gs --max-steps 250
python visualize.py --run runs/jev-challenge-turn-000-clearance-01 --serve --port 8765
```

显存有限可用 --rgb mesh。保持与前轮相同的 250 步预算，先观察转角附近停滞、实际轨迹与参考的偏离、无效动作和最终距离。原动作策略保持，因此本次可以优先归因于参考路线变化，但单轮结果仍不足以估计稳定成功率。

复用生成器：

```bash
python prepare_clearance.py --tasks tasks/challenge-v1-20260928/tasks.json \
  --episode turn-000 --out tasks/my-clearance-variant
```

--episode 可重复，省略则选择全部原任务。输出必须使用新目录。
