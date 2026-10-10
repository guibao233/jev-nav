# 单卡 CUDA / EGL 配置修复（2026-09-29）

原因：用户设置 `CUDA_VISIBLE_DEVICES=7`，当前 `config.json` 却仍把 `gpu_id=2` 传给 Habitat 的 `SimulatorConfiguration.gpu_device_id`。只暴露一张 GPU 时有效逻辑编号为 0；原生 EGL 查询无法匹配逻辑 CUDA 设备 2，因而在模型请求前退出。这份报错没有显示显存耗尽。EGL 的 17 个枚举设备也不等于 17 张可见 CUDA 显卡。

## 修复

新增 `config.single-gpu.json`，仅把 `gpu_id` 从 2 改为 0，保留原默认配置。物理 GPU 由启动时的 CUDA_VISIBLE_DEVICES 指定。没有修改导航算法、提示词、运行器或 Habitat-GS 源码。

```bash
CUDA_VISIBLE_DEVICES=7 python run.py --config config.single-gpu.json run \
  --tasks tasks/challenge-v1-20260928/tasks.json --episode turn-000 \
  --out runs/jev-challenge-turn-000-neutral-02 --rgb gs --max-steps 250
```

`--config` 是顶层参数，位于 `run` 子命令前。neutral-01 的初始化失败产物保留；新输出目录若已存在，应另选新名称。配置副本以后需要与希望采用的基础参数保持同步。

## 实际验证

- 在 CUDA_VISIBLE_DEVICES=7 的独立进程里，CUDA Driver API 枚举到 1 张卡，逻辑编号为 0；UUID 与 nvidia-smi 的物理 7 号卡相同，见 device-mapping.json。
- 使用该配置运行 `smoke --rgb gs --max-steps 1 --actions stop`；移除测试子进程中的 API 密钥，不调用 Jev。mesh 初始化约 0.8 秒，GS 约 31.6 秒，退出码 0。
- 保存并检查 2 幅 640×480 GS RGB 和 2 份有效 mesh 深度。early_stop 是脚本在起点主动停止的预期结果，仅验证设备选择和渲染，不测导航成功率。
- 原 config、jev.py、environment.py、run.py 和 neutral-01 失败记录哈希保持一致。
- [运行回放](../../runs/smoke-gpu7-20260929-01/index.html)、[控制台](smoke.log)、[进程记录](smoke-process.json)、[核对结果](verification.json)。

显存紧张时可采用 `--rgb mesh`，或者不需要 RGB 时采用 `--rgb none`。两者均避免第二个 GS 渲染器，但 mesh 深度依旧需要 EGL/GPU；模型输入方案保持不变。本次没有比较两种模式的具体显存用量，也没有执行新的真实模型导航。
