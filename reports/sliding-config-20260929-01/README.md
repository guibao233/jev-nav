# allow_sliding 参数回归验证（2026-09-29）

当前 `config.json` 设置 `allow_sliding=true`。导航适配器将其传入 Habitat 的现有 `SimulatorConfiguration.allow_sliding`，绕过本地 no-sliding 分支在精确边界点误阻挡合法移动的问题。没有修改或编译 Habitat-GS 源码，也没有更换 NavMesh。

这是执行配置的替代方案，不是原生 no-sliding 实现的修复。允许滑动后，前进可能产生沿边界的侧向位移；可选动作仍是六个，不包含主动侧移或后退。模型提示、路径采样、短期历史和停止判定未变。新旧实验需按 `allow_sliding` 参数区分。

## 改动范围

- `config.json`：新增 `allow_sliding: true`。
- `environment.py`：把该配置传给现有模拟器参数。
- `run.py`：检查参数必须为 JSON 布尔值，缺少该字段的旧配置保持 false；metadata 顶层和 config 均记录实际值。
- `test_core.py`：配置布尔值及旧配置兼容检查。
- README、VALIDATION：说明设置、行为差异和测试证据。

修改前文件保存在 [before](before/)，完整补丁见 [change.diff](change.diff)。恢复旧行为只需把配置中的 `allow_sliding` 改回 false。

## 真实模拟器的边界对照

使用已安装的 Habitat-GS、同一 shuyuan mesh 和原 NavMesh，调用真实 `Environment.reset` 和 `Environment.act("move_forward")`。两种设置分别复用三轮失败实验的卡点，每个卡点检查一个合法离开方向和一个不可通行方向，共 12 次实际动作；没有请求 Jev。

| 卡点来源 | 验证朝向 | false：合法方向实际移动 | true：合法方向实际移动 |
|---|---|---:|---:|
| six-actions-01，第 247 次决策前 | 原记录朝向 | 0 m，collided=true | 0.25 m，collided=false |
| six-actions-02，第 150 次决策前 | 原朝向增加 45° | 0 m，collided=true | 0.25 m，collided=false |
| six-actions-03，第 174 次决策前 | 原记录朝向 | 0 m，collided=true | 0.25 m，collided=false |

验证前确认合法方向的目标点可通行，最短路径约为直线的 0.25 m。开启后均完整到达该目标点。第二个用例通过重置朝向检查可离开方向，并不代表模型已自行选择该转向。

另外三个开启滑动的朝外对照，期望终点均不可通行，实际移动分别约 0.18691 / 0.01683 / 0.24167 m；均保持在 NavMesh 内、没有到达不可通行的期望终点，且 `collided=true`。关闭滑动的朝外对照同样没有离开 NavMesh。这里的碰撞仍指 Habitat Agent 运动过滤，不能据此声称完整三维 mesh 刚体碰撞验证。

脚本：[verify_execution.py](verify_execution.py)；逐项数据：[execution-results.json](execution-results.json)；控制台：[execution.log](execution.log)。脚本使用独立输出目录，原目录存在时拒绝复写，重复验证请使用新的报告目录。

## 正常入口与回归

- `python -B -m unittest -v test_core test_map_view test_visualize test_challenges`：37 项通过，见 [tests.log](tests.log)。
- `python -B run.py smoke --tasks tasks/debug-10.json --episode episode-000 --out runs/smoke-sliding-20260929-01 --rgb mesh`：9 步，0 碰撞，1 次刻意超出俯仰限制；脚本最后提前 stop，结果 early_stop，符合预期。这是脚本验证，不是 Jev 成功任务。
- [冒烟回放](../../runs/smoke-sliding-20260929-01/index.html)与 [metadata](../../runs/smoke-sliding-20260929-01/metadata.json) 已生成，元数据两处 `allow_sliding` 均为 true。未做浏览器交互验收。
- 61 个受保护文件的 SHA-256 未变化，包括已有任务、运行元数据/日志/结果、`jev.py`、`core.py` 和本地原生 `PathFinder.cpp`。NavMesh SHA-256 与历史实验相同；mesh/GS 的路径、大小、修改时间也相同。
- 复核脚本：[check_results.py](check_results.py)；最终结果：[verification.json](verification.json)。未调用 API、未更改依赖环境；本次未加载 GS RGB。

## 同一复杂任务的下一轮

在已配置 OpenRouter 密钥的 habitat-gs 环境中，从 jev_nav 目录运行：

```bash
python run.py run --tasks tasks/challenge-v1-20260928/tasks.json --episode turn-000 \
  --out runs/jev-challenge-turn-000-sliding-01 --rgb gs --max-steps 500
```

此输出目录尚未生成。真实 Jev 的整轮结果仍待复测；参数回归只证明已复现的执行边界误阻挡得到绕过，不证明初始方向错误、路径恢复或整体成功率已有改善。
