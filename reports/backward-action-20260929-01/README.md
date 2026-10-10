# 恢复同距离后退候选（2026-09-29）

当前 Jev 和 Habitat 动作集为：move_forward、move_backward、turn_left、turn_right、look_up、look_down、stop。左右平移仍然禁用。前进和后退共同使用 config.json 的 move_m，当前 0.25 m；后退不改变身体朝向。

这是供 Jev 自行选择的后退候选，不是自动恢复控制器。新增的后退深度检查复用原算法；前视深度看不到后方时返回 unknown。路径进度、原路径、停止规则、五步历史、原有深度事实与 allow_sliding=true 都保持。提示词版本升级为 seven_actions_backward_v3。

## 验证

- [tests.log](tests.log)：37 项现有回归通过，更新七动作合同、后方未知以及侧移禁用断言。
- [verify_native.py](verify_native.py)、[native-results.json](native-results.json)、[native.log](native.log)：真实 mesh 原生动作；0.25/0.40 m 两种临时内存配置，各在 17°/107° 朝向上前进后退，实际位移相等、往返误差小于 1e-5 m、无碰撞、后退不改变朝向或俯仰。磁盘 config.json 没有修改。
- 从真实 sliding-01 第 14 次动作后的碰撞位置后退：实际 0.25 m，collided=false，目标误差约 2.5e-7 m。此结果仅验证后退执行，不是新的 Jev 导航结果。
- [正常入口冒烟回放](../../runs/smoke-backward-20260929-01/index.html)、[metadata](../../runs/smoke-backward-20260929-01/metadata.json)：动作序列 forward, backward, turn_left, turn_right, look_down, look_up, move_left, move_right, stop。9 步、0 碰撞、2 次刻意无效侧移、early_stop；前进/后退共走 0.5 m 后回到起点。
- [check_results.py](check_results.py)、[verification.json](verification.json)、[verification.log](verification.log)：所有请求七选一、前后检查齐全、后方仍 unknown；原有动作说明、停止规则、路径类与前向深度事实不变；72 个受保护文件哈希不变。
- 碰撞/无效标识沿用既有回放组件，历史动作翻译已经包含后退，无需改动可视化代码。本次没有手动浏览器验收。
- 全部检查均未调用模型 API，没有重编译或修改 Habitat-GS；没有重写旧实验。修改前文件见 before/，变更见 change.diff。

## 用户模型测试

在已有密钥的 habitat-gs 环境下，从 jev_nav 目录运行：

```bash
python run.py run --tasks tasks/challenge-v1-20260928/tasks.json --episode turn-000 \
  --out runs/jev-challenge-turn-000-backward-01 --rgb gs --max-steps 250
```

上述新模型运行尚未执行。记录里 available_actions 应有 7 个选项，prompt_version 为 seven_actions_backward_v3，config.move_m 为 0.25；前后实际位移仍会受 NavMesh 过滤。
