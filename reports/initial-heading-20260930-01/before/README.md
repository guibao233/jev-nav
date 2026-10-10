# Jev 路径辅助跟随与避障：shuyuan 最小实验

目标：先在 NavMesh 上确定可达起终点及初始最短路径，参考路线默认采用最短路径，也可选用居中路线变体；每步把当前位置前方一段**有序路径采样点**转换成机器人相对位置，与当前 mesh 深度摘要、本体参数及最近动作结果一起交给 Jev，选择一个动作。此实验测量路径辅助下的跟随、局部避障、碰撞恢复和停止，不测独立全局寻路。

模块独立于 `habitat_dynamic_search`。不使用物体标注，不修改场景资产、原 NavMesh、已有实验或 Conda 依赖。真实 Jev 调用使用 Python 标准库访问 [OpenRouter Decisions API](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request)。

基础模块已完成离线与实际 GPU 仿真验证，并已有用户执行的真实 Jev 运行记录。详情及回放见 [验证记录](VALIDATION.md)。可视化工具只读取已有记录，不调用模型。

## 2026-09-29 更新：可选的居中参考路线

已生成与原 turn-000 **相同起点、终点和初始朝向**的 [居中路线任务](tasks/challenge-clearance-20260929-01/tasks.json) 和 [新旧路线对照图](tasks/challenge-clearance-20260929-01/index.html)。必须在运行时选用新 tasks 文件才会采用这条路线，原任务文件继续使用原参考路径。

采用“路程 + 靠近 NavMesh 边界的连续软惩罚”的网格 A*，并逐段检查可通行性。新参考长度 **11.71 m**，原最短距离 **9.80 m**；1 cm 密集采样下，新路线最小额外 NavMesh 余量约 **0.41 m**、中位余量 **0.60 m**。这些余量是原 NavMesh 已计入约 0.10 m 机器人半径之后的额外空间；不代表模型实际运动保证无碰撞。

```bash
CUDA_VISIBLE_DEVICES=7 python run.py --config config.single-gpu.json run \
  --tasks tasks/challenge-clearance-20260929-01/tasks.json --episode turn-000 \
  --out runs/jev-challenge-turn-000-clearance-01 --rgb gs --max-steps 250
python visualize.py --run runs/jev-challenge-turn-000-clearance-01 --serve --port 8765
```

显存紧张可用 `--rgb mesh`。本次保持 v5 提示词、七动作、停滞摘要和重新关联策略，便于单独比较参考路线效果。

任务中的 `path` 为新参考路线，`shortest_path` 保存原路线，`geodesic_m` 保持原最短距离；SPL 和成功判定继续使用原 NavMesh 最短距离。回放中蓝线为本轮参考路线，紫线为另存的原最短路径，橙线为实际轨迹。

以后可复用离线生成工具；不需要 GPU 或 API key，不覆盖既有目录：

```bash
python prepare_clearance.py --tasks tasks/challenge-v1-20260928/tasks.json \
  --episode turn-000 --out tasks/my-clearance-variant
```

可重复 `--episode` 选择多条，省略则处理全部。默认网格 0.10 m、代价衰减尺度 0.20 m、权重 4；可用 `--grid-m`、`--clearance-m`、`--weight`、`--padding-m` 调整。衰减尺度是软偏好，不是硬最小余量，不额外侵蚀 NavMesh。当前工具支持高度跨度 ≤0.02 m 的平面路线；网格找不到路时明确报错，可尝试更细网格或更大搜索范围，不自动退回贴边路线。

57 项回归与实际 mesh 初始化通过；没有运行新的真实 Jev 任务。详细证据见 [居中参考路线验证](reports/clearance-reference-20260929-01/README.md)。

## 2026-09-29 更新：路径重新关联与五步停滞摘要

当前提示词为 `seven_actions_reassociate_motion_v5`，路径策略为 `checked_reassociation_v1`。

- 路径正常跟踪仍采用局部、单调投影。机器人离旧跟踪窗口超过 0.5 m 时，寻找距离机器人不超过 0.5 m 的后续路线投影点；只有 NavMesh 直连检查通过才重新关联。直连按最多 5 cm 一段查询运动过滤器，每个期望位置均须可达，不能靠绕行或滑动到另一个位置来通过。保留初始路线、拐角目标与单调进度。
- 模型输入新增 `recent_motion`，仅汇总最近五步已有自身动作。净位移按每步身体朝向变化组合，不能直接相加各步局部前进距离；同时提供净转角、累计转角、相邻相反转向次数、碰撞和无效动作计数。
- 完整五步窗口净位移不超过 0.05 m（当前 0.25 m 步长）且至少两对相邻相反转向时，标记 `turn_oscillation`。`no_translation` 本身也可能只是正常观察，提示词明确区分动作执行成功与导航进展。没有强制后退、屏蔽动作或替模型选择恢复方向。

七动作、前后各 0.25 m、明确停止规则、allow_sliding、深度算法及 API 调用方式保持。NavMesh 只检查重新关联连接，不把查询结果当成 Jev 动作的安全答案。

同一任务复测：

```bash
CUDA_VISIBLE_DEVICES=7 python run.py --config config.single-gpu.json run \
  --tasks tasks/challenge-v1-20260928/tasks.json --episode turn-000 \
  --out runs/jev-challenge-turn-000-reassociate-motion-01 --rgb gs --max-steps 250
python visualize.py --run runs/jev-challenge-turn-000-reassociate-motion-01 --serve --port 8765
```

显存紧张时可用 `--rgb mesh` 省去 GS RGB 渲染器，深度与模型输入方案相同。

新日志可查看 `request.state.reference.tracking`（本步关联方式、路线进度与跳变量）和 `request.state.recent_motion`。已有回放会展示这些真实请求字段。

验证：50 项回归通过；neutral-02 的 250 份保存状态重放能修复路线进度滞后并识别转向循环；12 条正常路线的 1,448 个采样状态保持原目标行为；真实 mesh 六步冒烟已核对新字段。没有调用 Jev，实际导航改善待复测。见 [实现与验证报告](reports/reassociate-motion-20260929-01/README.md)。

## 2026-09-29 更新：恢复中性动作与通用恢复描述

该阶段提示词版本为 `seven_actions_neutral_v4`，现已由上述 v5 替代。以成功实验 `jev-challenge-turn-000-02` 保存的请求为依据，恢复通用导航说明与六个非停止动作的原始描述：后退只说明“保持身体朝向向后移动指定距离”；恢复“允许暂时远离目标进行恢复”及“避免无进展的相反动作交替”。去掉后来新增的后退专属恢复/后方风险强调，以及“前进受阻后先转向”的指令。深度状态中的后方 unknown 与通用 unknown 提醒仍保留。

当前七个动作、前后各 0.25 m、明确停止规则及 allow_sliding=true 保持；未恢复左右平移。路径、深度计算、短期历史和 API 调用逻辑均未调整。此次恢复的是提示词描述，不能据此保证复现旧九动作实验的成功结果。

```bash
python run.py run --tasks tasks/challenge-v1-20260928/tasks.json --episode turn-000 \
  --out runs/jev-challenge-turn-000-neutral-01 --rgb gs --max-steps 250
```

37 项现有回归通过；在 22 份保存输入上核对旧通用说明和非停止动作描述精确一致，停止规则及输入状态不变。未调用真实 Jev，导航效果待复测。详见 [中性提示词恢复验证](reports/neutral-prompt-20260929-01/README.md)。

## 2026-09-29 更新：恢复后退候选

当前动作集为七个：前进、后退、左转、右转、抬头、低头、停止；左右平移仍禁用。前进和后退共同读取 `config.json` 的 `move_m`，当前均为 **0.25 m / 次**。后退保持身体朝向，由 Jev 自己选择，不会在碰撞后自动触发。

该阶段提示词版本为 `seven_actions_backward_v3`，现已由上述中性描述版本替代。新增后退选项及其当前深度检查；前视深度没有覆盖后方时仍为 unknown。现有停止规则、路径进度管理、深度扇区与数值表达、五步历史、allow_sliding=true 均保持。尚未加入带安全余量的路线、路径重接或深度语义改写。

用同一条 250 步任务测试：

```bash
python run.py run --tasks tasks/challenge-v1-20260928/tasks.json --episode turn-000 \
  --out runs/jev-challenge-turn-000-backward-01 --rgb gs --max-steps 250
```

本次未调用 Jev。37 项回归与真实 mesh 后退验证通过；详情见 [后退验证报告](reports/backward-action-20260929-01/README.md)。

## 2026-09-29 更新：碰撞与无效动作可视化

RGB 与 NavMesh 同步显示动作反馈：**红色边框 / 圈叉表示碰撞，黄色边框 / 方框叹号表示无效动作**，同时注明动作名称和步号。地图保留已经发生事件的机器人位置；当前事件在机器人周围加框线强调。原始 RGB、深度和请求均不改写。

记录中的图像位于本步执行前，因此标识对应**上一动作完成后的当前观察**，最后的终态也会显示上一动作反馈；不会提前给动作前的画面加上未来碰撞。HTML 决策详情及视频顶部文字仍明确展示本帧之后的动作。地图事件点是机器人位置，不是精确的 mesh 接触点。

后续实验自动生成的回放以及 `visualize.py`、`export_replay.py` 的 HTML / MP4 / GIF 均采用此显示。已有回放需要重新导出到新目录：

```bash
python visualize.py --run runs/jev-challenge-turn-000-02 --serve --port 8765
# 如需同时生成视频、动图和静态总览，再加 --media
```

已生成：[真实 Jev 任务新版回放](runs/jev-challenge-turn-000-02/visualizations/events-20260929-01/index.html)、[碰撞/无效动作示例](reports/replay-events-20260929-01/event-examples.png)。验证和时序说明见 [事件可视化报告](reports/replay-events-20260929-01/README.md)。

## 2026-09-29 更新：允许沿边界滑动

`config.json` 新增 `"allow_sliding": true`，由导航适配器传给 Habitat 的已有参数。此方案使用允许滑动的运动过滤路径，绕过当前本地 no-sliding 分支的边界误阻挡；没有修改或重新编译 Habitat-GS 源码，也没有改 NavMesh。

这个参数允许碰壁时沿边界滑动，前进的实际位移可能含侧向分量；不是移除了碰撞约束。当次参数调整没有改变当时的六个可选动作、停止提示、路径和短期历史。新记录的配置及顶层元数据均保存真实 `allow_sliding` 值，需与旧的 false 实验分开比较。需要旧行为时显式设置 `"allow_sliding": false`；缺少该字段的旧配置按 false 解释。

重新测试同一任务（使用新输出目录）：

```bash
python run.py run --tasks tasks/challenge-v1-20260928/tasks.json --episode turn-000 \
  --out runs/jev-challenge-turn-000-sliding-01 --rgb gs --max-steps 500
```

## 2026-09-29 更新：六动作与明确停止提示

该阶段提示词版本为 `six_actions_stop_v2`，属于恢复后退之前的版本。停止规则位于提示词首位：当前目标为最终终点（`current_target.is_final=true`）且 `final_goal.distance_m <= task.stop_tolerance_m`（默认 0.30 m，包含边界）时，立即选择 `stop`；无需到达零距离或对齐身体/相机朝向，停止优先于继续跟随、观察和恢复。该规则同时写入 stop 选项说明。

该阶段模型选项、Habitat 动作空间和深度动作检查统一到六动作。只保留前进的扫过体积检查，九个方向的障碍距离扇区仍保留。被移除的动作若意外返回，会记为无效、不执行并消耗预算。最终成功仍由原 NavMesh 距离和主动 stop 判定，不自动代替模型停止；提示词使用的水平距离与评估用的路径距离并非普遍等价。

新运行元数据记录 `available_actions` 与 `prompt_version`。旧任务路线可以复用，旧实验记录及回放保持原样；历史报告中的九动作描述对应旧版本。比较新旧结果时需同时注明动作集与提示词变化。

```bash
python run.py run --tasks tasks/challenge-v1-20260928/tasks.json --episode turn-000 \
  --out runs/jev-challenge-turn-000-six-actions-01 --rgb gs --max-steps 500
```

## 已固定的实验约定

- 环境：`config.json` 指定 shuyuan 资产目录。`shuyuan.mesh.ply` 提供深度，原 `shuyuan.navmesh` 约束运动；可选同位姿的 `shuyuan.gs.ply` RGB 仅供回放，不送给模型。
- 机器人半径和高度读取 NavMesh 保存的参数。本场景为约 0.10 m / 1.50 m，`config.json` 当前设置 `allow_sliding=true`，允许碰壁后沿 NavMesh 边界滑动。运动为 Habitat 离散运动学动作，无 Bullet 动力学。
- 每轮固定任务文件中的参考路线（默认最短路径，也可选用居中变体），不自动重规划。每步提供沿路径前方 3 m 的预览，每 0.5 m 采样并额外保留拐角；“前方”指路径进度方向，不要求位于当前相机视野内。局部目标前视 0.75 m，在下一拐角截断；预览可能包含拐角之后的点，不能直接抄近路。
- 路径正常投影采用局部、单调进度。偏离局部窗口超过 0.5 m 后，仅当附近后续路线点通过 NavMesh 直连检查才重新关联；否则保持原进度。重关联不会重规划路线。只保留路线管理状态，不记忆历史障碍。
- 所有目标转换成**当前身体坐标系**：前方/左方为正，方位角向左为正。相机低头不改变目标的水平相对坐标。
- 短期记忆仅最近 5 个自身动作的有效性、执行成功、碰撞、实际局部平移及角度变化，并计算这些动作的净位移、相反转向等摘要；不保存跨帧地图、历史深度或模型思考文本。
- 七个动作：前进、后退各 0.25 m（共用 `move_m`）；左右转各 15°；抬头/低头各 15°；停止。俯仰角正值向下，范围 [-30°,45°]。
- 碰撞、受阻、未知动作或超限后继续决策。未知/超限动作不改变位姿，但计入 100 步预算。没有规则控制器接管，也不根据深度屏蔽/替换模型动作。NavMesh 的正常运动过滤仍然生效。
- 只有主动 `stop` 且到**最终终点**的 NavMesh 路径距离 ≤0.30 m 才成功。进入范围不会自动结束；到达中间目标不能停止。记录提前停止、曾到达但未正确停止、预算耗尽、服务失败。
- API 失败最多重试 2 次；鉴权/格式错误不反复重试。失败单独记录，不生成替代动作。每步同步“观察→决策→执行”。

## 深度摘要

当前帧米制相机 Z 深度反投影后，消除俯仰角，按离机器人脚底的高度筛选障碍，按水平角度分为 9 区间。每个区间提供最近障碍、观测表面距离统计和近地面覆盖情况。

前进和后退动作分别有 `blocked / clear / unknown` 和身体新增扫过体积的观测比例。`blocked` 来自有邻域支持的障碍像素；`clear` 要求采样的扫过体积都被深度射线观测为空闲；其余为 `unknown`。视野外、无效深度和遮挡不解释为空闲。检查不查询 NavMesh。

这些是离散采样、阈值化的几何估计，不能保证无碰撞。mesh 细节、地面偏差、细小物体与 NavMesh 的边界也可能不同。成功和**无碰撞成功**分别统计。`collided` 是 Habitat Agent 移动过滤反馈，不是完整的刚体接触检测。

## 运行

使用已经配置好的 `habitat-gs` 环境；无需安装 SDK、requests 或 pytest：

```bash
conda activate habitat-gs
cd /data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav
python -m unittest -v test_core
```

`config.json` 默认使用进程内的 CUDA GPU 2。只暴露一张卡时，使用新增的 `config.single-gpu.json`（`gpu_id=0`，其余设置为当前配置的副本）：

```bash
# 物理 GPU 7 在这个进程中对应逻辑 GPU 0；--config 必须放在 run 前面。
CUDA_VISIBLE_DEVICES=7 python run.py --config config.single-gpu.json run \
  --tasks tasks/challenge-v1-20260928/tasks.json --episode turn-000 \
  --out runs/jev-challenge-turn-000-neutral-02 --rgb gs --max-steps 250
```

切换单卡时只替换 `CUDA_VISIBLE_DEVICES` 的值，配置里的 `gpu_id` 继续使用 0。此文件是当前 `config.json` 的副本；以后调整基础参数时需同步到所用配置。设备初始化失败也可能已创建输出目录，重试使用新 `--out`，不要覆盖历史记录。

若显存紧张，可将 `--rgb gs` 改为 `--rgb mesh` 或 `--rgb none`，避免额外加载 GS RGB 渲染器；mesh 深度、NavMesh、任务和模型输入方案保持相同，回放分别显示 mesh RGB 或不含 RGB。仍需可用的 EGL GPU 渲染 mesh 深度。

生成任务（无渲染、无 API）：

```bash
python run.py sample --count 10 --seed 20260928 --out tasks/debug-10.json
python run.py sample --count 50 --seed 20260929 --out tasks/eval-50.json
```

已存在的文件拒绝覆盖。任务按 NavMesh 最短距离 2–5 m、相同连通区域、近似同层、端点额外留白筛选。straight/corner/detour 按路径长度与直线距离之比分层，是几何代理标签，不宣称物体类别或“家具绕行”语义标签。预存任务含种子、朝向、原路径及资产信息；运行时检查 NavMesh 哈希。

不调用模型的仿真验证：

```bash
python run.py smoke --tasks tasks/debug-10.json --episode episode-000 \
  --out runs/my-smoke-01 --rgb gs
```

默认脚本测试低头上限、前进、左右转、抬头和提前停止。`--actions` 可提供逗号分隔的动作序列；`--rgb mesh` 用 mesh RGB 验证，`--rgb none` 只保存深度。所有 smoke 结果明确标记 `scripted_smoke`，不代表 Jev 导航能力。

**真实 Jev 实验需要配置密钥，不能把 smoke 当作模型结果。**当前调用配置：

- 密钥只读取环境变量 `OPENROUTER_API_KEY`，无需 TypeSafe 密钥。
- 请求地址：`https://openrouter.ai/api/alpha/decisions`。
- `config.json` 默认模型：`typesafe/jev-1.13`。若需要跟随最新版本，可显式改为官方别名 `~typesafe/jev-latest`；实验日志保留服务返回的实际模型 ID。
- 请求为 `model + state + questions`，使用七选一 Choice。保留 OpenRouter 返回的概率、置信度、请求 ID 和 `usage.cost`，不使用聊天生成或 Jev Router 的模型路由功能。

用户在自己的终端配置密钥后，才执行：

```bash
# Bash 中隐藏输入密钥；不把密钥字面量写入命令历史。
read -r -s -p 'OpenRouter API key: ' OPENROUTER_API_KEY
export OPENROUTER_API_KEY

python run.py run --tasks tasks/debug-10.json --episode episode-000 \
  --out runs/jev-debug-000-01 --rgb gs
```

缺少密钥会在加载渲染器前停止，不发送请求。模块只从上述环境变量取密钥，不扫描其他项目的配置，不把请求头或密钥写入日志；旧的 `TYPESAFE_API_KEY` 不会用于 OpenRouter。一次最多 100 个决策，每次可能有有限重试；401 鉴权失败、402 余额不足直接记录服务失败。先验证单轮再自行批量运行。`--max-steps 5` 可以限制首次联调。

### 首次启动与中断

`--rgb gs` 会额外加载约 1 GB 的高斯资产用于回放，初始化可能耗时数十秒。控制台会依次显示 mesh 就绪、GS 加载/就绪和进入决策循环；直到出现 `[jev] Requesting action ...` 才开始请求模型。`shuyuan.gs.scn` / `info_semantic.json` 的缺失提示属于语义标注加载，本实验的 RGB、mesh 深度与 NavMesh 导航不依赖它们。

原生渲染器初始化期间按 Ctrl+C，会等当前构造完成后关闭渲染器、保存 `interrupted` 记录并以状态码 130 退出；不会继续调用模型。第一次 API 联调可用 `--rgb mesh --max-steps 5` 跳过 GS RGB 加载，深度、导航路径和模型输入方案保持相同。重试使用新的输出目录，避免覆盖原记录。

## 更长路线测试

`jev-first-5steps-03` 已完成 [逐帧审核](reports/success-audit-20260928-01/README.md)：4.20 m 直线任务，36 次决策后主动停止，零碰撞，3 次无效低头。高 SPL 不代表原地转向和观察开销小。

已生成 [12 条固定挑战任务](tasks/challenge-v1-20260928/README.md) 和 [NavMesh 路线预览](tasks/challenge-v1-20260928/index.html)：6–10 m 长直线对照、6–10 m 转弯、10–15 m 多转弯、15–20 m 更长绕行，每档 3 条。新任务几何已验证，模型效果待运行。

```bash
# 9.80 m、2 个明显转折；沿用已成功运行的 500 步预算
python run.py run --tasks tasks/challenge-v1-20260928/tasks.json --episode turn-000 \
  --out runs/jev-challenge-turn-000-01 --rgb gs --max-steps 500
python visualize.py --run runs/jev-challenge-turn-000-01 --serve --port 8765

# 如需新种子/更多任务：只生成任务与静态预览，无 GPU 或 API
python prepare_challenges.py --per-tier 3 --seed 20261001 --out tasks/challenge-v2
```

切换 `--episode` 为 control-000、long-000、extended-000 可测试各档第一条；同步改用新的 `--out`。`run.py` 不会自动读取任务集的建议预算，需显式提供 `--max-steps 500`。任务生成器使用已有 habitat-gs 环境，不改配置或旧任务；拒绝覆盖既有输出。转折按路径顶点 ≥30° 的水平转角计算，具体筛选及比较指标见任务集 README。

## 输出和回放

每次运行要求新目录，不覆盖历史结果：

```text
metadata.json         模式、API 服务及地址、完整配置、任务、资产来源及 NavMesh 哈希
steps.jsonl           每帧请求、返回、实际动作和度量；没有 API 请求头
summary.json          成功、无碰撞成功、步数、碰撞、无效动作、路径长度、SPL、延迟
frames/*-depth.npz    原始 float32 深度，键 depth_m
frames/*-depth.png    0–6 m 固定色标深度预览
frames/*-rgb.png      同位姿 RGB（可选）
navmap.png            仅供回放/评估，不送入 Jev
index.html            离线回放：观察、参考路线及原最短路线（如另存）、实际轨迹、输入和决策
```

直接打开 `index.html` 即可。每帧观察与输入是执行动作**之前**的状态，结果字段是执行之后的反馈；最后另存一帧终态。脚本运行在页面上明确提示“没有调用 Jev”。

NavMesh 视图会放大本轮任务所在区域：绿色 S 起点、红色 G 终点、蓝色本轮参考路线、紫色另存的原最短路径（如有）、橙色已执行轨迹、白色机器人朝向；粉色菱形 T 为 `current_target`，青色编号点为 `ordered_preview`。目标点使用实际请求内的 `forward_m / left_m` 和当帧身体位姿反算到世界 X/Z 平面，不重新规划或产生新的目标；精度受原日志 0.001 m 舍入影响。终态没有模型请求，不显示新的目标点。底图是已保存的 NavMesh 可通行区域投影，裁剪仅影响展示。

### 可复用的可视化工具

使用 `visualize.py`，只需要提供一个已结束的实验目录。无需 API key 或 GPU，不启动 Habitat；需要当前 `habitat-gs` 环境中的 NumPy、Pillow。

```bash
conda activate habitat-gs
cd /data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav

# 推荐：生成交互回放，并提供浏览器入口
python visualize.py --run runs/jev-first-5steps-02 --serve --port 8765
```

终端会打印新输出目录和 `http://127.0.0.1:8765/index.html`。在远程服务器运行时，先在 VS Code 的“端口”面板转发 **8765**，再用本机浏览器打开该地址；如果转发后的本地端口不同，使用 VS Code 显示的本地地址。终端保持运行，按 Ctrl+C 关闭浏览服务，生成文件仍保留。端口占用时可改成 `--port 8766`。

网页支持播放/暂停、上一帧/下一帧、左右方向键、拖动时间轴和调整展示间隔。包含 RGB、深度、NavMesh、模型输入、返回概率和执行结果。速度设置只控制展示，不代表真实执行时间。

```bash
# 仅生成 HTML，然后退出
python visualize.py --run runs/jev-first-5steps-02

# 同时导出 MP4、GIF 和静态总览；也可追加 --serve
python visualize.py --run runs/jev-first-5steps-02 --media

# 指定新的输出目录
python visualize.py --run runs/jev-first-5steps-02 --out visualizations/my-review-01
```

默认输出到 `<实验目录>/visualizations/view-时间戳/`；重复运行自动选新目录，不覆盖旧回放。指定 `--out` 时也要求目录不存在。输出包含所有页面所需图像，可以将**整个输出目录**下载到本机浏览。`visualization.json` 记录源文件哈希。没有观察帧或缺图的实验会明确报错，不会生成看似完整的回放。

`--media` 额外使用 ffmpeg/ffprobe，默认使用已验证的 `concerto` 环境中的程序，找不到时检查 PATH；也可用 `--ffmpeg /path/to/ffmpeg --ffprobe /path/to/ffprobe` 指定。只生成 HTML 不需要这两个程序。

旧的独立媒体导出命令仍可用：

```bash
python export_replay.py --run runs/jev-first-5steps-02 \
  --out runs/jev-first-5steps-02/exports/my-navmesh-view-01
```

生成 MP4、GIF、静态总览、单文件 GIF 页面，以及可单独打开的 `maps/*.png` 和目标坐标记录 `map-points.json`。每幅观察显示 1.5 秒，无运动插值，不代表实验实际耗时。输出目录必须是新目录；导出不启动仿真或调用 Jev。

P50/P95 分别统计 Jev 请求耗时（包括重试）与循环耗时（包括图像保存）。这些是本机端到端记录，不代表模型本身的纯推理延迟。服务失败记为独立状态，不能悄悄剔除。

## 文件

`core.py`：坐标、路径预览与单帧深度几何；`environment.py`：任务采样和 Habitat 适配；`jev.py`：请求与有限重试；`run.py`：执行/记录/度量；`visualize.py`：可复用可视化工具与浏览服务；`replay.py`：HTML 回放；`map_view.py`：日志目标反算与 NavMesh 图层；`export_replay.py`：离线视频/动图导出；`test_core.py` / `test_map_view.py` / `test_visualize.py` / `test_recovery.py`：几何、接口、可视化及重新关联/动作摘要回归。

不依赖其他 Jev 导航方案的代码或控制器。本版没有自动批量调参、复杂地图记忆和自动重规划。
