# 六动作与明确停止规则验证

2026-09-29，提示词版本 `six_actions_stop_v2`。

- 提示词首位与 stop 选项明确：当前目标为最终终点，且给定 final_goal 距离 ≤ stop_tolerance_m（默认 0.30 m，含边界）时立即停止。无需精确到达中心或对齐朝向；停止优先于路径跟随、移动、观察与恢复。没有自动替换模型动作为 stop。
- 模型选项与 Habitat 动作空间统一为前进、左转、右转、抬头、低头、停止。深度摘要只保留前进的扫过体积检查，九扇区观测保留。被移除动作若异常返回则不执行，记无效且消耗预算。
- `metadata.json` 新增 available_actions 和 prompt_version，既有任务可复用；旧九动作结果需作为旧版本看待。
- 35 项离线回归通过，见 [tests.txt](tests.txt)。新增/更新检查覆盖六动作请求、请求中无移除动作、禁止动作不下发模拟器、stop 不触发移动、停止规则与配置阈值一致。
- 实际 RTX 4090 mesh 仿真：`runs/smoke-six-actions-20260929-01`，9 次脚本动作覆盖全部六个动作。0 碰撞，1 次刻意低头超限，第 9 步刻意提前 stop，正确标记 early_stop。该结果是执行接口验证，不是模型表现。
- 实际保存的 9 次请求均只有六个选项和前进动作检查，均包含优先停止规则。样例见 [prompt-example.json](prompt-example.json)。
- 核对原 47 个配置/任务/历史运行记录的哈希，全部保持不变。摘要见 [verification.json](verification.json)，修改前源码在 before/，差异在 changes.patch。
- 当前工具进程未配置 OPENROUTER_API_KEY，本轮未调用真实 Jev。是否改善停止行为，需要新版本重跑同一任务确认。

提示词的距离来自已有机器人水平相对坐标；最终评估仍使用 NavMesh 距离。二者不是普遍等价的距离定义，保留了原有的终点评估规则。

复测命令（项目目录，habitat-gs 环境，已配置 API key）：

```bash
python run.py run --tasks tasks/challenge-v1-20260928/tasks.json --episode turn-000 \
  --out runs/jev-challenge-turn-000-six-actions-01 --rgb gs --max-steps 500
python visualize.py --run runs/jev-challenge-turn-000-six-actions-01 --serve --port 8765
```
