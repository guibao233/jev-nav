# Jev 路径辅助跟随与避障：shuyuan 最小实验

目标：先在 NavMesh 上确定可达起终点及初始最短路径，每步把当前位置前方一段**有序路径采样点**转换成机器人相对位置，与当前 mesh 深度摘要、本体参数及最近动作结果一起交给 Jev，选择一个动作。此实验测量路径辅助下的跟随、局部避障、碰撞恢复和停止，不测独立全局寻路。

模块独立于 `habitat_dynamic_search`。不使用物体标注，不修改场景资产、原 NavMesh、已有实验或 Conda 依赖。真实 Jev 调用使用 Python 标准库访问 [OpenRouter Decisions API](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request)。

基础模块已完成离线与实际 GPU 仿真验证，并已有用户执行的真实 Jev 运行记录。详情及回放见 [验证记录](VALIDATION.md)。可视化工具只读取已有记录，不调用模型。

## 2026-09-29 更新：六动作与明确停止提示

当前提示词版本为 `six_actions_stop_v2`。停止规则位于提示词首位：当前目标为最终终点（`current_target.is_final=true`）且 `final_goal.distance_m <= task.stop_tolerance_m`（默认 0.30 m，包含边界）时，立即选择 `stop`；无需到达零距离或对齐身体/相机朝向，停止优先于继续跟随、观察和恢复。该规则同时写入 stop 选项说明。

模型选项、Habitat 动作空间和深度动作检查已统一到六动作。只保留前进的扫过体积检查，九个方向的障碍距离扇区仍保留。被移除的动作若意外返回，会记为无效、不执行并消耗预算。最终成功仍由原 NavMesh 距离和主动 stop 判定，不自动代替模型停止；提示词使用的水平距离与评估用的路径距离并非普遍等价。

新运行元数据记录 `available_actions` 与 `prompt_version`。旧任务路线可以复用，旧实验记录及回放保持原样；历史报告中的九动作描述对应旧版本。比较新旧结果时需同时注明动作集与提示词变化。

```bash
python run.py run --tasks tasks/challenge-v1-20260928/tasks.json --episode turn-000 \
  --out runs/jev-challenge-turn-000-six-actions-01 --rgb gs --max-steps 500
```

## 已固定的实验约定

- 环境：`config.json` 指定 shuyuan 资产目录。`shuyuan.mesh.ply` 提供深度，原 `shuyuan.navmesh` 约束运动；可选同位姿的 `shuyuan.gs.ply` RGB 仅供回放，不送给模型。
- 机器人半径和高度读取 NavMesh 保存的参数。本场景为约 0.10 m / 1.50 m，`allow_sliding=False`。运动为 Habitat 离散运动学动作，无 Bullet 动力学。
- 每轮固定初始最短路径，不自动重规划。每步提供沿路径前方 3 m 的预览，每 0.5 m 采样并额外保留拐角；“前方”指路径进度方向，不要求位于当前相机视野内。局部目标前视 0.75 m，在下一拐角截断；预览可能包含拐角之后的点，不能直接抄近路。
- 路径投影采用局部、单调进度；不会因另一段路径欧氏距离近就跳过去。明显偏离（超过 0.5 m）时保持进度，让模型恢复。这里只保留路线管理状态，不记忆历史障碍。
- 所有目标转换成**当前身体坐标系**：前方/左方为正，方位角向左为正。相机低头不改变目标的水平相对坐标。
- 短期记忆仅最近 5 个自身动作的有效性、成功、碰撞、实际局部平移及角度变化，不保存跨帧地图、历史深度或模型思考文本。
- 六个动作：前进 0.25 m；左右转各 15°；抬头/低头各 15°；停止。俯仰角正值向下，范围 [-30°,45°]。
- 碰撞、受阻、未知动作或超限后继续决策。未知/超限动作不改变位姿，但计入 100 步预算。没有规则控制器接管，也不根据深度屏蔽/替换模型动作。NavMesh 的正常运动过滤仍然生效。
- 只有主动 `stop` 且到**最终终点**的 NavMesh 路径距离 ≤0.30 m 才成功。进入范围不会自动结束；到达中间目标不能停止。记录提前停止、曾到达但未正确停止、预算耗尽、服务失败。
- API 失败最多重试 2 次；鉴权/格式错误不反复重试。失败单独记录，不生成替代动作。每步同步“观察→决策→执行”。

## 深度摘要

当前帧米制相机 Z 深度反投影后，消除俯仰角，按离机器人脚底的高度筛选障碍，按水平角度分为 9 区间。每个区间提供最近障碍、观测表面距离统计和近地面覆盖情况。

前进动作另外有 `blocked / clear / unknown` 和身体新增扫过体积的观测比例。`blocked` 来自有邻域支持的障碍像素；`clear` 要求采样的扫过体积都被深度射线观测为空闲；其余为 `unknown`。视野外、无效深度和遮挡不解释为空闲。检查不查询 NavMesh。

这些是离散采样、阈值化的几何估计，不能保证无碰撞。mesh 细节、地面偏差、细小物体与 NavMesh 的边界也可能不同。成功和**无碰撞成功**分别统计。`collided` 是 Habitat Agent 移动过滤反馈，不是完整的刚体接触检测。

## 运行

使用已经配置好的 `habitat-gs` 环境；无需安装 SDK、requests 或 pytest：

```bash
conda activate habitat-gs
cd /data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav
python -m unittest -v test_core
```

`config.json` 默认 GPU 2；在实际具有 CUDA/EGL 访问权限的终端运行仿真。若使用 `CUDA_VISIBLE_DEVICES`，应确认逻辑 GPU 编号对应关系。受限沙箱可能看不到该 EGL 设备。

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
- 请求为 `model + state + questions`，使用六选一 Choice。保留 OpenRouter 返回的概率、置信度、请求 ID 和 `usage.cost`，不使用聊天生成或 Jev Router 的模型路由功能。

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
index.html            离线回放：观察、原路线、实际轨迹、输入和决策
```

直接打开 `index.html` 即可。每帧观察与输入是执行动作**之前**的状态，结果字段是执行之后的反馈；最后另存一帧终态。脚本运行在页面上明确提示“没有调用 Jev”。

NavMesh 视图会放大本轮任务所在区域：绿色 S 起点、红色 G 终点、蓝色初始最短路径、橙色已执行轨迹、白色机器人朝向；粉色菱形 T 为 `current_target`，青色编号点为 `ordered_preview`。目标点使用实际请求内的 `forward_m / left_m` 和当帧身体位姿反算到世界 X/Z 平面，不重新规划或产生新的目标；精度受原日志 0.001 m 舍入影响。终态没有模型请求，不显示新的目标点。底图是已保存的 NavMesh 可通行区域投影，裁剪仅影响展示。

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

`core.py`：坐标、路径预览与单帧深度几何；`environment.py`：任务采样和 Habitat 适配；`jev.py`：请求与有限重试；`run.py`：执行/记录/度量；`visualize.py`：可复用可视化工具与浏览服务；`replay.py`：HTML 回放；`map_view.py`：日志目标反算与 NavMesh 图层；`export_replay.py`：离线视频/动图导出；`test_core.py` / `test_map_view.py` / `test_visualize.py`：几何、接口及可视化回归。

不依赖其他 Jev 导航方案的代码或控制器。本版没有自动批量调参、复杂地图记忆和自动重规划。
