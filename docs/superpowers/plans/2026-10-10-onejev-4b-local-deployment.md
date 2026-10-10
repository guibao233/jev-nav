# OneJev-4B 本地轻量部署与导航接入 Implementation Plan

> **For agentic workers:** 审批后使用 `superpowers:executing-plans` 逐项实施，步骤以复选框跟踪。本计划不要求子代理或额外的审批阶段。

**Goal:** 将本地 OneJev-4B 接入现有路径辅助导航模块，支持文字和带当前航点标记的 RGB，并交付简单、复杂、长路线 × 数值、语义、无深度的测试命令。

**Architecture:** 独立 Python 环境运行官方 `qev` 模型服务；现有 `habitat-gs` 环境通过本机 HTTP 请求选择动作。复用现有导航状态、提示词和图像标记，仅添加 OneJev 的协议适配、身份记录与运行入口。

**Tech Stack:** Python 3.12、官方 OneJev/qev、PyTorch BF16、Transformers、FastAPI/Uvicorn；导航端沿用标准库 HTTP、现有 Habitat-GS 与 unittest。

**Spec:** 本文“设计与范围”部分就是本次设计规格。状态：**待用户审批；尚未部署或修改导航代码**。核对日期：2026-10-10。

## Global Constraints

- 项目根目录 `ROOT=/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav`，实际解析到 `/share/guiyuanze/code/habitat-gs/jev_nav`。
- 用户要求先审批计划；审批前只读核查和写计划。审批后才下载权重、创建环境、安装依赖或改代码。
- 全部新增代码、模型运行环境、权重及验证结果放在 ROOT 下；不升级或安装包到已有 `habitat-gs` 环境。
- OneJev-4B 首版采用 BF16 主体和官方默认 FP32 输出头，不训练、不量化；单实例、串行请求、单张明确指定的模型 GPU。
- 保持七动作：前进/后退 0.25 m，左右转 15°，上下俯仰 15°，停止；停止判据仍是模型选择 stop 且最终 NavMesh 距离 ≤0.30 m。
- 保持路线重关联策略、当前航点、3.0 m 路径预览、0.5 m 采样、0.75 m 航点前视距离、最近 5 个自身动作结果和 `allow_sliding=true`。
- 保持 640×480 RGB、90° 水平视场、相机高度 1.5 m、任务中的初始位姿/俯仰及 mesh 深度处理；图像继续使用 `target_marked_rgb_v1`。
- 数值模式仍为九扇区；语义模式仍复用 `depth_language.py`；无深度模式必须在请求边界去掉 depth，不能将本地数值诊断重新送入模型。
- 不修改 Habitat-GS 源码、现有任务、场景资产或历史运行；每次运行使用新输出目录。
- 本地服务仅监听 `127.0.0.1`，默认端口 8011；不需要 OpenRouter 密钥，不发生云端调用或自动回退。

## Review Focus

1. 服务不可达、模型名不匹配：在加载 GPU 渲染器前明确失败，不能误调用 OpenRouter。
2. 图片缺失、占位符或哈希不匹配：停止联调并保留证据，不能静默退成文字输入。
3. 协议转换改变深度/动作/提示词：用固定状态和历史请求比较，保证只有模型、传输形式及图片引用发生预期变化。
4. 显存不足、长请求超限或超时：保留失败，不截断输入、不更换精度、不自动重跑整轮。
5. 新模型身份和服务失败：回放、summary 区分 OneJev；服务失败不能伪造执行动作或计成模型导航失败。

---

## 设计与范围

### 1. 为什么选择这个部署方式

推荐官方 PyTorch + 本机 HTTP。它直接提供 Choice 接口和多模态服务，与当前模块的“状态 + 动作候选 → 动作选择”结构接近。官方也支持 GGUF/llama.cpp，但首版不引入另一套编译与量化条件；若 BF16 实测无法满足资源限制，再单独讨论量化方案。[官方部署说明](https://github.com/OmniJev/OneJev)

“轻量化”在本次指 4B 模型、独立小服务、无训练、无分布式推理和最少导航改动，不代表已经量化。模型仓库公开权重约 10.4 GB，这只是文件体积；实际显存还包含输出头、视觉处理和前向计算，不能据此保证能与 GS 共用 24 GB 显卡。[模型文件](https://huggingface.co/OmniJev/OneJev-4B/tree/main)

当前只读检查识别到 8 张 RTX 4090，每张约 24 GB；显存占用会随其他任务变化。默认建议模型和 Habitat 各使用一张用户分配的卡，便于测量和避免竞争；若只能使用一张卡，先测模型与 GS 的联合峰值，验证通过后再跑完整路线。检查到空闲卡不等于本计划获准占用该卡。

### 2. 部署参数与资源控制

部署目录拟定为：

```text
local_models/onejev-4b/
  env/                   独立 Conda 环境，使用完整前缀启动
  source/                固定 Git commit 的官方 OneJev 源码
  weights/               固定 HF revision 的权重、配置、tokenizer、processor
  cache/                 本次 HF/pip 缓存
  requirements.lock.txt  实际通过验证的依赖版本
  deployment.json        版本、权重/配置哈希、启动参数、GPU 与验证记录
  logs/                  启动与模型服务日志，每次新文件
```

预留约 40 GB 磁盘作为首版安装预算，实施前重新检查可用空间；这是预算，不是已测量占用。HF 下载只取运行必需文件，不下载训练集或展示资产；校验文件完整性与 revision 后从本地目录启动，避免服务运行时追踪 main。

上游声明 Python ≥3.10、Transformers ≥5.0、PyTorch ≥2.6、torchvision ≥0.21。首版选择 Python 3.12；具体包版本在独立环境中根据固定 commit 和 Qwen3.5 类/API 兼容性验证后锁定，不能把版本下限当作已验证组合。优先官方 CUDA wheel，不默认编译 FlashAttention/FLA；若依赖确实要求额外内核，只在独立环境处理并记录。[上游依赖](https://github.com/OmniJev/OneJev/blob/main/pyproject.toml)

拟定服务命令由 `scripts/serve_onejev.sh` 包装，底层为：

```bash
CUDA_VISIBLE_DEVICES="$MODEL_GPU" QEV_DEBIAS=1 \
  local_models/onejev-4b/env/bin/qev serve \
  --model local_models/onejev-4b/weights \
  --name OmniJev/OneJev-4B \
  --device cuda:0 --dtype bfloat16 --head-dtype float32 \
  --host 127.0.0.1 --port 8011 \
  --no-cuda-graphs --no-gpu-preprocess \
  --max-branch-tokens 8192 --max-request-tokens 8192
```

关闭 CUDA Graph 以减少不同输入长度的缓存开销；图片预处理放 CPU。保留官方 fork 模式 auto 及其启动一致性检查，记录最终实际模式。8192 是首版服务输入上限，必须先用真实导航请求验证；超出时明确失败，不能裁剪提示词/历史/图片。图像只发送现有 JPEG 原始字节，不新增客户端降采样；服务 processor 的配置随权重一起归档。上述 CLI 参数已在上游源码核对，但尚未在本机执行。[CLI](https://github.com/OmniJev/OneJev/blob/main/qev/cli.py)、[推理实现](https://github.com/OmniJev/OneJev/blob/main/qev/mm_engine.py)

`MODEL_GPU` 和 `NAV_GPU` 必须显式指定物理卡号。两个进程均通过 `CUDA_VISIBLE_DEVICES` 限制可见卡，内部使用 GPU 0；Habitat 继续使用 `config.single-gpu.json`。不自动挑卡、不修改全局 CUDA 配置、不终止其他进程。

### 3. 模型切换与请求协议

拟新增：

```text
--decision-model onejev
--onejev-url http://127.0.0.1:8011
--onejev-timeout-s 30
```

默认模型继续由原配置决定。`onejev` 固定请求模型名 `OmniJev/OneJev-4B`；网址仅在该模型下使用。导航端通过标准库 HTTP 调用 `POST /v1/systemone`，不导入 torch/transformers/qev。

复用 `jev.make_request(state, cfg)` 产生任务状态、深度、历史、七动作和 instructions。本地编码器做如下协议转换：

```json
{
  "model": "OmniJev/OneJev-4B",
  "state": {
    "task": "保留现有内容",
    "reference": "保留现有内容",
    "robot": "保留现有内容",
    "recent_actions": "保留现有内容",
    "recent_motion": "保留现有内容",
    "visual": {"marker": "保留现有内容", "image": "<image:1>"},
    "depth": "仅数值/语义模式包含"
  },
  "questions": {"action": "保留现有 choice 问题和七动作 criteria"},
  "media": [{"type": "image", "data": "data:image/jpeg;base64,..."}]
}
```

这是结构示意，省略项实际仍为原有 JSON 对象/数组。图片仅引用一次，复用同一观察时刻 `save_model_image()` 的 JPEG 字节，不重复编码 JPEG；`--rgb-input none` 时不添加图片引用和 media。OneJev 要求的 `media + <image:1>` 与 OpenRouter 现有 state 数组不同，因此需要独立编码器。[请求/响应 schema](https://github.com/OmniJev/OneJev/blob/main/qev/schema.py)、[图片协议](https://github.com/OmniJev/OneJev/blob/main/qev/media.py)

三个深度条件默认都配合 `--rgb gs --rgb-input target_marked`，主要与已有 OpenAI 图文组比较。**“无深度”仍含 RGB，不能称为无感知。** 同时保留 OneJev 的 `--rgb-input none`，后续可用来单独比较本地模型的纯文字条件，首批不自动扩展成更多实验。

执行返回的 `answers.action.choice`，保留概率、confidence、usage 和 qev 元信息；不采样、不自动修改动作、不用规则恢复。概率必须是有限数、位于 [0,1]，覆盖七候选且总和在数值容差内。格式损坏记 service_failure；若结构可解析但返回未知动作名，沿用现有无效动作规则记录并消耗动作预算，不替换为合法动作。

本地请求默认不自动重试；30 秒为联调超时初值，完整实验前根据暖启动延迟确认。如果上调，单独记录配置。服务失败不执行动作、不消耗动作预算并终止该轮，沿用现有 service_failure 路径；动作被阻挡或超限仍消耗预算并继续交给模型决策。

### 4. 身份、证据与指标

拟新增 `provider=onejev_local`、`api_provider=local_qev`、`model_label=OneJev-4B`、`is_onejev_evaluation=true`；`is_model_evaluation=true`，`is_jev_evaluation=false`，`is_openai_decisions_evaluation=false`。脚本 smoke 仍为 scripted_smoke，不算模型评估。

metadata 保存模型 revision、qev commit、依赖锁定文件/部署清单哈希、精度、GPU、endpoint、输入模式、候选顺序和服务 health。服务清单是启动时记录的部署证据，health 返回的是服务自报信息，不把 health 当作权重哈希认证。

steps 保存现有可读 request、image_input 清单和 JPEG 哈希、实际 wire 请求 SHA256、原始 response、choice、延迟和执行结果。回放通过该清单重建请求；不把大段 Base64 塞入 steps.jsonl。服务返回 qev.prompt_sha256 时保留，区分导航提示词版本和服务内部模板版本。

summary 沿用成功、零碰撞成功、动作数、碰撞数、无效动作数、累计路程、最终测地距离、SPL、是否曾到达但未停止、模型请求和整轮循环 P50/P95。部署验证另外记录冷启动、暖启动请求延迟、模型进程峰值显存以及联合渲染显存。不能用单步回放正确率代替闭环导航结果，也不能保证新模型一定优于已有方案。

## 文件改动清单

| 文件 | 计划职责 |
|---|---|
| 新增 `onejev.py` | 本地编码、health/model 检查、HTTP 客户端、响应校验；不包含导航逻辑 |
| 修改 `jev.py` | 加入模型身份、`create_decision_client(cfg)` 工厂及编码分发；保留原 DecisionsClient/JevClient 与 OpenRouter 分支 |
| 修改 `run.py` | CLI、客户端选择、真实 endpoint/身份/部署清单记录、协议对应的 wire hash 与控制台提示 |
| 修改 `rgb_input.py` | 允许 OneJev 图像输入；投影与绘图算法保持 |
| 修改 `scripts/run_model_ablation.sh` | 支持 onejev、独立本地服务参数和密钥条件；原 jev/openai 命令保持 |
| 新增 `scripts/serve_onejev.sh` | 从固定本地权重启动服务，显式 GPU、端口、日志；不隐式安装或下载 |
| 新增 `scripts/probe_onejev.py` | 发送新构造或历史归档状态/图片，验证输入哈希与选择结果；不执行机器人动作 |
| 新增 `test_onejev.py` | 本地协议、错误分支、模型身份和请求隔离测试 |
| 修改 `test_decision_models.py`、`test_rgb_input.py`、`test_ablation_script.py` | 覆盖切换、图片允许条件、脚本 dry-run；保留历史回归用例 |
| 更新 `README.md`、`VALIDATION.md` | 安装/启动/测试命令、完成程度和限制 |

`core.py`、`environment.py`、`clearance.py`、`depth_language.py`、原配置与任务文件在本次设计中无需修改。已有 replay 使用显式 model_label/is_model_evaluation，可先直接复用；通过回放验证后，仅在发现身份显示问题时做局部修复。

## Task 1：独立环境与固定权重的本地服务

**Files:** `local_models/onejev-4b/`、`scripts/serve_onejev.sh`、部署说明。

- [ ] 审批后再次检查 GPU 分配、可用显存、磁盘、端口和现有目录；不覆盖已有部署目录。
- [ ] 记录导航源码/配置/三任务哈希，并为将修改文件创建单独备份。当前目录不是 Git 仓库，不要求创建提交或清理用户文件。
- [ ] 获取并记录完整上游 commit/HF revision，在独立前缀创建 Python 3.12 环境，安装适配 CUDA 的依赖与固定源码，导出依赖锁定。
- [ ] 下载所需模型文件到 weights，检查 config、processor、tokenizer 和权重完整性及哈希；记录 calibration.json 是否存在，若不存在则记录官方默认校准，不能自行训练或伪造校准文件。
- [ ] 实现显式 GPU 的服务启动脚本；缺少 GPU、权重、锁文件或端口被占用时，在模型加载前报错。
- [ ] 在用户分配 GPU 上启动，检查 `/health` 和 `/v1/models` 的模型名；验证固定七候选的文字/图片请求、概率与图片计数。
- [ ] 用当前实际最长归档请求验证 8192 上限，测暖启动延迟与显存；超限/OOM 时保留日志，提出明确参数调整再继续，不能静默裁剪。

**验收：** 本机独立服务可重复启动，返回七动作 Choice；环境与模型版本可追踪，已有 habitat-gs 包版本和文件保持。

## Task 2：导航端本地接口与模型身份

**Interfaces:** `onejev.encode_local_request(payload, image_bytes=None) -> bytes`；`OneJevClient(cfg).decide(payload, image_bytes=None) -> dict`；`jev.create_decision_client(cfg)` 返回对应客户端。结果继续满足 runner 的 choice/provider/response/latency_s/attempts 合同，失败使用现有 ServiceFailure。

- [ ] 先添加并运行失败用例：七候选、一次图片占位符、原 JPEG 字节哈希、三深度模式、输入对象不被修改、本地调用不需要 OPENROUTER_API_KEY。
- [ ] 添加健康检查、模型不匹配、拒绝非本机 URL、超时、HTTP 422/500、损坏 JSON/概率、未知动作保留和不自动回退用例。
- [ ] 实现本地标准库客户端与身份分发；显式将 local endpoint 和 OpenRouter endpoint 分开。健康检查在渲染初始化前执行，检查不发决策请求。
- [ ] 在 run.py 接入参数、客户端、日志、协议对应 hash。非 onejev 情况若误传本地专用参数则明确拒绝，不悄悄忽略。
- [ ] 扩展 rgb_input 的模型允许条件；原 JPEG 投影/保存函数不改。
- [ ] 在 habitat-gs 中运行离线相关测试和完整 unittest discover，测试只用 fake HTTP，不请求任何真实云端模型。

**验收：** 既有 Jev/OpenAI 文字与图像请求在原条件下保持；OneJev 身份正确、三种文字条件和图片输入无泄漏；失败不执行替代动作。

## Task 3：归档输入核查与最小闭环验证

**Files:** `scripts/probe_onejev.py`、独立 `runs/onejev-*` 和 `reports/onejev-local-validation-*`。

- [ ] 实现 probe，从历史运行读取指定 before_action 帧，校验图像 SHA256 后转换模型与本地传输形式；输出新的 JSON，不改历史 steps。
- [ ] 至少核查普通行走、转弯/受阻、最终到达三类归档状态；各深度条件均检查对应真实输入。归档动作不是标签，不要求 OneJev 与旧模型选同一动作。
- [ ] 对原地/目标画面外帧检查 media 数量、占位符和 qev 模板 hash；核实服务确实处理一张图。此验证只证明输入链路，不证明有效利用视觉。
- [ ] 在没有 API key 的子进程执行 scripted smoke，验证新身份和回放；通过后执行简单路线最多 5 步真实 OneJev 闭环联调，保留 action_budget/early_stop 等真实状态。
- [ ] 生成现有可视化，确认 OneJev 标题、模型输入图片、NavMesh、航点、碰撞和无效动作标记正确；统计模型与 GS 同时运行的显存和循环耗时。
- [ ] 将离线、服务、GPU 渲染、5 步闭环分别记录为通过/失败/未执行，不把成功加载或短 smoke 写成路线成功。

**验收：** 能逐步追踪“本轮状态与图片 → 本地请求 → OneJev 响应 → Habitat 执行”，不发生云端调用，日志可回放。

## Task 4：交付固定三路线的用户运行命令

- [ ] 扩展现有脚本的 onejev 分支，确保本地模式不检查 OpenRouter key；图文模式允许 openai 或 onejev。脚本仍串行执行，输出目录冲突则开始前整体拒绝。
- [ ] dry-run 用例检查三路线、预算、输入模式、模型和图片标志；对已有 jev/openai 分支做回归，不改默认行为。
- [ ] 交付 9 个组合的 dry-run/实跑入口、单轮例子和第二轮不同 batch ID。完整批次由用户执行，不自动增加样本或重跑失败轮。
- [ ] README/VALIDATION 记录具体已验证安装版本、GPU、部署清单、运行命令和资源限制，并复查本文各项验收状态。

**固定实验矩阵：**

| 路线 | 任务文件 / episode | 最短基准距离 | 动作预算 |
|---|---|---:|---:|
| 简单 | `tasks/debug-10.json` / `episode-000` | 4.196 m | 100 |
| 复杂 | `tasks/challenge-clearance-aligned-20260930-01/tasks.json` / `turn-000` | 9.798 m | 250 |
| 长路线 | `tasks/extended-clearance-aligned-20261008-01/tasks.json` / `extended-000` | 16.323 m | 500 |

距离是原 NavMesh 最短路径评估基准；复杂/长路线实际跟随已保存的 clearance_weighted 参考路线，不能将其长度混成最短距离。各路线分别使用 numeric、semantic、none，均默认 GS 标记 RGB。

## 实施完成后拟交付的命令

以下新增命令当前**不可执行**，审批实施后才提供对应脚本/参数。先显式设置由用户分配的 `MODEL_GPU` 和 `NAV_GPU`，可以不同，也可以经联合显存验证后相同。

终端 A，启动模型服务：

```bash
cd /data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav
MODEL_GPU="$MODEL_GPU" bash scripts/serve_onejev.sh
```

终端 B，在 habitat-gs 环境中做 5 步联调：

```bash
cd /data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav
CUDA_VISIBLE_DEVICES="$NAV_GPU" python run.py --config config.single-gpu.json run \
  --decision-model onejev --onejev-url http://127.0.0.1:8011 \
  --onejev-timeout-s 30 --rgb gs --rgb-input target_marked \
  --tasks tasks/debug-10.json --episode episode-000 \
  --depth-input mesh --depth-format numeric --max-steps 5 \
  --out runs/onejev-simple-rgbtarget-numeric-smoke-01
```

检查完整矩阵命令（不启动仿真、不发请求），随后由用户运行第一轮：

```bash
CUDA_VISIBLE_DEVICES="$NAV_GPU" \
  NAV_RGB_INPUT=target_marked ONEJEV_BASE_URL=http://127.0.0.1:8011 \
  bash scripts/run_model_ablation.sh onejev local-round-01 --dry-run

CUDA_VISIBLE_DEVICES="$NAV_GPU" \
  NAV_RGB_INPUT=target_marked ONEJEV_BASE_URL=http://127.0.0.1:8011 \
  bash scripts/run_model_ablation.sh onejev local-round-01
```

只测简单路线可以增加 `ROUTES=simple`；第二轮更换 `local-round-02`。每轮先完成本地服务预检，不覆盖目录。正式矩阵保持与 OpenAI 图文组相同的任务/文字条件；OneJev 内部模板、校准与预处理属于模型部署差异，须记录而不能宣称完全相同。

## 完成标准与回退

- 离线回归、本地文字/图片服务、三输入链路、5 步 GS 闭环和回放均有可核查验证记录；资源条件不足的部分明确列为未完成。
- 交付服务脚本、本地模型切换、9 组命令和验证文档；本阶段完成不以 OneJev 必须导航成功或胜过 OpenAI 为条件。
- 服务启动/依赖/模型失败时先修复独立部署，不修改现有导航策略作为补救；资源不足需要改变量化/图片分辨率时，另行讨论实验条件。
- 回退时停止本次模型服务并选择原 `--decision-model jev|openai` 即可；需要撤销改动时只还原本次备份，保留全部新旧运行证据，不删除环境/权重作为默认动作。
- 本次计划审批范围包含独立安装、代码接入、离线测试、本地 probe 和最多 5 步的真实联调；完整 9 组实验仍交给用户执行。实施前确认实际 GPU 分配即可，不要求提供任何 API key。

## 计划自审

- 已核对当前 `jev.py`、`run.py`、`rgb_input.py`、`environment.py`、模型消融脚本、配置及三任务文件。
- 当前配置实际 gpu_id=0，滑动已开启；不沿用旧 README 中曾经默认 GPU 2 的说法。
- 已核对官方 HTTP 路由、模型名检查、Choice schema、图片占位符及部署 CLI；尚未验证本机推理兼容性、显存和速度。
- 路线/深度/执行策略保持，仅扩展模型和输入传输；没有把服务重试、恢复控制器或量化偷偷纳入方案。
- 本轮只新增这份计划，实施任务均保持未勾选，等待用户审批。
