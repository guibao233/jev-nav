# 中性提示词恢复验证（2026-09-29）

已更新 `jev.py`，提示词版本 `seven_actions_neutral_v4`。本轮只恢复描述，尚未验证真实 Jev 导航效果。

## 改动

以 `runs/jev-challenge-turn-000-02/steps.jsonl` 第一份请求为文本依据：

- 后退恢复为 `Translate backward 0.25 metres without changing body heading.`，与前进采用对称的中性描述。
- 通用指令恢复为旧原文，包含避免无进展的重复/相反动作交替、允许暂时远离目标进行恢复、观察地面与遵守俯仰限制。
- 移除后加的后退专属恢复/后方风险强调、受阻先转向规则和冗余动作集枚举。实际选项仍由七项 criteria 明确列出。
- 当前最高优先级停止前缀和 stop criterion 保持原样；深度中的 unknown 事实和通用 unknown 提醒仍保留。

七动作、前后共用 `move_m=0.25`、`allow_sliding=true`、路径/深度/短期历史及 API 逻辑均保持。没有恢复左右平移。与旧九动作成功实验的动作空间及滑动设置仍有差异，不能保证重现其结果。

## 验证

- 37 项已有单元测试通过：[完整输出](tests.txt)。API 测试使用模拟响应，没有网络请求。
- 对 backward-01 的 22 份保存请求状态离线重新构造请求。通用正文、六个非停止动作 criterion 与旧成功实验精确一致；最高优先级停止前缀与 stop criterion 和修改前精确一致；输入状态、模型及其他字段不变。
- API 代码 AST 不变；88 个受保护文件 SHA-256 不变，包含配置、任务、历史结果及其他模块源码。无仿真、无 API 调用。
- [核对脚本](verify.py)、[验证结果](verification.json)、[请求样例](request-example.json)、[提示词差异](prompt.patch)、[原文件校验表](protected-before.json)。`before/` 保存修改前的 `jev.py`、README 和 VALIDATION。

## 同任务复测

在 habitat-gs 环境和已配置 OpenRouter 密钥的终端中执行：

```bash
python run.py run --tasks tasks/challenge-v1-20260928/tasks.json --episode turn-000 \
  --out runs/jev-challenge-turn-000-neutral-01 --rgb gs --max-steps 250
python visualize.py --run runs/jev-challenge-turn-000-neutral-01 --serve --port 8765
```

输出使用新目录，保留原记录。新实验的 metadata.json 应记录 `seven_actions_neutral_v4`。比较起始方向选择、有效进展、碰撞恢复及相反动作往返；若再次出现 service_failure，应单独记录服务中断，不能当作完整 250 步导航失败。导航成功率是否改善仍需实际运行评估。
