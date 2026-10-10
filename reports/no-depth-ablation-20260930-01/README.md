# 无深度摘要消融：实现与验证（2026-09-30）

已完成可运行开关与验证，未运行真实 Jev 消融任务。目的是测量当前参考路线辅助导航中“提供局部深度摘要”带来的收益。

## 实验边界

| 内容 | 有深度 mesh（默认） | 无深度 none |
|---|---|---|
| state.depth 扇区距离、覆盖/近地面状态、move_checks | 提供 | 完全移除 |
| depth_facts 计算 | 执行 | 跳过 |
| 路线/相对目标、身体参数、相机俯仰 | 提供 | 相同 |
| 碰撞与实际位移反馈、最近五步动作/运动摘要 | 提供 | 相同 |
| 前进/后退/左右转/上下看/停止 | 七选一 | 相同 |
| 主动停止条件、NavMesh/滑动/路径关联 | 原方案 | 相同 |
| RGB 与 mesh 深度图 | 回放用 | 回放用，仍渲染/保存 |
| RGB 输入 Jev | 不提供 | 不提供 |

--depth-input none 不把深度替换成全 unknown，也不修改任务路线。make_request 在 API 边界额外删除 depth，并复制外层 state，避免其他调用者不小心把摘要发出。真实 API 传输仍是日志中保存的 request，旧状态不回填任何深度。

提示词仅对感知相关段落作条件化：无深度时移除 mesh-depth、Blocked/Unknown/Clear 解释和“用俯仰看近地面”，说明没有深度或图像输入、俯仰不会揭示环境观测；停止、路线跟随、动作准则和通用恢复说明保持。无深度版本为 seven_actions_reassociate_motion_v5_no_depth；默认 v5 请求与原实验一致。动作仍完整保留，因此模型若选择俯仰，仍消耗预算并收到本体执行反馈。

meta/summary 中的 depth_input 和 depth_provided_to_model 明确模式；depth_source 仍标记回放渲染来源，不意味着提供给模型。回放继续展示保存的深度，但标明仅供回放；视频导出支持没有 state.depth 的记录。

## 验证证据

- [69 项测试](tests.txt)：原 63 项 + 新增 6 项，模拟请求已验证序列化不含深度摘要。
- [独立验证脚本](verify.py) / [结果](verification.json)：250 份历史 Jev 默认请求精确相等；两组 6 份请求状态只相差 depth、位姿与执行结果相同；118 个受保护文件未变。
- GPU 7 / 内部逻辑设备 0：两组使用同一 turn-000、同一动作脚本 move_forward,look_down,turn_left,move_forward,move_backward,stop。都为 early_stop、6 步、0 碰撞、0 无效；预设停止是验证流程，不是模型失败。无深度组还拦截 depth_facts，确认完全未调用。
- [有深度脚本回放](../../runs/smoke-depth-ablation-mesh-20260930-01/index.html)、[无深度脚本回放](../../runs/smoke-depth-ablation-none-20260930-01/index.html)、[进程及参数](smoke-process.json)、[mesh 日志](smoke-mesh.txt)、[none 日志](smoke-none.txt)。测试子进程移除了模型密钥，API 调用为 0。
- [便携无深度回放](viewer-none/index.html)、[MP4](viewer-none/media/rgb-depth.mp4)、[GIF](viewer-none/media/rgb-depth.gif)：7 幅观察，H.264/yuv420p 1920×688、315 帧、10.5 秒；导出验证了完整解码、GIF 时长和原文件哈希。HTML 输入与日志相等，JavaScript 语法通过，未作交互浏览器验收。
- [受保护文件哈希](protected-before.json)、[改动](implementation.patch)，修改前源码和说明保存在 before/。

## 同任务复测

在 habitat-gs Conda 环境、jev_nav 目录执行：

```bash
CUDA_VISIBLE_DEVICES=7 python run.py --config config.single-gpu.json run \
  --tasks tasks/challenge-clearance-aligned-20260930-01/tasks.json --episode turn-000 \
  --out runs/jev-challenge-turn-000-clearance-aligned-no-depth-01 \
  --rgb gs --max-steps 250 --depth-input none
python visualize.py --run runs/jev-challenge-turn-000-clearance-aligned-no-depth-01 --serve --port 8765
```

有深度基线可参照已完成的 runs/jev-challenge-turn-000-clearance-aligned-01。若重跑，使用同一个命令，将 --depth-input none 改为 mesh，输出改成新的 runs/jev-challenge-turn-000-clearance-aligned-depth-control-01。省略开关默认 mesh。其他任务也直接复用开关，不生成新任务文件。

当前任务初始 yaw=−90.39°、pitch=0°，参考长度 11.71097 m、原最短距离 9.79769 m，两组相同；这次不引入 30° 初始下视。模型、预算和渲染模式也应一致。建议比较主动停止成功率、碰撞/无效动作数、路径长度、动作数和停滞；若需要稳定结论，使用相同任务集合重复运行。

即使无深度组成功，也只能说明在给定安全参考路线和碰撞反馈条件下可以跟随，不代表独立完成了避障规划。整轮耗时还受跳过深度摘要计算影响，不能直接当作模型决策速度变化。
