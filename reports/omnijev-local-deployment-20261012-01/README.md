# OmniJev-4B 本地部署与导航接入验证

本次加入 tinnel123 的 OmniJev-4B v1.1 本地图文决策后端。不是 OneJev 或同名的 shapsider 模型。沿用现有三条路线、七动作、深度模式、航点标记、记忆、执行层和成功条件。正式实验交给分配了 GPU 的运行进程执行。

## 已核验

- 独立环境可导入 torch 2.8.0+cu128、transformers 5.19.0、peft 0.21.2；官方 processor、LoRA 配置及原生 runtime 可在 CPU 加载。没有修改 Habitat 或 OneJev 的依赖环境。
- 基线 124 项测试通过；加入后完整回归 135 项通过。新增测试覆盖文字状态真正进入原生问题、三深度模式、JPEG 原字节、概率与 abstain、CLI、批次脚本、日志与回放身份、失败不重试、离线单步准备等。
- 27 个真实历史图文观察使用上游 `MSO1._encode_many` 处理：三条路线 × 三深度条件，每条件选择第一步、最后决策步和最长请求。每次一张图，七个 option 块，完整文字状态保留；最长输入序列为 3304 token。没有模型权重前向、没有 GPU 使用。
- 15 个已有 Jev/OpenAI/OneJev 条件的 wire 编码和提示词版本、模型身份与改动前一致。
- 数值和语义条件保留对应 depth；none 不传 depth，仍保留标记 RGB。图片只来自当前观察，原始 JPEG SHA256 保持。

## 部署协议与可解释性

原生 MSO1 不读取任意 JSON state，因此服务使用原问题说明 + `NAVIGATION_STATE_JSON` + 原完整 state。HTTP 接口 `/v1/systemone` 使用内联一张 JPEG；实际送入模型的图片与问题哈希返回并保存。候选及顺序保留现有七动作。服务只监听 loopback，无云端回退、无自动重试、无动作安全替换。

原生 choice 策略取七动作中最高概率者，不因更高 abstain 而另选动作。概率原样记录，七项与 abstain 的质量总和允许上游四位小数舍入误差。原生 `valid` 是概率归一化诊断，区别于 `outcome.valid` 的物理动作有效性。保持上游校准温度，不把动作概率重新归一化。

服务设置为 BF16 底座、FP32 决策头、SDPA、原生 branch；不安装可选 FLA。缓存数设为 1，因 v1.1 零缓存会在首次编码访问空缓存。未改动上游源码，未量化、未裁剪状态、未改变 JPEG 分辨率或目标标记。processor 自身预处理沿用上游配置。完整 metadata 记录 health、部署清单和源哈希。

## 尚未核验

尚未获知用户分配的 MODEL_GPU/NAV_GPU，未运行真实 GPU 模型前向、请求延迟/峰值显存、五步 GS 闭环及九组导航成绩。CPU 接入测试、模拟 HTTP 运行和模型真实导航效果属于不同证据层级，不能互相替代。权重下载与逐文件校验最终状态见 `verification.json`，本报告不在未校验时声称权重完整。

## 证据和命令

- [完整测试](tests.log)、[基线测试](baseline-tests.log)、[新增功能失败测试](red-tests.log)
- [CPU 图片和状态编码](cpu-input-audit.json)、[核验脚本](audit_inputs.py)、[日志](cpu-input-audit.log)
- [既有请求不变核验](legacy-request-parity.json)
- [历史输入保护哈希](protected-before.json)、[原代码备份](before/)、[基线 commit](baseline-commit.txt)
- [九条批次命令预检](commands-dry-run.txt)、[实际最终核验状态](verification.json)
- [启动、单步请求、五步闭环与两轮九组实验命令](../../docs/OMNIJEV_LOCAL.md)

九组正式任务为简单 100 步、复杂 250 步、长路线 500 步，输出命名前缀 `omnijev-local-rgbtarget-`。使用新的 batch-id，拒绝覆盖已有结果。回退只需选原 `--decision-model jev|openai|onejev`，不需要删除新环境或改动仿真器。

## 用户放置权重后的核验（2026-10-13）

离线核验通过。使用官方固定 revision 的文件列表检查 23 个运行文件：大文件/适配器使用官方 SHA256，小型配置与分词器使用官方 Git blob SHA1；生成 `local_models/omnijev-4b/weights-manifest.json`，供服务启动时离线复核。底座两个分片分别为 5,329,398,688 和 3,990,429,408 字节。

- 底座索引中的 738 个张量与两个 safetensors 分片一致；400 个 LoRA 张量的输入/输出形状与对应底座权重匹配。
- 决策头和 ordinal 头在 CPU 严格加载通过，额外 token embedding 为 2×2560；没有完整骨干前向。
- 实际独立环境的 CPU 预检通过，完整回归 135 项通过；重新验证 27 个历史图文观察，以及单步请求 `--prepare-only`。
- 355 个历史文件保持原哈希，两个批次各九条命令通过 dry-run。
- 用户明确选择自行执行 GPU 验证。因此模型加载、单步真实推理、五步 GS 闭环和正式成绩仍待执行；现有证据不表示 GPU 导航成功。

证据：[官方权重核验](user-weights-hash.log)、[权重结构](user-weight-structure.json)、[CPU 预检](user-weights-preflight.log)、[完整回归](user-weights-tests.log)、[图文编码](cpu-input-audit.json)、[单步输入准备](user-weights-prepare-only.json)、[第一轮命令](user-commands-01.txt)、[第二轮命令](user-commands-02.txt)。启动顺序与完整命令见 [OMNIJEV_LOCAL.md](../../docs/OMNIJEV_LOCAL.md)。
