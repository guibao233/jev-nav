# 基础模块验证记录（2026-09-28）

**真实 Jev 请求次数：0。** 按用户要求，验证到仿真与接口模拟为止，等待用户配置 `OPENROUTER_API_KEY` 后再开展模型实验。以下成功/失败均为预设动作的集成测试，不能解释为 Jev 的导航表现。

## 已验证

- `/data/guiyuanze/miniconda3/envs/habitat-gs/bin/python -m unittest -v test_core`：13 项通过。覆盖身体坐标、俯仰补偿、地面过滤、未知深度、障碍判断、路径拐角/进度、停止条件、九动作请求和模拟 HTTP 返回/鉴权失败。
- 已生成 [10 轮调试任务](tasks/debug-10.json)（4 straight / 3 corner / 3 detour）和 [50 轮评估任务](tasks/eval-50.json)（17 / 17 / 16）。每轮 NavMesh 路径距离 2–5 m；两组没有相同起终点对。这里只完成任务采样，尚未执行这 60 轮模型评估。
- 实际 GPU 2 上完成 GS RGB 和 mesh 深度的同位姿渲染；查看了输出的办公室 RGB 和低头深度预览。
- 三次完整仿真运行的所有帧文件存在，日志可解析；逐帧确认输入记忆恰为最近至多 5 条自身动作结果。
- 回放 JavaScript 通过 `node --check`。本次未进行浏览器交互测试。

| 运行与回放 | 执行动作数 | 碰撞 | 无效动作 | 验证结果 |
| --- | ---: | ---: | ---: | --- |
| [GS + mesh 基础动作](runs/smoke-gs-20260928-02/index.html) | 12 | 0 | 1 | 三次低头到 45°，第四次低头超限且计步；四向平移及左右转角正确；远离终点停止记为提前停止 |
| [碰撞后继续执行](runs/collision-check-20260928-01/index.html) | 7 | 2 | 1 | 连续受阻后后退成功；未知动作不改变位姿且计步；提前停止记为失败 |
| [到达后停止](runs/arrival-check-20260928-01/index.html) | 17 | 0 | 0 | 16 次前进后距终点约 0.196 m，主动停止记为成功和无碰撞成功 |

碰撞与到达测试分别使用 [collision-fixture.json](tasks/collision-fixture.json) 和 [arrival-fixture.json](tasks/arrival-fixture.json)。它们从调试任务的同一起终点派生，调整初始朝向以触发特定执行分支，不能作为随机任务性能统计。

`runs/smoke-gs-20260928-01` 保留了最初受限沙箱中的未完成尝试：EGL 无法匹配 CUDA device 2，原生渲染进程退出，未生成完整报告。随后在可访问实际 GPU 的执行环境中完成 `smoke-gs-20260928-02`；未改动 Conda 环境或场景资产。

## 尚未验证

真实 Jev 服务的鉴权、在线返回、延迟、路径跟随成功率和碰撞率仍待验证。模拟 HTTP 测试只能检查客户端协议处理。建议配置密钥后先执行一轮最多 5 步的联调，再进行完整任务：

```bash
conda activate habitat-gs
cd /data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav
# 在自己的终端预先配置 OPENROUTER_API_KEY；不要把密钥写入代码或日志。
python run.py run --tasks tasks/debug-10.json --episode episode-000 \
  --out runs/jev-first-5steps-01 --rgb gs --max-steps 5
```

此命令尚未执行。每次使用新的输出目录。

## OpenRouter 接口迁移验证（2026-09-28）

按用户要求将客户端切换到 [OpenRouter Decisions API](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request)：`POST https://openrouter.ai/api/alpha/decisions`，默认 `typesafe/jev-1.13`，只读取 `OPENROUTER_API_KEY`。保留原导航输入和九选一输出，新增 API 服务与地址记录；历史 `runs/` 内容未改写。

- 同一条 unittest 命令现为 **15 项通过**。模拟 HTTP 校验了目标地址、Bearer 鉴权、模型 ID、原始状态传递，以及请求 ID、实际模型、概率和费用字段保留。
- 401 鉴权失败、402 余额不足不重试；429 限流、524 超时遵循有限重试；畸形答案记为服务失败。旧 TypeSafe 密钥不会被误发给 OpenRouter。
- 显式移除 `OPENROUTER_API_KEY` 后执行真实 CLI 入口，按预期报缺少该变量；在加载渲染器、创建运行目录及发送请求之前退出。
- 本次未重跑 GPU 仿真，导航几何逻辑未改动；**未发送任何真实 Jev 请求**。在线服务可用性与实际导航效果仍待用户配置密钥后联调。

## 目录迁移验证（2026-09-28）

代码、任务文件和全部测试结果已迁移到 `/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav`（实际路径 `/share/guiyuanze/code/habitat-gs/jev_nav`）。复制后对原有 158 个文件逐一校验 SHA-256；除更新两份说明文档的工作目录外，其余文件内容一致，包含 3 次完整仿真记录和 1 次未完成的 EGL 尝试。

在新目录执行 `python -B -m unittest -v test_core`：**15 项通过**。同时检查了历史回放引用的帧文件和场景资产路径。未重跑 GPU 仿真，未调用 Jev。旧目录 `/data/guiyuanze/code/our_scene_graph/jev_pointnav` 仅保留指向新目录的符号链接，代码和结果实体只存放在新目录。

## GS 初始化中断问题修复（2026-09-28）

用户运行 `runs/jev-first-5steps-01` 时，在 GS 渲染器构造期间收到多次 Ctrl+C，抛出 `KeyboardInterrupt`；随后原生对象清理报 `GL::Context::current(): no current context`。该轮 `steps=0`、步骤日志为空，堆栈停在 `Environment.__init__ -> h.Simulator`，尚未进入 Jev 请求。原始运行记录保留。

源码核对：Habitat 的 `Simulator.cpp` 调用 `ResourceManager::loadSemanticScene` 后继续初始化；缺少 `.gs.scn` / `info_semantic.json` 对当前不使用语义传感器的实验并不致命。正常启动实测也会产生这些提示。

修复：增加 mesh、GS 和 API 请求阶段提示；原生构造期间收到 SIGINT 时先记录取消，等返回并接管完整 simulator 后关闭资源；CLI 保存 interrupted 记录并以 130 退出。没有修改场景文件或 Habitat 安装。

- 离线回归：`python -B -m unittest -v test_core`，**17 项通过**，新增重复中断延迟处理及异常时恢复信号处理器的验证。
- [正常 GS 启动回放](runs/startup-gs-check-20260928-01/index.html)：mesh 约 0.8 s，GS 约 31.0 s；脚本执行 stop，正常以状态码 0 退出，因仍远离终点记 early_stop。
- [加载期间取消记录](runs/startup-interrupt-check-20260928-01/index.html)：GS 开始加载后连续发送 3 次 SIGINT，加载结束后关闭资源，`status=interrupted`、`steps=0`、退出码 130，没有 traceback 或 OpenGL context abort。
- 两个新运行目录均保存 `console.log` 和 `startup-check.json`，后者包含进程退出码、耗时及注入信号时间。两个测试均使用 smoke，并移除测试子进程的 API 密钥，**未调用 Jev**。

首次 API 联调可使用 `--rgb mesh --max-steps 5` 跳过 GS RGB 初始化；如需 GS 回放则继续使用 `--rgb gs` 并等待出现 GS ready。务必使用新的输出目录，例如 `runs/jev-first-5steps-02`。

## NavMesh 与 Jev 目标点可视化（2026-09-28）

已更新 `map_view.py`、`replay.py` 和 `export_replay.py`，在离线 HTML、MP4、GIF、总览中同时显示起点、终点、初始最短路径、已执行轨迹、当前机器人朝向、当前目标与前方有序采样。使用已保存 `navmap.png` 的本轮任务区域投影，仅影响展示。

目标点由每条真实请求的 `forward_m / left_m` 与对应观察的身体位姿反算到世界 X/Z 平面；没有重算或替换模型输入。最后的终态记录没有请求，因此明确不显示新的目标。

本轮 `jev-first-5steps-02` 的新版入口：

- [交互回放](runs/jev-first-5steps-02/index-navmesh.html)
- [三列 MP4](runs/jev-first-5steps-02/exports/viewing-navmesh-01/rgb-depth.mp4)
- [三列 GIF](runs/jev-first-5steps-02/exports/viewing-navmesh-01/rgb-depth.gif)
- [第一帧单独地图](runs/jev-first-5steps-02/exports/viewing-navmesh-01/maps/00000.png)
- [目标坐标记录](runs/jev-first-5steps-02/exports/viewing-navmesh-01/map-points.json)

验证：`python -B -m unittest -v test_core test_map_view`，**21 项通过**；已知朝向的坐标变换、日志目标来源、终态无目标以及地图轴向/裁剪均检查通过。实际五条请求的目标点变回身体坐标后与原始 `forward_m / left_m` 一致，与本轮初始直线路径的最大偏差约 0.000483 m，符合原日志毫米级舍入。

HTML 与视频的地图 PNG 内容一致；HTML JavaScript 通过 `node --check`，未做浏览器交互验证。视频经 ffprobe 与完整解码验证，为 1920×688、H.264/yuv420p、30 fps、270 编码帧、9 秒；6 幅已保存观察各展示 1.5 秒，无运动插值。已目视检查第一帧地图和第五帧三列画面。

迁移前存在的本轮 36 个文件逐一校验 SHA-256 未改变，包括原始日志、原始图像和旧版导出；新版使用新增文件。未重跑仿真，未调用 Jev。后续新实验的默认 `index.html` 会使用更新后的可视化。

## 可复用可视化工具（2026-09-28）

新增 `visualize.py`：`--run` 指定实验目录，默认在其 `visualizations/view-时间戳/` 下生成便携 HTML；`--media` 同时导出 MP4/GIF/总览；`--serve --port 8765` 启动 127.0.0.1 的本地浏览服务。支持播放/暂停、上一帧/下一帧、左右方向键、时间轴和展示间隔选择。

输出复制页面依赖的 RGB、深度和 NavMesh 图像，完整目录可下载到本机。原始请求不变，只有展示用图像路径被重写。工具检查缺图、无观察帧和输出覆盖，记录源文件哈希；不导入 Habitat、不要求 GPU 或 API key。

- `python -B -m unittest -v test_core test_map_view test_visualize`：**26 项通过**。
- 在真实 `jev-first-5steps-02` 记录上完成 `--media --serve --port 0` 端到端验证：[工具生成的回放](runs/jev-first-5steps-02/visualizations/tool-check-20260928-01/index.html)。
- 通过实际 HTTP 请求检查 HTML、RGB、深度、NavMesh、来源清单及 MP4，均返回 200；测试后 Ctrl+C 正常关闭服务，退出码 0。控制台和请求检查记录保存在该目录的 `cli-check.log`、`tool-check.json`。
- 6 条观察的原始请求与 HTML 中嵌入的请求逐一相等，16 个源文件哈希保持一致，页面资源路径均落在输出目录。视频导出通过格式、时长及完整解码检查。
- 通过 Node DOM 桩运行实际生成的脚本，检查初始帧、前后切换、时间轴、键盘、终态、重播、计时器、调速和暂停。未进行原生浏览器的手工交互验收。
- 本次没有运行仿真或调用 Jev；本地 HTTP 测试子进程移除了模型 API 密钥。


## 2026-09-28：成功运行审核与长路线任务

- 原记录 `runs/jev-first-5steps-03`：真实 Jev 成功，36 步、0 碰撞、3 无效低头，最终距离 0.02334 m；本轮配置实际为 500 步预算。逐帧深度、路径输入、动作与历史精确核对，NavMesh 距离及 SPL 独立重算通过。
- 审核记录及原文件哈希：`reports/success-audit-20260928-01/audit.json`；行为解释、限制与后续安排见同目录 README。
- 新增独立 `prepare_challenges.py`，保持决策/几何/执行代码及基础配置不变。生成 `tasks/challenge-v1-20260928`：种子 20260930，159 次采样得到 4 档 × 3 条，距离 6.69–19.42 m，附静态 HTML、PNG 总览与单任务 NavMesh 图。
- 检查全部 12 条可达性、路径几何、分档、无旧任务重合；相同种子重现一致。以理想路径位置每 0.10 m 检查预览进度单调、拐角目标及最终目标，属于输入几何测试，不是离散动作执行或 Jev 结果。详见新任务集 `verification.json`。
- 新增 6 项任务几何/输出保护测试；结合原 26 项，32 项单元测试通过，见审核目录 `tests.txt`。
- 更难任务未调用 Jev，也未作 GPU 闭环测试：当前工具进程无 OPENROUTER_API_KEY。运行命令见主 README 和任务集 README；用户可在已配置密钥的终端继续测试。


## 2026-09-29：明确停止规则与六动作

按用户要求更新为 `six_actions_stop_v2`：当前目标为终点且终点距离 ≤ 容差时立即 stop，无需精确定位或对齐；规则优先于继续跟随、观察和恢复。模型选项、模拟器与深度动作检查统一为前进、左右转、上下俯仰、停止，去除后退及左右平移。保留模型主动停止与原 NavMesh 成功判定。

- 35 项离线回归通过；实际 mesh 仿真 `runs/smoke-six-actions-20260929-01` 覆盖六动作、俯仰超限及提前停止，9 步、0 碰撞、1 次刻意超限、early_stop 符合脚本预期。
- 逐条检查 9 个实际请求：六选一，深度 move_checks 只有 move_forward，优先停止规则已写入。原 47 个配置/任务/历史运行文件哈希保持不变。
- 详细记录、请求样例和修改前源码：[六动作验证报告](reports/six-actions-stop-20260929-01/README.md)。历史章节中的九动作说明属于旧版本。
- 未调用真实 Jev；当前进程无 OPENROUTER_API_KEY。停止行为改善尚待用户终端使用同一任务复测，命令见上述报告。


## 2026-09-29：allow_sliding 执行参数

按用户授权，仅在独立导航模块中启用 Habitat 现有 `allow_sliding` 参数；不修改或编译 Habitat-GS 源码。当前 `config.json` 为 true，旧配置缺少字段时保持 false，新实验元数据保存实际值。

- 在真实 mesh 模拟器中复用三轮失败实验卡点，关闭滑动时合法离开方向全部移动 0 m，开启后全部前进 0.25 m 且无碰撞；第二个卡点使用相对原朝向 +45° 的离开方向。朝不可通行区域移动的对照均仍受 NavMesh 约束并报告碰撞，共验证 12 次实际动作。
- 37 项回归测试通过。正常入口 `runs/smoke-sliding-20260929-01`：9 步、0 碰撞、1 次刻意俯仰超限、early_stop；两处 allow_sliding 元数据均为 true，六动作和停止提示不变。
- 61 个原有任务/日志/结果/受保护源码文件哈希未变，NavMesh 哈希与历史实验一致。允许滑动可能产生被动侧向位移，实验应与旧的 false 配置区分。
- 本次未调用 Jev，也未运行新的完整模型任务；不能将执行层回归通过等同于导航成功率改善。详细证据、限制及复测命令见 [参数验证报告](reports/sliding-config-20260929-01/README.md)。


## 2026-09-29：碰撞与无效动作可视化

新增离线 `replay_events.py`，在动作完成后的下一幅观察上标注碰撞（红色）和无效动作（黄色），终态遵循同一规则。RGB 增加边框与动作/步号提示，NavMesh 同步高亮并保留已发生事件的位置。HTML 和 MP4/GIF 共用绘制逻辑；不覆盖原始图像、日志或旧回放，不改变导航与模型输入。

- 37 项已有回归通过；使用真实保存记录核查共 211 帧。8 帧脚本记录显示 2 次碰撞和 1 次无效动作，203 帧真实 Jev 记录显示 20 次碰撞和 28 次无效动作，与原始结果一致。
- 验证第一帧、动作前不得预告碰撞、动作后对齐、终态、无执行结果、倒退查看及播放切换。实际页面 JavaScript 通过 Node 语法和 DOM 桩运行检查；本地 HTTP 返回 HTML、两类 RGB 标识、地图和视频共 5 个资源。
- 8 帧导出的 HTML 与媒体中的 RGB/地图逐像素一致；MP4 完整解码通过，H.264/yuv420p、1920×688、30 fps、360 编码帧、12 秒；GIF 8 帧、12 秒。已目视检查两类事件的合成图片，未做真实浏览器交互验收。
- 两份导出的源图像/日志哈希均保持不变，另外 21 个受保护导航源码、配置及历史记录哈希通过；未运行仿真或调用 Jev。
- [验证报告](reports/replay-events-20260929-01/README.md)包含可直接查看的回放、事件示例与全部检查记录。


## 2026-09-29：恢复与前进同距离的后退候选

按用户要求恢复 `move_backward`，七个候选仍由 Jev 选择，左右平移仍为无效动作。前进和后退的模拟器 actuation 与提示均共用 `move_m`，当前是 0.25 m；提示词版本 `seven_actions_backward_v3`。只在原深度算法中增加后退方向的检查，后方不可见仍为 unknown。

- 37 项现有回归检查通过。
- 真实 mesh 原生检查：0.25 m 和 0.40 m 两种内存配置 × 两个身体朝向，验证前进/后退各走同一步长、往返返回原点、后退不改变身体朝向和相机俯仰。当前磁盘配置保持 0.25 m。
- 从 sliding-01 第 14 步碰撞后的保存位置与朝向执行一次后退，实际后退 0.25 m、无碰撞、终点可通行。这只是动作执行验证，不代表模型会主动选择正确恢复动作。
- 正常入口 `runs/smoke-backward-20260929-01`：9 个脚本动作，0 碰撞、2 次刻意左右平移无效、early_stop 符合预期。元数据为七动作、allow_sliding=true；全部请求包含 move_backward，前后步长都是 0.25 m。回放中的无效动作标识正常生成。
- 原 RoutePreview 的 AST 完全相同；移除新增后退字段后，全部冒烟帧的深度事实与修改前逐项一致；已有动作 criteria 与停止规则未变。72 个受保护配置、任务、历史记录及源码文件哈希保持不变。
- 未调用 Jev、未修改 Habitat-GS 源码。当前路径冻结、路线安全余量和深度语义等后续议题未在本次调整。
- [详细验证报告](reports/backward-action-20260929-01/README.md)包含日志、脚本、原生结果、冒烟回放和模型复测命令。


## 2026-09-29：中性后退与通用导航描述恢复

按用户要求将提示词更新为 `seven_actions_neutral_v4`。`jev.py` 的通用指令正文恢复为 `jev-challenge-turn-000-02` 首份真实请求中的原文；保留当前最高优先级停止规则前缀与 stop 选项说明。后退和另外五个非停止动作的描述与旧成功实验精确一致。恢复对无进展的相反动作交替的提醒和暂时远离目标进行恢复的许可，移除后加的“后退用于恢复/后方未确认”专属描述及“前进受阻先转向”规则。

- 37 项现有离线回归通过，见报告内 `tests.txt`；没有新增策略或调用真实 Jev。
- 对 backward-01 中保存的 22 份请求状态逐一生成新请求，确认只有通用指令与后退 criterion 改变；当前停止前缀、stop criterion、输入状态、模型和其余请求字段保持一致。包括服务失败那一步的请求，共 22 份；不等于 22 次实际执行。
- 七动作、前后共用 0.25 m、allow_sliding=true 保持。API 客户端代码 AST 未变，88 个配置、任务、历史记录及其他源码文件哈希一致；未修改 Habitat-GS 源码或场景资产。
- 本次属于提示词与离线接口验证，没有运行新的仿真或真实模型任务；不能声称导航能力已恢复。旧成功实验使用九动作且 allow_sliding=false，因此当前设置不是该实验的完整复刻。
- [报告、修改前副本、请求样例及复测命令](reports/neutral-prompt-20260929-01/README.md)。


## 2026-09-29：单卡设备编号配置

新增 `config.single-gpu.json`，仅将默认配置中的 `gpu_id=2` 改为 0，用于 `CUDA_VISIBLE_DEVICES` 只暴露一张卡的启动方式。原配置、导航代码、提示词和旧结果保持原样。`CUDA_VISIBLE_DEVICES=7` 下已用 CUDA Driver API 核对逻辑 GPU 0 的 UUID 与物理 GPU 7 一致。

实际 `runs/smoke-gpu7-20260929-01` 在 7 号卡上正常初始化 mesh 与 GS，完成 1 次脚本 stop 并正常退出；2 幅 RGB 和 2 份 mesh 深度检查通过。early_stop 属于脚本预期，不是模型导航评估。测试子进程移除了 API 密钥，未调用 Jev。详细记录及启动命令见 [单卡验证报告](reports/gpu-selection-20260929-01/README.md)。


## 2026-09-29：路径重新关联与最近动作停滞摘要

按用户确认的两个方向实现：`RoutePreview` 在偏离旧局部窗口时，对距离不超过 0.5 m 的后续路线投影点做 NavMesh 直连检查，通过后更新单调路径进度；`recent_motion` 只汇总最近五步自身动作。提示词版本 `seven_actions_reassociate_motion_v5`，路径策略 `checked_reassociation_v1`。没有自动恢复动作、重规划、动作替换或深度语义改写。

- 50 项回归通过（原 37 项 + 13 项新回归）。覆盖跨墙拒绝、近邻路径分支、拐角、进度不回退、旋转坐标下的净位移、转向循环、正常单向观察及历史截断。
- CPU 重放 neutral-02 的全部 250 个历史状态：新策略在原第 46、82 步分别重新关联，最终参考进度由旧 2.546 m 改为 4.767 m，剩余原路线由 7.252 m 改为 5.031 m。原第 150 步的目标从左侧已越过路段转为右侧后续拐角；同一帧 recent_motion 显示净位移 0、4 对相反转向、turn_oscillation。
- 五步局部动作组合得到的净位移与保存世界位姿差的最大偏差约 0.000411 m，符合原动作日志舍入精度。该摘要计算本身不读取世界位姿、目标或历史深度。
- 12 条挑战路线共 1,448 个理想采样位置，新增 tracking 字段以外的目标/预览行为与旧算法完全一致。真实 NavMesh 负例：两点直线距 0.382 m，但需绕角走 0.400 m，直连检查正确拒绝。
- 在用户所选 7 号 GPU 上运行 `runs/smoke-reassociate-motion-20260929-01`，只加载 mesh、无 API。脚本五次左右交替后 stop，6 步、0 碰撞、0 无效、early_stop 符合预期；第六份实际请求已包含 turn_oscillation，所有脚本选择与实际执行动作一致。
- 七项动作 criteria 和明确停止前缀保持；深度算法、模拟器动作适配器及 API 客户端 AST 保持。90 个配置、任务、历史记录及受保护源码文件哈希不变，未修改 Habitat-GS 源码。
- 离线重放沿用旧轨迹，不能代表新模型会采取这些动作或完成任务；没有调用真实 Jev。报告保存全部验证、请求样例及复测命令：[实现与验证报告](reports/reassociate-motion-20260929-01/README.md)。


## 2026-09-29：带额外 NavMesh 余量的居中参考路线

新增独立 `clearance.py` 与 `prepare_clearance.py`，在原 NavMesh 上以连续距离惩罚执行 CPU 网格 A*，按相同代价与最低余量限制简化路径，生成新任务变体。原 tasks、NavMesh 和场景不覆盖。运行器在初始化前检查新参考路径每段直连；回放同时显示新参考与原最短路线。

- 新任务 `tasks/challenge-clearance-20260929-01/tasks.json` 只包含原 turn-000，起终点、初始朝向、geodesic_m 等原字段保持，path 替换，shortest_path 保留原路径。原 9.79769 m 最短距离仍作 SPL 基准，新参考长 11.71097 m（增加 19.53%）。
- 原最短路径 2.5 cm 采样下最小额外余量 0 m，中位数 0.177 m，42.2% 采样点小于 0.10 m。新参考按 1 cm 验证 1,173 个样本，最小 0.410 m、中位数 0.599 m，低于 0.20 m 的样本为 0；原 NavMesh 已考虑机器人半径，该量不等于实际 mesh 全身安全保证。
- 8 个顶点、7 个线段全部通过原生 NavMesh 直连验证；最短线段 0.550 m。沿新参考的 119 个理想位置检查进度单调、当前目标可直连，无多余重新关联。最终源码重生成得到完全一致的路径。
- 57 项测试通过（此前 50 项 + 7 项新测试），包含窄通道不被软惩罚封死、不可达报错、简化不切穿障碍、零权重长度行为及输出保护。
- `runs/smoke-clearance-reference-20260929-01`：GPU 7、mesh、脚本 stop，正常退出，early_stop 符合预期；实际请求的参考剩余长度为 11.711 m，而 summary.initial_geodesic_m 仍为 9.79769 m。实际回放包含蓝色新路线和紫色原最短路径。
- 提示词仍为 seven_actions_reassociate_motion_v5；core.py、environment.py、jev.py、配置、原任务和历史主要日志等 94 个受保护文件哈希保持。未调用 Jev，模型跟随效果待用户复测。
- [验证报告、命令、对照图与可复用生成器说明](reports/clearance-reference-20260929-01/README.md)。


## 2026-09-30：独立初始朝向对齐任务

新增 `prepare_initial_heading.py`，按运行器相同的首个局部目标计算初始 yaw，处理拐角截断，精度为方位字段的 0.01°。生成 [challenge-clearance-aligned-20260930-01](tasks/challenge-clearance-aligned-20260930-01/tasks.json)，继承居中路线；原字段仅改变 yaw_deg，新增 initial_heading 及生成来源/源码哈希。没有修改运行器、core、环境适配器、提示词或配置。

- **63 项回归通过**，覆盖八方向坐标、首个拐角与终点区别、近拐角/短路线、确定性和来源保护、无效输入与输出覆盖保护。
- 原 12 条 challenge 任务均能对齐，未另行写入任务；当前居中 turn-000 首目标方位从 156.90° 变为 0°、距离保持 0.708 m。新旧任务除 yaw 和新增来源记录外相同；113 个历史任务/日志/配置/原源码哈希保持。
- 实际 GPU 7 的 [mesh 冒烟回放](runs/smoke-initial-heading-20260930-01/index.html)：加载 yaw=−90.390002°，首个请求目标 forward=0.708 m、left=0、bearing=0°。脚本前进 0.25 m，无碰撞/无效动作；第二步预设 stop 产生预期 early_stop，进程正常退出。
- 保留原最短距离 9.797690 m 和参考长度 11.710970 m；提示词仍为 seven_actions_reassociate_motion_v5。没有加入运行中视野约束或自动转向，俯仰不变。
- 未发送真实 Jev 请求，初始化改善是否带来成功率收益待用户测试。几何对齐不等于地面点可见，也不保证后续目标不出视野。

生成命令、验证脚本、测试日志及可复现证据见 [初始朝向验证报告](reports/initial-heading-20260930-01/README.md)。


## 2026-09-30：无深度摘要消融

新增 `run/smoke --depth-input {mesh,none}`，默认 mesh 保留原行为；配置也可写 `depth_input`，CLI 优先。none 分支不调用深度摘要计算，API 组包还会移除输入 state.depth，保持调用者对象原样。没有移除模型的路线、状态、碰撞反馈或任何动作；未修改相机初始姿态、NavMesh、控制器和资产。

- **69 项回归通过**，新增 6 项覆盖 API 边界、深度值独立性、动作/停止规则一致性、真实序列化字段、配置验证和 CLI 选择。模拟 HTTP 请求不含深度摘要，碰撞和路线字段仍在。
- 原真实 `clearance-aligned-01` 的 **250 份请求**与修改前组包函数及新默认模式逐条相等，默认提示词仍为 v5。
- 实际 GPU 7 上同一任务执行两组六步预设动作：前进、低头、左转、前进、后退、停止。两组位姿/执行结果完全一致，0 碰撞/无效、预期 early_stop；两组请求状态仅相差 depth，七动作准则相同。无深度组将 depth_facts 替换成抛错桩，仍正常退出，证明未调用摘要计算。
- 无深度模式提示词只调整对应的感知说明，版本记为 `seven_actions_reassociate_motion_v5_no_depth`。元数据和结果显式标记模式，raw depth/PNG 保留仅供回放；HTML/视频不伪造 missing depth 为 clear 或 unknown。
- 7 幅无深度观察成功导出便携 HTML、MP4、GIF 和静态总览；视频 315 帧、10.5 秒，完整解码与源哈希通过，HTML 请求与日志逐条相等，JavaScript 语法检查通过。
- 118 个受保护历史/任务/配置/其他源码文件哈希一致。本轮真实 Jev 请求为 0，模型导航收益待用户对照测试。

详见 [消融验证报告](reports/no-depth-ablation-20260930-01/README.md)；[无深度组回放示例](reports/no-depth-ablation-20260930-01/viewer-none/index.html)。


## 2026-10-08：九方向语义深度

新增 depth_language.py，在 Jev 组包边界转换已有数值摘要，保留几何算法、九扇区和其右至左顺序；新增 --depth-format numeric/semantic，默认 numeric，depth-input none 优先。语言等级上界 0.5/1/2/4 m（包含边界）；未知和 no_obstacle_seen 独立保留。深度摘要中的距离、角度和覆盖比例不进入语义请求，数值另存顶层 depth_numeric_debug；导航目标和本体数值保持。

- **76 项完整 unittest discover 通过**，包含原 69 项与新增 7 项。新增测试先失败（7 failures），实现后通过，覆盖分档边界、左右顺序、未知/未见障碍、运动状态、序列化隔离、默认/no-depth 模式、配置 CLI 和九扇区约束。
- 536 份历史输入在新组包与修改前源码之间相等；其中当前 v5 有深度和无深度各 250 份与历史原请求也精确相等。另 36 份简单路线来自初始九动作提示词，当前 v5 本就不同，不能作为当前动作集的直接对照。
- GPU 7、内部 gpu_id=0：简单 numeric、简单 semantic、复杂 semantic 各 4 步脚本验证，0 碰撞/无效，预设 stop 产生预期 early_stop。简单两组位姿、动作、执行结果和非深度状态完全一致。
- 两组语义共 8 份请求从保存原始 NPZ 重算，numeric_debug 精确匹配底层事实，语义输入精确对应这些事实，深度对象递归检查无数字。133 个受保护历史/任务/配置/其他代码文件哈希未变。
- 复杂语义 5 幅观察成功导出便携 HTML/MP4/GIF，视频 225 帧、7.5 秒，完整解码和源文件哈希验证通过；HTML 请求与日志相等、JavaScript 语法检查通过，未作浏览器手工交互验收。
- 真实 Jev API 请求为 0；上述 early_stop 均为脚本验证，不代表模型导航效果。

[报告和命令](reports/semantic-depth-20261008-01/README.md)、[验证脚本与结果](reports/semantic-depth-20261008-01/verification.json)、[语义回放样例](reports/semantic-depth-20261008-01/viewer-complex/index.html)。
