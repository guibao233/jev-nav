# 固定方案下全部55轮导航指标

保留全部可比成功与失败。每行是一轮；最终距离使用六位小数，成功阈值为NavMesh距离≤0.30 m且主动stop。M1表示mesh RGB回放，G1/G2表示GS回放，H表示同一固定策略的较早记录；Jev和OpenAI纯文字的RGB均不送模型。

## Jev 文字决策

### 简单路线

| 输入 | 批次 | 结果 | 动作 | 碰撞 | 无效 | 路程 m | 最终距离 m | SPL |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 数值深度 | [M1](../../runs/jev-simple-numeric-20261008-01/summary.json) | 成功 | 18 | 0 | 0 | 4.000 | 0.240986 | 1.000 |
| 数值深度 | [G1](../../runs/jev-simple-rgbgs-numeric-20261008-01/summary.json) | 成功 | 18 | 0 | 0 | 4.000 | 0.240986 | 1.000 |
| 语义深度 | [G1](../../runs/jev-simple-rgbgs-semantic-20261008-01/summary.json) | 成功 | 23 | 0 | 0 | 4.000 | 0.240986 | 1.000 |
| 语义深度 | [M1](../../runs/jev-simple-semantic-20261008-01/summary.json) | 成功 | 23 | 0 | 0 | 4.000 | 0.218624 | 1.000 |
| 无深度 | [G1](../../runs/jev-simple-rgbgs-none-20261008-01/summary.json) | 成功 | 18 | 1 | 0 | 3.996 | 0.255777 | 1.000 |
| 无深度 | [G2](../../runs/jev-simple-rgbgs-none-20261008-02/summary.json) | 成功 | 18 | 1 | 0 | 3.996 | 0.255777 | 1.000 |

### 复杂路线

| 输入 | 批次 | 结果 | 动作 | 碰撞 | 无效 | 路程 m | 最终距离 m | SPL |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 数值深度 | [H](../../runs/jev-challenge-turn-000-clearance-aligned-01/summary.json) | 失败：预算耗尽 | 250 | 1 | 16 | 33.358 | 0.571755 | 0.000 |
| 数值深度 | [M1](../../runs/jev-complex-numeric-20261008-01/summary.json) | 成功 | 86 | 0 | 1 | 13.750 | 0.283747 | 0.713 |
| 数值深度 | [G1](../../runs/jev-complex-rgbgs-numeric-20261008-01/summary.json) | 失败：提前停止 | 119 | 1 | 9 | 15.228 | 0.303706 | 0.000 |
| 语义深度 | [G1](../../runs/jev-complex-rgbgs-semantic-20261008-01/summary.json) | 失败：提前停止 | 124 | 1 | 6 | 15.901 | 0.351736 | 0.000 |
| 语义深度 | [M1](../../runs/jev-complex-semantic-20261008-01/summary.json) | 成功 | 76 | 0 | 0 | 13.000 | 0.265350 | 0.754 |
| 无深度 | [H](../../runs/jev-challenge-turn-000-clearance-aligned-no-depth-01/summary.json) | 失败：预算耗尽 | 250 | 29 | 0 | 43.098 | 0.910429 | 0.000 |
| 无深度 | [G1](../../runs/jev-complex-rgbgs-none-20261008-01/summary.json) | 成功 | 77 | 6 | 0 | 13.430 | 0.294787 | 0.730 |

### 长路线

| 输入 | 批次 | 结果 | 动作 | 碰撞 | 无效 | 路程 m | 最终距离 m | SPL |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 数值深度 | [G1](../../runs/jev-extended-rgbgs-numeric-20261008-01/summary.json) | 成功 | 252 | 0 | 4 | 30.000 | 0.161575 | 0.544 |
| 数值深度 | [G2](../../runs/jev-extended-rgbgs-numeric-20261008-02/summary.json) | 失败：预算耗尽 | 500 | 1 | 78 | 30.721 | 9.730200 | 0.000 |
| 语义深度 | [G1](../../runs/jev-extended-rgbgs-semantic-20261008-01/summary.json) | 失败：预算耗尽 | 500 | 0 | 18 | 57.500 | 1.776616 | 0.000 |
| 语义深度 | [G2](../../runs/jev-extended-rgbgs-semantic-20261008-02/summary.json) | 失败：预算耗尽 | 500 | 0 | 16 | 55.000 | 1.209574 | 0.000 |
| 无深度 | [G1](../../runs/jev-extended-rgbgs-none-20261008-01/summary.json) | 失败：预算耗尽 | 500 | 46 | 0 | 84.058 | 1.497800 | 0.000 |
| 无深度 | [G2](../../runs/jev-extended-rgbgs-none-20261008-02/summary.json) | 失败：预算耗尽 | 500 | 112 | 0 | 84.545 | 15.817625 | 0.000 |

## OpenAI 纯文字

### 简单路线

| 输入 | 批次 | 结果 | 动作 | 碰撞 | 无效 | 路程 m | 最终距离 m | SPL |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 数值深度 | [01](../../runs/openai-decisions-simple-rgbgs-numeric-20261009-01/summary.json) | 失败：预算耗尽 | 100 | 5 | 0 | 5.559 | 4.667272 | 0.000 |
| 数值深度 | [02](../../runs/openai-decisions-simple-rgbgs-numeric-20261009-02/summary.json) | 失败：预算耗尽 | 100 | 5 | 0 | 5.559 | 4.667272 | 0.000 |
| 语义深度 | [01](../../runs/openai-decisions-simple-rgbgs-semantic-20261009-01/summary.json) | 失败：预算耗尽 | 100 | 10 | 1 | 17.609 | 3.388045 | 0.000 |
| 语义深度 | [02](../../runs/openai-decisions-simple-rgbgs-semantic-20261009-02/summary.json) | 失败：预算耗尽 | 100 | 10 | 1 | 17.609 | 3.388045 | 0.000 |
| 无深度 | [01](../../runs/openai-decisions-simple-rgbgs-none-20261009-01/summary.json) | 失败：提前停止 | 75 | 17 | 0 | 6.918 | 0.462650 | 0.000 |
| 无深度 | [02](../../runs/openai-decisions-simple-rgbgs-none-20261009-02/summary.json) | 失败：提前停止 | 75 | 17 | 0 | 6.918 | 0.462650 | 0.000 |

### 复杂路线

| 输入 | 批次 | 结果 | 动作 | 碰撞 | 无效 | 路程 m | 最终距离 m | SPL |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 数值深度 | [01](../../runs/openai-decisions-complex-rgbgs-numeric-20261009-01/summary.json) | 成功 | 86 | 0 | 0 | 12.000 | 0.278290 | 0.816 |
| 数值深度 | [02](../../runs/openai-decisions-complex-rgbgs-numeric-20261009-02/summary.json) | 成功 | 86 | 0 | 0 | 12.000 | 0.278290 | 0.816 |
| 语义深度 | [01](../../runs/openai-decisions-complex-rgbgs-semantic-20261009-01/summary.json) | 成功 | 156 | 0 | 9 | 11.750 | 0.241567 | 0.834 |
| 语义深度 | [02](../../runs/openai-decisions-complex-rgbgs-semantic-20261009-02/summary.json) | 成功 | 156 | 0 | 9 | 11.750 | 0.241567 | 0.834 |
| 无深度 | [01](../../runs/openai-decisions-complex-rgbgs-none-20261009-01/summary.json) | 失败：预算耗尽 | 250 | 106 | 0 | 31.390 | 0.689694 | 0.000 |
| 无深度 | [02](../../runs/openai-decisions-complex-rgbgs-none-20261009-02/summary.json) | 失败：预算耗尽 | 250 | 106 | 0 | 31.390 | 0.689694 | 0.000 |

### 长路线

| 输入 | 批次 | 结果 | 动作 | 碰撞 | 无效 | 路程 m | 最终距离 m | SPL |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 数值深度 | [01](../../runs/openai-decisions-extended-rgbgs-numeric-20261009-01/summary.json) | 失败：提前停止 | 194 | 0 | 0 | 20.500 | 0.308222 | 0.000 |
| 数值深度 | [02](../../runs/openai-decisions-extended-rgbgs-numeric-20261009-02/summary.json) | 失败：提前停止 | 194 | 0 | 0 | 20.500 | 0.308222 | 0.000 |
| 语义深度 | [01](../../runs/openai-decisions-extended-rgbgs-semantic-20261009-01/summary.json) | 成功 | 351 | 0 | 3 | 19.750 | 0.261363 | 0.826 |
| 语义深度 | [02](../../runs/openai-decisions-extended-rgbgs-semantic-20261009-02/summary.json) | 成功 | 351 | 0 | 3 | 19.750 | 0.261363 | 0.826 |
| 无深度 | [01](../../runs/openai-decisions-extended-rgbgs-none-20261009-01/summary.json) | 成功 | 202 | 7 | 0 | 28.071 | 0.173495 | 0.581 |
| 无深度 | [02](../../runs/openai-decisions-extended-rgbgs-none-20261009-02/summary.json) | 成功 | 202 | 7 | 0 | 28.071 | 0.173495 | 0.581 |

## OpenAI 图文

### 简单路线

| 输入 | 批次 | 结果 | 动作 | 碰撞 | 无效 | 路程 m | 最终距离 m | SPL |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 数值深度 | [01](../../runs/openai-decisions-rgbtarget-simple-rgbgs-numeric-20261009-01/summary.json) | 成功 | 40 | 0 | 0 | 4.000 | 0.263354 | 1.000 |
| 数值深度 | [02](../../runs/openai-decisions-rgbtarget-simple-rgbgs-numeric-20261009-02/summary.json) | 成功 | 40 | 0 | 0 | 4.000 | 0.263354 | 1.000 |
| 语义深度 | [01](../../runs/openai-decisions-rgbtarget-simple-rgbgs-semantic-20261009-01/summary.json) | 成功 | 67 | 0 | 0 | 4.000 | 0.269591 | 1.000 |
| 语义深度 | [02](../../runs/openai-decisions-rgbtarget-simple-rgbgs-semantic-20261009-02/summary.json) | 成功 | 67 | 0 | 0 | 4.000 | 0.269591 | 1.000 |
| 无深度 | [01](../../runs/openai-decisions-rgbtarget-simple-rgbgs-none-20261009-01/summary.json) | 成功 | 40 | 1 | 0 | 3.996 | 0.250113 | 1.000 |
| 无深度 | [02](../../runs/openai-decisions-rgbtarget-simple-rgbgs-none-20261009-02/summary.json) | 成功 | 40 | 1 | 0 | 3.996 | 0.250113 | 1.000 |

### 复杂路线

| 输入 | 批次 | 结果 | 动作 | 碰撞 | 无效 | 路程 m | 最终距离 m | SPL |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 数值深度 | [01](../../runs/openai-decisions-rgbtarget-complex-rgbgs-numeric-20261009-01/summary.json) | 成功 | 166 | 0 | 0 | 12.250 | 0.109957 | 0.800 |
| 数值深度 | [02](../../runs/openai-decisions-rgbtarget-complex-rgbgs-numeric-20261009-02/summary.json) | 成功 | 166 | 0 | 0 | 12.250 | 0.109957 | 0.800 |
| 语义深度 | [01](../../runs/openai-decisions-rgbtarget-complex-rgbgs-semantic-20261009-01/summary.json) | 成功 | 94 | 0 | 1 | 12.000 | 0.234743 | 0.816 |
| 语义深度 | [02](../../runs/openai-decisions-rgbtarget-complex-rgbgs-semantic-20261009-02/summary.json) | 成功 | 94 | 0 | 1 | 12.000 | 0.234743 | 0.816 |
| 无深度 | [01](../../runs/openai-decisions-rgbtarget-complex-rgbgs-none-20261009-01/summary.json) | 成功 | 158 | 0 | 0 | 11.750 | 0.177727 | 0.834 |
| 无深度 | [02](../../runs/openai-decisions-rgbtarget-complex-rgbgs-none-20261009-02/summary.json) | 成功 | 158 | 0 | 0 | 11.750 | 0.177727 | 0.834 |

### 长路线

| 输入 | 批次 | 结果 | 动作 | 碰撞 | 无效 | 路程 m | 最终距离 m | SPL |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 数值深度 | [01](../../runs/openai-decisions-rgbtarget-extended-rgbgs-numeric-20261009-01/summary.json) | 成功 | 334 | 0 | 0 | 20.000 | 0.208400 | 0.816 |
| 数值深度 | [02](../../runs/openai-decisions-rgbtarget-extended-rgbgs-numeric-20261009-02/summary.json) | 成功 | 334 | 0 | 0 | 20.000 | 0.208400 | 0.816 |
| 语义深度 | [01](../../runs/openai-decisions-rgbtarget-extended-rgbgs-semantic-20261009-01/summary.json) | 成功 | 313 | 0 | 0 | 19.750 | 0.258362 | 0.826 |
| 语义深度 | [02](../../runs/openai-decisions-rgbtarget-extended-rgbgs-semantic-20261009-02/summary.json) | 成功 | 313 | 0 | 0 | 19.750 | 0.258362 | 0.826 |
| 无深度 | [01](../../runs/openai-decisions-rgbtarget-extended-rgbgs-none-20261009-01/summary.json) | 成功 | 428 | 0 | 0 | 19.750 | 0.096026 | 0.826 |
| 无深度 | [02](../../runs/openai-decisions-rgbtarget-extended-rgbgs-none-20261009-02/summary.json) | 成功 | 428 | 0 | 0 | 19.750 | 0.096026 | 0.826 |
