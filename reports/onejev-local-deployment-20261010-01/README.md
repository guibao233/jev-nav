# OneJev-4B 本地接入与部署准备验证

代码、独立环境和固定权重已准备完成；**尚未执行 GPU 模型加载、真实决策或 Habitat 五步联调**。按用户最新要求，本轮核查权重并交付运行命令，由用户选择 GPU、启动模型和执行导航；本轮没有初始化 CUDA、启动模型或渲染器。以下通过项均为离线/CPU 证据，不包含 OneJev 导航成功率。

## 原版本固定

- 本地仓库：`/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav`，物理路径 `/share/guiyuanze/code/habitat-gs/jev_nav`。
- 原版提交：`3589b100ae56d05a8f5179b673aced26745d58a0`；标签 `baseline-20261010-before-onejev`；当前分支 `feature/onejev-local`。
- 原源码、配置、任务、报告、审批计划进入 Git；约 39 GB 的 runs 留在原位置，通过基线清单记录 metadata/summary/steps 哈希；独立环境、模型和缓存不进入 Git。
- [完整性核查](baseline-integrity.json)：280 份历史运行记录，以及 47 份导航算法、执行层、配置、任务/回放文件与原版一致。原版 103 项测试通过；本次源码回归 124 项通过。

## 部署版本与输入

| 项目 | 固定配置 |
|---|---|
| 模型 | OmniJev/OneJev-4B |
| HF revision | c88e18653ceb7a8770716287f55fdefc79d6b588 |
| 官方 qev commit | de0c1125855e3f496f65a79f9aab2fbbc08e55ba |
| Python / PyTorch | 3.12.15 / 2.8.0+cu128，CUDA runtime 12.8 |
| Transformers / qev | 5.19.0 / 0.1.1 |
| 精度和执行 | BF16 主体，FP32 输出头；禁用 CUDA Graph；CPU 图片预处理 |
| token / debias | branch/request 8192；QEV_DEBIAS=1 |
| 校准 | 固定版本没有 calibration.json，官方 Choice 默认温度 1.0 |
| 服务 | http://127.0.0.1:8011，POST /v1/systemone |

权重 `model.safetensors` 为 10,350,019,328 bytes，完整 SHA256 为 `c725978346bb87ff598b04b6ffe7ea89461368e9b20a0081a3c6a85d377c8f91`，与官方 LFS 一致。最终完整权重由用户提供，本轮直接核验完整文件；此前代理下载已按用户要求停止，分片未用于拼接本次权重。独立环境使用同一版本的 USTC PyPI 依赖，没有更换精度或模型。Tokenizer LFS、small-file Git blob 与完整 safetensors 数据边界均检查通过。下载/安装日志留在 local_models/onejev-4b/logs。

安装位置为 `local_models/onejev-4b/env`，权重为 `local_models/onejev-4b/weights`。记录 [deployment.json](deployment.json)、[权重清单](weights-manifest.json)、[实际依赖锁定](requirements.lock.txt)。[环境检查](environment-validation.json)通过 pip check、64 个包版本、13 个已安装 qev 源码文件哈希、上游源码 clean 和 processor CPU 导入；没有向 habitat-gs 环境安装包。

导航仍使用固定参考路线、有序预览和局部航点；七动作包括前进、后退、左右转、上下俯仰、停止。平移 0.25 m、转角/俯仰 15°、最近五条自身动作历史、原停止规则与碰撞反馈沿用原配置。OneJev 使用原 instructions、criteria 和 state；传输时追加一个 `<image:1>` 和已保存目标标记 JPEG 的原始字节，官方 qev 内部模板单独记录。无深度条件仍有 GS RGB，只去除深度文字。

## 验证结果与边界

| 验证 | 状态 | 证据 |
|---|---|---|
| 原版冻结 | 通过 | 原版提交、基线 103 项测试和哈希清单 |
| 本地适配及原 Jev/OpenAI 回归 | 通过 | [124 项完整测试](onejev-suite-final.log)；fake HTTP，不调用云端 |
| 显式选卡、CLI、九组 dry-run | 通过 | [命令清单](commands-dry-run.txt)；dry-run 不使用列出的 GPU |
| 独立环境、processor、依赖与权重 | 通过 | 环境/权重清单；未加载模型到 GPU |
| 归档输入与媒体链路 CPU 检查 | 通过 | [12 类实例和最长输入](cpu-archive-validation.json)、[三模式首帧](cpu-processor-validation.json) |
| 原 JPEG 哈希和尺寸 | 通过 | [3285 张保存输入](archived-jpeg-integrity.json)；全部 640×480 |
| fake 环境本地 runner 与回放身份 | 通过 | 测试检查 OneJev 标题、响应身份、图片/wire SHA、停止和服务失败不执行动作 |
| 本地服务 health/models、真实七动作概率 | 未执行 | 等待明确模型 GPU 分配 |
| 普通/受阻/到达的真实 OneJev probe | 未执行 | 已保存 prepare-only 输入，未发送决策 |
| 最长输入真实推理、延迟、显存 | 未执行 | CPU token 检查不证明显存和推理兼容性 |
| 最多五步 GS 闭环和渲染回放 | 未执行 | 等待模型卡与渲染卡分配 |
| 三路线 × 三输入完整实验 | 交由用户执行 | 本轮没有自动运行 9 组实验 |

扫描 19 份既有 OpenAI 图文归档，包含固定矩阵两轮的 18 份及 1 份连通性记录，共 3285 条 before_action 输入。三模式各检查普通、转弯/受阻、到达、最长四例：每例一个 image 占位符和七候选，官方 processor 实际展开后最长无深度 3060、数值 3979、语义 4111 token。逐张读取 JPEG 并验证 SHA256、字节数和实际尺寸；全部相同 640×480、所选 image_grid=[1,30,40]。最长排名根据完整文本 tokenizer，统一图片尺寸对应相同 299 token 扩展量。没有裁剪状态或图片，没有把归档动作当正确标签。

独立审查见 [review.md](review.md)：畸形 qev.media 的异常和默认选卡两项重要问题已用失败回归验证并修复；复审 27 项聚焦测试通过，无剩余重要问题。真实模型 forward、显存和导航质量仍需 GPU 验证。

## 用户运行命令

先选择已分配的 `MODEL_GPU` 和 `NAV_GPU`，模型卡与渲染卡可以不同；共用卡的显存尚未实测。无需 OpenRouter API key。详细单轮/probe/第二轮说明见 [docs/ONEJEV_LOCAL.md](../../docs/ONEJEV_LOCAL.md)。

终端 A：

```bash
cd /data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav
MODEL_GPU="$MODEL_GPU" bash scripts/serve_onejev.sh
```

出现 Application startup complete 后，可 `curl http://127.0.0.1:8011/health` 检查。启动脚本验证固定版本、权重、选卡和端口，使用独立环境；控制台日志和启动前可用显存收据留在 local_models/onejev-4b/logs。

终端 B，激活 habitat-gs：

```bash
conda activate habitat-gs
cd /data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav
CUDA_VISIBLE_DEVICES="$NAV_GPU" python run.py --config config.single-gpu.json run \
  --decision-model onejev --onejev-url http://127.0.0.1:8011 \
  --rgb gs --rgb-input target_marked \
  --tasks tasks/debug-10.json --episode episode-000 \
  --depth-input mesh --depth-format numeric --max-steps 5 \
  --out runs/onejev-simple-rgbtarget-numeric-smoke-user-01
```

五步 smoke 只验证联调，action_budget 不代表导航模型失败；后续完整矩阵：

```bash
CUDA_VISIBLE_DEVICES="$NAV_GPU" NAV_RGB_INPUT=target_marked \
  bash scripts/run_model_ablation.sh onejev local-round-01 --dry-run

CUDA_VISIBLE_DEVICES="$NAV_GPU" NAV_RGB_INPUT=target_marked \
  bash scripts/run_model_ablation.sh onejev local-round-01
```

| 路线 | episode | 预算 | 三种输入 |
|---|---|---:|---|
| 简单 | episode-000 | 100 | numeric / semantic / none |
| 复杂 | turn-000 | 250 | numeric / semantic / none |
| 长路线 | extended-000 | 500 | numeric / semantic / none |

第二轮换 local-round-02；脚本开始前检查全部输出目录，串行运行并保留失败。单步服务错误记 service_failure、不执行替代动作；预检失败则在渲染前退出；未知 choice 保留并按无效动作消耗预算。step/metadata 记录 onejev_local 身份、本地 endpoint、部署清单和原始 qev 响应。出现加载或超时错误时保留日志，先完成本地部署验证，再评估完整导航结果。
