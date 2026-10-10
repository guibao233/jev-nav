# 路径重新关联与五步动作停滞摘要

已实现用户确认的两个功能，供下一轮同任务 Jev 复测。提示词版本 `seven_actions_reassociate_motion_v5`；路径策略版本 `checked_reassociation_v1`。七动作、步长、停止规则、深度算法、API 和滑动设置保持；不修改 Habitat-GS 源码。

## 行为

正常沿路线附近运动时保持原局部投影。到旧跟踪窗口的距离超过 0.5 m，才从后续路段寻找距机器人不超过 0.5 m 的投影点，按距离优先、同距时进度更早优先检查。连接起终点须可通行、高差不超过 0.25 m，直线每段最多 5 cm，NavMesh 运动过滤结果须与每个期望位置相差不超过 0.0001 m；否则拒绝。不会因为另一个点仅仅在墙对面很近就跨墙关联；没有可直连候选时仍保持原进度，属于本版明确限制。

路径进度保持单调，目标前视和拐角截断规则保持，路线本身不重新规划。输入 `reference.tracking` 记录 local/off_path/reassociated、本步 progress_m 及 reassociation_jump_m。连接检查只用于目标提供器，不查询或过滤 Jev 的候选动作。

`recent_motion` 使用最近五步原动作结果，累计每步身体转角后组合局部平移，得到净位移而不是简单相加前进/后退值。输出净/累计转角、路程、相邻相反转向对数、碰撞/无效/执行成功数。满五步、净位移 ≤ max(0.02, move_m×0.2) m 且相反转向对数 ≥2 时标记 turn_oscillation；在当前步长下阈值为 0.05 m。

状态还区分 insufficient_history、no_translation、low_net_motion、moving。no_translation 可包含有意义的原地观察，不自动判失败。提示词解释执行成功不等于导航进展，并让 Jev 在循环时考虑不同观察或恢复动作。执行层仍原样执行模型选择，没有自动后退、动作屏蔽或控制器接管。后退的中性 criterion 和明确停止规则不变。

## 验证

- [50 项单元测试](tests.txt)：37 项原回归和 13 项新增关键回归。
- [保存轨迹验证](offline-verification.json)、[验证脚本](verify_saved.py)、[逐步重放结果](saved-trajectory.csv)、[连接查询](connector-checks.json)。沿用 neutral-02 的 250 个原始位姿及动作，未生成新模型决策。
- 原第 46 与 82 步在离线重放中重新关联。最终进度从原 2.546 m 修复为 4.767 m，剩余原路线从 7.252 m 变为 5.031 m；单调性保持。第 150 步的目标不再指向已走过的路段，见 [第 150 步新请求样例](request-step-150.json)。
- 同一原始动作历史下，第 91 步起可识别 turn_oscillation；第 150 步窗口净位移为 0、相邻相反转向 4 对。摘要与世界位姿计算的净位移最大差约 0.000411 m。
- 12 条正常挑战路线的 1,448 个状态保持原目标和路径预览；新增 tracking 不影响原几何行为。真实 NavMesh 上可绕角到达但不能直连的近点被正确拒绝。
- [六步 mesh 冒烟](../../runs/smoke-reassociate-motion-20260929-01/index.html)、[控制台](smoke.txt)、[进程信息](smoke-process.json)、[请求核对](smoke-verification.json)。GPU 7，mesh 初始化约 1 秒，不加载 GS；子进程移除 API 密钥。五次交替转向后，第六份请求含 turn_oscillation；脚本 stop 产生预期 early_stop。
- 90 个受保护配置/任务/历史记录/其他源码文件哈希一致：[校验清单](protected-before.json)。深度函数、Environment 类和 API 客户端 AST 不变；修改前文件见 before/，[代码差异](implementation.patch)。

这些验证确认输入和执行接线正确，不证明新 Jev 策略已能脱困；真实效果仍由下一轮实验判断。没有调用真实模型，也没有改变历史实验结果。

## 用户复测

在 jev_nav 目录、habitat-gs 环境和已配置 OpenRouter key 的终端执行：

```bash
CUDA_VISIBLE_DEVICES=7 python run.py --config config.single-gpu.json run \
  --tasks tasks/challenge-v1-20260928/tasks.json --episode turn-000 \
  --out runs/jev-challenge-turn-000-reassociate-motion-01 --rgb gs --max-steps 250
python visualize.py --run runs/jev-challenge-turn-000-reassociate-motion-01 --serve --port 8765
```

显存紧张可用 `--rgb mesh`，仅改变回放 RGB 来源。两份现有配置都自动启用新功能，无需同步新增参数；gpu_id=0 的单卡配置继续与 CUDA_VISIBLE_DEVICES=7 配合。输出目录须是新目录。

检查新 metadata 的两个版本字段；steps.jsonl 中的 `request.state.reference.tracking` 与 `request.state.recent_motion` 展示重新关联和停滞摘要。模型是否减少反复转向、碰撞/路程/成功率如何，需与旧记录在实际运行后比较。
