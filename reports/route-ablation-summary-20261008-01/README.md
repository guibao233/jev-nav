# 三类路线 × 三种输入：Jev 导航消融汇总

范围：当前七动作 v5 路径跟随策略、同一路线的相同起终点/初始姿态/参考路径。纳入 19 轮真实模型实验，包括可比历史失败；不混入早期九动作、六动作、不同初始朝向或不同参考路径的实验。

简单路线最短/参考均约 4.20 m，预算 100；复杂路线最短 9.80 m、参考 11.71 m，预算 250；长路线最短 16.32 m、参考 19.61 m，预算 500。成功阈值均为 NavMesh 距离 <=0.30 m 且模型输出停止。

## 成功数 / 运行数

| 路线 | 数值深度 | 语义深度 | 无深度 |
|---|---|---|---|
| 简单路线 | 2/2 | 2/2 | 2/2 |
| 复杂路线 | 1/3 | 1/2 | 1/2 |
| 长路线 | 1/2 | 0/2 | 0/2 |

## 逐轮指标

批次：H=此前同配置历史记录；M1=第一批 mesh RGB 回放；G1/G2=GS RGB 回放的第一/第二轮。同一输入的编号用于区分记录，并非所有输入都有同批次运行。RGB 不发送给模型，所有有深度条件仍使用 mesh 深度。完整运行目录见表中链接和 runs.csv。

预算耗尽和提前停止均计失败；累计路程含往返。最终距离保留六位小数，避免将 0.303706 m 的失败误读为达到 0.30 m。

### 简单路线

| 输入 | 批次 | 结果 | 动作数 | 碰撞 | 无效动作 | 累计路程 m | 最终距离 m | SPL |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 数值深度 | [M1](../../runs/jev-simple-numeric-20261008-01/summary.json) | 成功 | 18 | 0 | 0 | 4.000 | 0.240986 | 1.000 |
| 数值深度 | [G1](../../runs/jev-simple-rgbgs-numeric-20261008-01/summary.json) | 成功 | 18 | 0 | 0 | 4.000 | 0.240986 | 1.000 |
| 语义深度 | [M1](../../runs/jev-simple-semantic-20261008-01/summary.json) | 成功 | 23 | 0 | 0 | 4.000 | 0.218624 | 1.000 |
| 语义深度 | [G1](../../runs/jev-simple-rgbgs-semantic-20261008-01/summary.json) | 成功 | 23 | 0 | 0 | 4.000 | 0.240986 | 1.000 |
| 无深度 | [G1](../../runs/jev-simple-rgbgs-none-20261008-01/summary.json) | 成功 | 18 | 1 | 0 | 3.996 | 0.255777 | 1.000 |
| 无深度 | [G2](../../runs/jev-simple-rgbgs-none-20261008-02/summary.json) | 成功 | 18 | 1 | 0 | 3.996 | 0.255777 | 1.000 |

### 复杂路线

| 输入 | 批次 | 结果 | 动作数 | 碰撞 | 无效动作 | 累计路程 m | 最终距离 m | SPL |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 数值深度 | [H](../../runs/jev-challenge-turn-000-clearance-aligned-01/summary.json) | 失败：预算耗尽 | 250 | 1 | 16 | 33.358 | 0.571755 | 0.000 |
| 数值深度 | [M1](../../runs/jev-complex-numeric-20261008-01/summary.json) | 成功 | 86 | 0 | 1 | 13.750 | 0.283747 | 0.713 |
| 数值深度 | [G1](../../runs/jev-complex-rgbgs-numeric-20261008-01/summary.json) | 失败：提前停止 | 119 | 1 | 9 | 15.228 | 0.303706 | 0.000 |
| 语义深度 | [M1](../../runs/jev-complex-semantic-20261008-01/summary.json) | 成功 | 76 | 0 | 0 | 13.000 | 0.265350 | 0.754 |
| 语义深度 | [G1](../../runs/jev-complex-rgbgs-semantic-20261008-01/summary.json) | 失败：提前停止 | 124 | 1 | 6 | 15.901 | 0.351736 | 0.000 |
| 无深度 | [H](../../runs/jev-challenge-turn-000-clearance-aligned-no-depth-01/summary.json) | 失败：预算耗尽 | 250 | 29 | 0 | 43.098 | 0.910429 | 0.000 |
| 无深度 | [G1](../../runs/jev-complex-rgbgs-none-20261008-01/summary.json) | 成功 | 77 | 6 | 0 | 13.430 | 0.294787 | 0.730 |

### 长路线

| 输入 | 批次 | 结果 | 动作数 | 碰撞 | 无效动作 | 累计路程 m | 最终距离 m | SPL |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 数值深度 | [G1](../../runs/jev-extended-rgbgs-numeric-20261008-01/summary.json) | 成功 | 252 | 0 | 4 | 30.000 | 0.161575 | 0.544 |
| 数值深度 | [G2](../../runs/jev-extended-rgbgs-numeric-20261008-02/summary.json) | 失败：预算耗尽 | 500 | 1 | 78 | 30.721 | 9.730200 | 0.000 |
| 语义深度 | [G1](../../runs/jev-extended-rgbgs-semantic-20261008-01/summary.json) | 失败：预算耗尽 | 500 | 0 | 18 | 57.500 | 1.776616 | 0.000 |
| 语义深度 | [G2](../../runs/jev-extended-rgbgs-semantic-20261008-02/summary.json) | 失败：预算耗尽 | 500 | 0 | 16 | 55.000 | 1.209574 | 0.000 |
| 无深度 | [G1](../../runs/jev-extended-rgbgs-none-20261008-01/summary.json) | 失败：预算耗尽 | 500 | 46 | 0 | 84.058 | 1.497800 | 0.000 |
| 无深度 | [G2](../../runs/jev-extended-rgbgs-none-20261008-02/summary.json) | 失败：预算耗尽 | 500 | 112 | 0 | 84.545 | 15.817625 | 0.000 |

## 观察

- 简单路线：三种输入均完成；数值深度 18 步且零碰撞，语义深度 23 步且零碰撞，无深度 18 步但每轮各 1 次碰撞。单纯参考路径可支撑直线路径跟随，但不等于可靠避障。
- 复杂路线：数值 1/3、语义 1/2、无深度 1/2。新增无深度成功样本为 77 步/6 次碰撞，历史无深度失败为 250 步/29 次碰撞。数值、语义的成功样本都零碰撞；两个近期失败是容差外提前停止。
- 长路线：只有数值一次成功（252 步、零碰撞、SPL 0.544）；语义两次均零碰撞但在终点附近绕行；无深度两次均失败且共 158 次碰撞。
- 总体：本批证据支持深度对减少碰撞有帮助；不能将零碰撞视为完成导航，也不能凭每格 2–3 次重复确定数值或语义的稳定优劣。

## 可比性和限制

- 每类只有一个固定起终点，因此是案例级消融，不是跨场景或多目标基准成功率。历史记录与近期记录不构成同一随机种子的配对试验；模型服务同请求可返回不同动作。
- 复杂数值组有 3 轮，其余各 2 轮；不可选择性剔除历史失败。aggregate.csv 保留各组样本数，不能直接合并不同难度来判断总体排名。
- 无深度仍保留参考路径、目标相对位置、本体状态和最近自身动作反馈；不是纯盲导航。相应提示词移除了深度和观察指令，语义版也有编码说明。
- 碰撞为 Habitat 的 NavMesh 移动过滤 collided，不是 Bullet 接触计数；成功与零碰撞成功分别记录。无效动作消耗预算。
- 累计路程不计原地转向与观察成本。失败路径受预算或提前停止截断，均值不是成功路径效率。
- M1 与 GS 记录的渲染耗时不可直接当作模型决策性能差异。

## 输出与核查

- [逐轮 CSV](runs.csv)：含所有所需指标、SPL、最小到达距离和原始目录。
- [按路线/输入聚合 CSV](aggregate.csv)：含成功数、零碰撞成功数、均值及总碰撞。
- [结构化结果与源文件哈希](summary.json)，[离线核查脚本](summarize.py)。
- 所有 3852 个实际动作重新计算到终点的 NavMesh 距离、累计路程、成功条件和 SPL；碰撞、无效动作由逐步日志重新计数。输入条件、共同配置、模型版本、日志步序和帧间位姿连续性均通过核对。历史 metadata 未必有 rgb_provided_to_model 字段，因此同时检查了实际保存的请求中不含图像载荷。此次没有重新渲染或逐帧重算原始深度。
- 检查原始日志和任务文件哈希未变化；未调用 API，未使用 GPU。

## 排除的完成记录

| 运行 | 原因 |
|---|---|
| jev-challenge-turn-000-01 | different action/prompt/route policy generation |
| jev-challenge-turn-000-02 | different action/prompt/route policy generation |
| jev-challenge-turn-000-backward-01 | different action/prompt/route policy generation |
| jev-challenge-turn-000-clearance-01 | different initial pose or reference path |
| jev-challenge-turn-000-clearance-02 | different initial pose or reference path |
| jev-challenge-turn-000-neutral-02 | different action/prompt/route policy generation |
| jev-challenge-turn-000-reassociate-motion-01 | different initial pose or reference path |
| jev-challenge-turn-000-six-actions-01 | different action/prompt/route policy generation |
| jev-challenge-turn-000-six-actions-02 | different action/prompt/route policy generation |
| jev-challenge-turn-000-six-actions-03 | different action/prompt/route policy generation |
| jev-challenge-turn-000-sliding-01 | different action/prompt/route policy generation |
| jev-first-5steps-01 | different action/prompt/route policy generation |
| jev-first-5steps-02 | different action/prompt/route policy generation |
| jev-first-5steps-03 | different action/prompt/route policy generation |
| jev-first-5steps-05 | different action/prompt/route policy generation |
| jev-first-5steps-06 | different action/prompt/route policy generation |
