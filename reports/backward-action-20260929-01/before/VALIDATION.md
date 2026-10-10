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
