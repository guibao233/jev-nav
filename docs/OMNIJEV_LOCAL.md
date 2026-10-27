# OmniJev-4B 本地图文导航

接入 tinnel123 的 OmniJev-4B v1.1，使用原生 `mso.infer.MSO1` 和独立 HTTP 服务。它与组织名为 OmniJev 的 OneJev 是两个不同项目。模型权重为 LoRA、决策头、额外 token embedding；还需原始 Qwen3.5-4B 底座，不能用已微调的 OneJev 权重代替。

固定来源：

- [上游代码](https://github.com/tinnel123666888/OmniJev/tree/5da4b5c4cd5cc2acb96d18beecbdf5972231ef1b)，v1.1 commit `5da4b5c4cd5cc2acb96d18beecbdf5972231ef1b`。
- [适配器](https://huggingface.co/tinnel123/OmniJev/tree/v1.1)，revision `ffe5f436eaf22e20e2f041f8e74e121fd057a6cb`。
- [底座](https://huggingface.co/Qwen/Qwen3.5-4B)，revision `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`。

## 导航与输入

沿用固定的简单、复杂、长路线，七动作和原成功条件；不自动恢复、不替换动作、不修改路线。模型每步收到当前一张带航点标记的 GS RGB JPEG，以及原导航文字状态。数值深度、语义深度、无深度三个模式保持不变；无深度仍保留 RGB。

原生 `MSO1.system_one` 读取 `state.images`，不会自动读取任意 JSON 状态字段。因此桥接层将现有问题说明原样保留，并在其后追加 `NAVIGATION_STATE_JSON` 和完整状态对象。目标、机器人状态、短期动作历史、深度都保留；七个 criteria 的内容和顺序保持。服务读取客户端发送的 JPEG 原始字节，不重新编码 JPEG，不加入地图或历史图片。processor 采用上游默认 `max_pixels=602112`；其实际处理结果记录在 CPU 核验中。

OmniJev 不生成动作文本。直接执行上游返回的 `choice`，保留完整 `probabilities`、`abstain`、`valid`、confidence 和模型内部耗时。七动作概率与 abstain 的和应约等于 1；上游保留四位小数，客户端容差为 0.001。`valid` 指概率归一化的有效性，不是机器人动作是否成功。即使 abstain 比动作概率高，也沿用上游返回的最高概率动作；不新增第八个动作，不按 abstain 自动停止或重试。

HTTP 默认仅监听 `127.0.0.1:8012`。导航端只使用标准库；只在模型独立环境导入 torch/transformers/peft。服务启动前核对源码、权重、依赖和端口。使用 BF16 底座、FP32 决策头、SDPA，关闭可选 FLA，不编译额外内核；强制使用原生 branch 推理，缓存最多一张图片。上游零缓存会在首次请求中淘汰空缓存，因此使用最小可用值 1。以上都是部署参数，没有修改上游源码。

## 本地目录与预检

```text
local_models/omnijev-4b/
  env/                    独立环境，复制已有依赖后只在副本安装 PEFT
  source/                 固定 v1.1 推理代码与许可证
  adapter/                OmniJev v1.1 适配器、头和 processor/tokenizer
  base/                   原始 Qwen3.5-4B 底座
  deployment.json         固定版本、实际依赖、部署参数
  requirements.lock.txt   实际依赖锁
  weights-manifest.json   权重逐文件 SHA256
  logs/                   服务日志与启动信息
```

环境版本以部署清单为准。复制依赖仅为了复用已验证的 Python/CUDA 包，副本目录独立，不修改 OneJev 或 habitat-gs 环境；残留的 qev 包不会被 OmniJev 服务调用。上游代码和权重保留各自许可证，运行资产不进入 Git。

离线检查（权重下载完成后）：

```bash
cd /data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav
local_models/omnijev-4b/env/bin/python scripts/check_omnijev_deployment.py --cpu-only
```

若需要续下缺失文件，可重新执行下载脚本；已有完整文件按哈希复用，未完成 `.partial` 文件重新下载。可通过 `--endpoint` 指定 HF 兼容公共镜像，仍要求固定 revision 和 SHA256。不要用不同版本覆盖此部署：

```bash
local_models/omnijev-4b/env/bin/python scripts/download_omnijev.py
```

## 启动与真实输入验证

先在终端 A 指定分配给模型的物理卡号，然后启动。服务不下载、不安装、不自动选 GPU：

```bash
cd /data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav
export MODEL_GPU=你的模型卡号
bash scripts/serve_omnijev.sh
```

终端 B 使用 habitat-gs 环境，先对已经完成的实验做一次请求回放，确认真实图片进入模型，不移动机器人：

```bash
cd /data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav
conda activate habitat-gs
python scripts/probe_omnijev.py \
  --run runs/openai-decisions-rgbtarget-simple-rgbgs-numeric-20261009-01 \
  --step 0 --out runs/omnijev-probe-step0-01.json
```

加 `--prepare-only` 只验证输入/哈希，不调用服务。成功响应中的 `omnijev.images=1`、`input_image_sha256` 与原 JPEG 哈希对应，`adapted_questions_sha256` 对应加入完整状态后的问题，`usage.input_tokens` 为原生 runtime 自报 token 数，`output_tokens=0`。

确认单次请求成功后再跑五步闭环；NAV_GPU 同样为分配的物理卡，进程内部使用 0。两卡可以不同；同卡需要确认模型和 GS 的联合显存能容纳。

```bash
export NAV_GPU=你的渲染卡号
CUDA_VISIBLE_DEVICES="$NAV_GPU" python run.py --config config.single-gpu.json run \
  --decision-model omnijev --omnijev-url http://127.0.0.1:8012 \
  --omnijev-timeout-s 60 --rgb gs --rgb-input target_marked \
  --tasks tasks/debug-10.json --episode episode-000 \
  --depth-input mesh --depth-format numeric --max-steps 5 \
  --out runs/omnijev-simple-rgbtarget-numeric-smoke-01
```

首次请求可能比暖启动慢。默认超时 60 秒、无自动重试；失败保存为 service_failure，不执行替代动作。启动 health 是服务自报信息，部署清单和文件哈希另行核对。

## 三路线 × 三深度输入

查看第一轮全部九条命令，随后执行第一、第二轮；脚本提前检查所有输出目录，拒绝覆盖。

```bash
CUDA_VISIBLE_DEVICES="$NAV_GPU" \
  bash scripts/run_model_ablation.sh omnijev local-round-01 --dry-run

CUDA_VISIBLE_DEVICES="$NAV_GPU" \
  bash scripts/run_model_ablation.sh omnijev local-round-01

CUDA_VISIBLE_DEVICES="$NAV_GPU" \
  bash scripts/run_model_ablation.sh omnijev local-round-02
```

OmniJev 模式默认 `NAV_RGB=gs`、`NAV_RGB_INPUT=target_marked`。可用 `ROUTES=simple` 限定路线、`MODES=semantic` 限定深度模式；默认执行 numeric、semantic、none。简单/复杂/长路线预算分别为 100/250/500；任务文件、起终点、参考路线和滑动设置与现有图文对照相同。自定义端口用 `OMNIJEV_PORT` 启动服务、`OMNIJEV_BASE_URL` 指定客户端地址，超时用 `OMNIJEV_TIMEOUT_S`。

保存 `provider=omnijev_local`、`api_provider=local_mso1`、`is_omnijev_evaluation=true`。metadata 包含 health 和部署清单；steps 包含可读原请求、图片清单/哈希、实际 wire 请求哈希、原始响应、动作与执行结果；不写入 Base64 大字符串。既有指标和回放工具通用，按 `model_label=OmniJev-4B` 显示。

接入、CPU 图片/文字处理与单元测试不等同于真实 GPU 推理或导航成绩。部署核验状态见 [本次验证报告](../reports/omnijev-local-deployment-20261012-01/README.md)。
