# OneJev-4B 本地导航

原版本固定为 `baseline-20261010-before-onejev`（3589b100ae56d05a8f5179b673aced26745d58a0），当前开发分支 `feature/onejev-local`。仓库无远程地址。运行数据、模型和环境留在本机，不进入 Git。

## 启动

模型环境位于 `local_models/onejev-4b/env`，不会改动 habitat-gs。选择已分配的物理 GPU 后，在项目根目录运行：

```bash
MODEL_GPU=你的模型卡号 bash scripts/serve_onejev.sh
```

服务默认仅监听 `http://127.0.0.1:8011`。等控制台出现 Application startup complete 后再运行导航；可用 `curl http://127.0.0.1:8011/health` 检查。服务启动前验证源版本、完整权重哈希、显式 GPU 和端口，启动时不自动下载。Ctrl+C 停止服务。

首版 BF16 主体、FP32 输出头、禁用 CUDA Graph、CPU 图片预处理、8192 token 上限、QEV_DEBIAS=1。推理使用官方 qev 内部模板；具体 revision/依赖/校准状态见 `local_models/onejev-4b/deployment.json`，权重清单见同目录 weights-manifest.json。

## 单轮联调

另一个终端激活原 habitat-gs 环境，在项目根目录运行；将 CUDA_VISIBLE_DEVICES 换成已分配的渲染卡号，单卡配置内部 gpu_id 始终为 0。模型和渲染可以用不同卡；共用卡需要实际验证显存。无需 API key。

```bash
CUDA_VISIBLE_DEVICES=你的渲染卡号 python run.py --config config.single-gpu.json run \
  --decision-model onejev --onejev-url http://127.0.0.1:8011 \
  --onejev-timeout-s 30 --rgb gs --rgb-input target_marked \
  --tasks tasks/debug-10.json --episode episode-000 \
  --depth-input mesh --depth-format numeric --max-steps 5 \
  --out runs/onejev-simple-rgbtarget-numeric-smoke-user-01
```

输出目录已存在时换新名称。5 步可能因为预算结束而失败，只用于联调，不算完整路线效果。

## 三路线 × 三深度条件

以下脚本串行运行简单/复杂/长路线各 numeric、semantic、none，共 9 轮，预算分别为 100/250/500；沿用已有任务、参考路线、初始位姿、七动作和停止规则。每轮都接收当前 GS RGB 和虚拟航点标记；none 只是不给深度文字，仍有图片。

```bash
CUDA_VISIBLE_DEVICES=你的渲染卡号 NAV_RGB_INPUT=target_marked \
  bash scripts/run_model_ablation.sh onejev local-round-01 --dry-run

CUDA_VISIBLE_DEVICES=你的渲染卡号 NAV_RGB_INPUT=target_marked \
  bash scripts/run_model_ablation.sh onejev local-round-01
```

第二轮改为 `local-round-02`。只测简单路线加 `ROUTES=simple`；只测一个条件加 `MODES=semantic`。默认配置 config.single-gpu.json，可用 NAV_CONFIG/NAV_PYTHON 覆盖；ONEJEV_BASE_URL/ONEJEV_TIMEOUT_S 控制本地地址和超时。服务端若报超限/OOM，保留结果，不要用自动裁剪或规则动作替换来继续本轮。

文字对照把 `NAV_RGB_INPUT=none`；RGB 仍可供回放，但不会送进模型。与已有 OpenAI 图文比较用 target_marked，不能把两种输入混在一组。

## 核查一份历史输入

```bash
python scripts/probe_onejev.py \
  --run runs/某次已有OpenAI图文实验 --step 0 \
  --out reports/onejev-probe-user-01.json --prepare-only
```

去掉 --prepare-only 才发送本地模型请求；不移动机器人。工具验证保存的标记图像哈希，保持原请求 instructions、criteria、深度和历史，只替换模型和传输协议。输出保留可读状态、图像清单、wire SHA256 和响应，不写大段 Base64。

## 记录和限制

metadata/summary 明确 provider=onejev_local，is_onejev_evaluation=true；不计入旧 Jev/OpenAI 身份。steps 保留原始 choice、概率、服务模板哈希及实际 JPEG/wire 哈希。未知动作按无效动作消耗预算；结构损坏或服务失败则不执行动作、停止本轮。本地 HTTP 禁用代理和重定向，没有云端回退。

离线回放、GPU 部署、5 步闭环与完整导航是不同层级的证据。具体通过/未执行项见 [部署验证报告](../reports/onejev-local-deployment-20261010-01/README.md)。
