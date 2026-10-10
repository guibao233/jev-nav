# OpenRouter Jev / OpenAI Decisions 切换验证（2026-10-09）

范围：在已有七动作 v5 导航实验中加入模型选择；OpenAI 使用 `openai/gpt-6-luna-decisions`，Jev 保持 `typesafe/jev-1.13`。两者都调用 OpenRouter Decisions，使用现有 `OPENROUTER_API_KEY`。没有新增 SDK、改变环境、重建 NavMesh 或修改历史任务/运行。

## 使用

在 `habitat-gs` 环境中运行：

```bash
cd /data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav
CUDA_VISIBLE_DEVICES=7 bash scripts/run_model_ablation.sh openai 20261009-01 --dry-run
CUDA_VISIBLE_DEVICES=7 bash scripts/run_model_ablation.sh openai 20261009-01
CUDA_VISIBLE_DEVICES=7 bash scripts/run_model_ablation.sh openai 20261009-02
# 相同九组 Jev 对照：
CUDA_VISIBLE_DEVICES=7 bash scripts/run_model_ablation.sh jev 20261009-01
```

每批九组：simple / complex / extended × numeric / semantic / none；动作预算分别 100 / 250 / 500，RGB 默认 gs。任务与前次汇总相同，初始姿态和路线均来自既有任务 JSON。`--dry-run` 不要求密钥、不加载 GPU、不创建运行输出。脚本检查所有输出路径及控制台日志，阻止覆盖；服务或运行错误时停止后续派发。

切换参数为 `run.py run --decision-model jev|openai`，`smoke` 同样支持。不指定继续使用 `config.model`。模型状态、动作规则和提示词不改变；无深度仍保留路径与自身动作反馈。有深度全部来自 mesh；GS RGB 不送入模型。

## 已验证

- `python -B -m unittest discover -v`：86 项通过，含新增 10 项测试。覆盖模型选择、默认 Jev 兼容、OpenRouter 请求/响应处理、原始响应保留、真实/脚本身份标志、汇总和回放保存、缺密钥提前退出、九组脚本派发与阻止覆盖。日志见 [tests-stage.log](tests-stage.log)，安装后另存 tests-installed.log。
- 全流程保存测试使用确定性的测试环境代替 GPU、模拟 HTTP 代替付费服务；实际 runner、组包、记录、图像保存和回放代码参与测试。不是模型导航性能结果。
- [历史请求比对](history-parity.json)：19 轮 / 3852 份默认 Jev 请求与已保存请求完全一致；相同状态换为 OpenAI 时仅 `model` 字段不同。可运行 [verify_history.py](verify_history.py) 复核，不使用 GPU 或 API。
- [回放脚本执行检查](replay-check.json)：Node DOM 桩实际执行生成的 JavaScript，旧 Jev、新 OpenAI 和 smoke 的身份标签均正确。`replay-fixture-*` 是合成测试夹具，非真实模型实验；未做原生浏览器手工测试。
- Shell 语法检查通过；通过外部命令替身实际执行全部九组派发，逐项核对路线文件、episode、预算、模型、深度模式与输出名称。未触发真实仿真或 API。
- 修改前源码和文档保存在 [before/](before/)。源文件哈希及安装核查见 installation.json；旧任务和运行受保护。

## 记录协议

metadata 和 summary 记录 `provider`、`requested_model`、`model_label`、`is_model_evaluation`、`is_jev_evaluation`、`is_openai_decisions_evaluation`。OpenAI 真实运行 `provider=openai_decisions`，且 `is_jev_evaluation=false`；smoke 两种模型的真实评估标志均为 false。`api_provider=openrouter` 与原始响应中的上游 provider 分开。

summary 的 `response_models` 保存实际收到的模型 ID，原始回答/置信度/概率/usage 继续保留于步骤日志。新增统一的 `model_request_latency`；Jev 保留 `jev_request_latency`，OpenAI 对该旧字段使用 null，避免后续误读成 Jev 实验。

## 未验证

本次真实模型请求 0 次、GPU 仿真 0 次。OpenRouter 当前账号的模型访问权限、在线服务返回、实际延迟与导航能力，等待用户执行命令验证。不能将模拟 HTTP、脚本 smoke 或本报告中的合成回放当作 OpenAI 导航结果。

接口依据：[OpenRouter 模型页](https://openrouter.ai/openai/gpt-6-luna-decisions)、[Decisions 统一协议](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request)。
