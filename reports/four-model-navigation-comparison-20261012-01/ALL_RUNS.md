# 四种方案全部 73 轮实验指标

所有成功、提前停止与预算耗尽样本均保留。结果链接为原始 summary.json；距离均为 NavMesh 路径距离，路程为实际位移累加。

## 简单路线

| 方案 | 输入 | 批次 | 结果 | 动作数 | 碰撞 | 无效 | 累计路程 m | 最终距离 m | 最近距离 m | SPL |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| Jev 文字 | 数值深度 | M1 | [成功](../../runs/jev-simple-numeric-20261008-01/summary.json) | 18 | 0 | 0 | 4.000 | 0.240986 | 0.240986 | 1.000 |
| Jev 文字 | 数值深度 | G1 | [成功](../../runs/jev-simple-rgbgs-numeric-20261008-01/summary.json) | 18 | 0 | 0 | 4.000 | 0.240986 | 0.240986 | 1.000 |
| OpenAI 纯文字 | 数值深度 | 01 | [失败：预算耗尽](../../runs/openai-decisions-simple-rgbgs-numeric-20261009-01/summary.json) | 100 | 5 | 0 | 5.559 | 4.667272 | 3.227464 | 0.000 |
| OpenAI 纯文字 | 数值深度 | 02 | [失败：预算耗尽](../../runs/openai-decisions-simple-rgbgs-numeric-20261009-02/summary.json) | 100 | 5 | 0 | 5.559 | 4.667272 | 3.227464 | 0.000 |
| OpenAI 图文 | 数值深度 | 01 | [成功](../../runs/openai-decisions-rgbtarget-simple-rgbgs-numeric-20261009-01/summary.json) | 40 | 0 | 0 | 4.000 | 0.263354 | 0.263354 | 1.000 |
| OpenAI 图文 | 数值深度 | 02 | [成功](../../runs/openai-decisions-rgbtarget-simple-rgbgs-numeric-20261009-02/summary.json) | 40 | 0 | 0 | 4.000 | 0.263354 | 0.263354 | 1.000 |
| OneJev-4B 图文 | 数值深度 | 01 | [失败：预算耗尽](../../runs/onejev-local-rgbtarget-simple-rgbgs-numeric-local-round-01/summary.json) | 100 | 19 | 0 | 24.983 | 1.026274 | 0.578175 | 0.000 |
| OneJev-4B 图文 | 数值深度 | 02 | [失败：预算耗尽](../../runs/onejev-local-rgbtarget-simple-rgbgs-numeric-local-round-02/summary.json) | 100 | 19 | 0 | 24.983 | 1.026274 | 0.578175 | 0.000 |
| Jev 文字 | 语义深度 | G1 | [成功](../../runs/jev-simple-rgbgs-semantic-20261008-01/summary.json) | 23 | 0 | 0 | 4.000 | 0.240986 | 0.240986 | 1.000 |
| Jev 文字 | 语义深度 | M1 | [成功](../../runs/jev-simple-semantic-20261008-01/summary.json) | 23 | 0 | 0 | 4.000 | 0.218624 | 0.218624 | 1.000 |
| OpenAI 纯文字 | 语义深度 | 01 | [失败：预算耗尽](../../runs/openai-decisions-simple-rgbgs-semantic-20261009-01/summary.json) | 100 | 10 | 1 | 17.609 | 3.388045 | 0.332596 | 0.000 |
| OpenAI 纯文字 | 语义深度 | 02 | [失败：预算耗尽](../../runs/openai-decisions-simple-rgbgs-semantic-20261009-02/summary.json) | 100 | 10 | 1 | 17.609 | 3.388045 | 0.332596 | 0.000 |
| OpenAI 图文 | 语义深度 | 01 | [成功](../../runs/openai-decisions-rgbtarget-simple-rgbgs-semantic-20261009-01/summary.json) | 67 | 0 | 0 | 4.000 | 0.269591 | 0.269591 | 1.000 |
| OpenAI 图文 | 语义深度 | 02 | [成功](../../runs/openai-decisions-rgbtarget-simple-rgbgs-semantic-20261009-02/summary.json) | 67 | 0 | 0 | 4.000 | 0.269591 | 0.269591 | 1.000 |
| OneJev-4B 图文 | 语义深度 | 01 | [失败：预算耗尽](../../runs/onejev-local-rgbtarget-simple-rgbgs-semantic-local-round-01/summary.json) | 100 | 19 | 0 | 24.983 | 1.474670 | 0.578175 | 0.000 |
| OneJev-4B 图文 | 语义深度 | 02 | [失败：预算耗尽](../../runs/onejev-local-rgbtarget-simple-rgbgs-semantic-local-round-02/summary.json) | 100 | 19 | 0 | 24.983 | 1.474670 | 0.578175 | 0.000 |
| Jev 文字 | 无深度文字 | G1 | [成功](../../runs/jev-simple-rgbgs-none-20261008-01/summary.json) | 18 | 1 | 0 | 3.996 | 0.255777 | 0.255777 | 1.000 |
| Jev 文字 | 无深度文字 | G2 | [成功](../../runs/jev-simple-rgbgs-none-20261008-02/summary.json) | 18 | 1 | 0 | 3.996 | 0.255777 | 0.255777 | 1.000 |
| OpenAI 纯文字 | 无深度文字 | 01 | [失败：提前停止](../../runs/openai-decisions-simple-rgbgs-none-20261009-01/summary.json) | 75 | 17 | 0 | 6.918 | 0.462650 | 0.462650 | 0.000 |
| OpenAI 纯文字 | 无深度文字 | 02 | [失败：提前停止](../../runs/openai-decisions-simple-rgbgs-none-20261009-02/summary.json) | 75 | 17 | 0 | 6.918 | 0.462650 | 0.462650 | 0.000 |
| OpenAI 图文 | 无深度文字 | 01 | [成功](../../runs/openai-decisions-rgbtarget-simple-rgbgs-none-20261009-01/summary.json) | 40 | 1 | 0 | 3.996 | 0.250113 | 0.250113 | 1.000 |
| OpenAI 图文 | 无深度文字 | 02 | [成功](../../runs/openai-decisions-rgbtarget-simple-rgbgs-none-20261009-02/summary.json) | 40 | 1 | 0 | 3.996 | 0.250113 | 0.250113 | 1.000 |
| OneJev-4B 图文 | 无深度文字 | 01 | [失败：预算耗尽](../../runs/onejev-local-rgbtarget-simple-rgbgs-none-local-round-01/summary.json) | 100 | 16 | 0 | 15.486 | 1.068982 | 0.644320 | 0.000 |
| OneJev-4B 图文 | 无深度文字 | 02 | [失败：预算耗尽](../../runs/onejev-local-rgbtarget-simple-rgbgs-none-local-round-02/summary.json) | 100 | 16 | 0 | 15.486 | 1.068982 | 0.644320 | 0.000 |

## 复杂路线

| 方案 | 输入 | 批次 | 结果 | 动作数 | 碰撞 | 无效 | 累计路程 m | 最终距离 m | 最近距离 m | SPL |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| Jev 文字 | 数值深度 | H | [失败：预算耗尽](../../runs/jev-challenge-turn-000-clearance-aligned-01/summary.json) | 250 | 1 | 16 | 33.358 | 0.571755 | 0.340788 | 0.000 |
| Jev 文字 | 数值深度 | M1 | [成功](../../runs/jev-complex-numeric-20261008-01/summary.json) | 86 | 0 | 1 | 13.750 | 0.283747 | 0.283747 | 0.713 |
| Jev 文字 | 数值深度 | G1 | [失败：提前停止](../../runs/jev-complex-rgbgs-numeric-20261008-01/summary.json) | 119 | 1 | 9 | 15.228 | 0.303706 | 0.303706 | 0.000 |
| OpenAI 纯文字 | 数值深度 | 01 | [成功](../../runs/openai-decisions-complex-rgbgs-numeric-20261009-01/summary.json) | 86 | 0 | 0 | 12.000 | 0.278290 | 0.278290 | 0.816 |
| OpenAI 纯文字 | 数值深度 | 02 | [成功](../../runs/openai-decisions-complex-rgbgs-numeric-20261009-02/summary.json) | 86 | 0 | 0 | 12.000 | 0.278290 | 0.278290 | 0.816 |
| OpenAI 图文 | 数值深度 | 01 | [成功](../../runs/openai-decisions-rgbtarget-complex-rgbgs-numeric-20261009-01/summary.json) | 166 | 0 | 0 | 12.250 | 0.109957 | 0.109957 | 0.800 |
| OpenAI 图文 | 数值深度 | 02 | [成功](../../runs/openai-decisions-rgbtarget-complex-rgbgs-numeric-20261009-02/summary.json) | 166 | 0 | 0 | 12.250 | 0.109957 | 0.109957 | 0.800 |
| OneJev-4B 图文 | 数值深度 | 01 | [失败：预算耗尽](../../runs/onejev-local-rgbtarget-complex-rgbgs-numeric-local-round-01/summary.json) | 250 | 41 | 0 | 43.248 | 10.929754 | 9.535145 | 0.000 |
| OneJev-4B 图文 | 数值深度 | 02 | [失败：预算耗尽](../../runs/onejev-local-rgbtarget-complex-rgbgs-numeric-local-round-02/summary.json) | 250 | 41 | 0 | 43.248 | 10.929754 | 9.535145 | 0.000 |
| Jev 文字 | 语义深度 | G1 | [失败：提前停止](../../runs/jev-complex-rgbgs-semantic-20261008-01/summary.json) | 124 | 1 | 6 | 15.901 | 0.351736 | 0.351736 | 0.000 |
| Jev 文字 | 语义深度 | M1 | [成功](../../runs/jev-complex-semantic-20261008-01/summary.json) | 76 | 0 | 0 | 13.000 | 0.265350 | 0.265350 | 0.754 |
| OpenAI 纯文字 | 语义深度 | 01 | [成功](../../runs/openai-decisions-complex-rgbgs-semantic-20261009-01/summary.json) | 156 | 0 | 9 | 11.750 | 0.241567 | 0.241567 | 0.834 |
| OpenAI 纯文字 | 语义深度 | 02 | [成功](../../runs/openai-decisions-complex-rgbgs-semantic-20261009-02/summary.json) | 156 | 0 | 9 | 11.750 | 0.241567 | 0.241567 | 0.834 |
| OpenAI 图文 | 语义深度 | 01 | [成功](../../runs/openai-decisions-rgbtarget-complex-rgbgs-semantic-20261009-01/summary.json) | 94 | 0 | 1 | 12.000 | 0.234743 | 0.234743 | 0.816 |
| OpenAI 图文 | 语义深度 | 02 | [成功](../../runs/openai-decisions-rgbtarget-complex-rgbgs-semantic-20261009-02/summary.json) | 94 | 0 | 1 | 12.000 | 0.234743 | 0.234743 | 0.816 |
| OneJev-4B 图文 | 语义深度 | 01 | [失败：预算耗尽](../../runs/onejev-local-rgbtarget-complex-rgbgs-semantic-local-round-01/summary.json) | 250 | 32 | 0 | 55.494 | 10.550807 | 9.535145 | 0.000 |
| OneJev-4B 图文 | 语义深度 | 02 | [失败：预算耗尽](../../runs/onejev-local-rgbtarget-complex-rgbgs-semantic-local-round-02/summary.json) | 250 | 32 | 0 | 55.494 | 10.550807 | 9.535145 | 0.000 |
| Jev 文字 | 无深度文字 | H | [失败：预算耗尽](../../runs/jev-challenge-turn-000-clearance-aligned-no-depth-01/summary.json) | 250 | 29 | 0 | 43.098 | 0.910429 | 0.910429 | 0.000 |
| Jev 文字 | 无深度文字 | G1 | [成功](../../runs/jev-complex-rgbgs-none-20261008-01/summary.json) | 77 | 6 | 0 | 13.430 | 0.294787 | 0.294787 | 0.730 |
| OpenAI 纯文字 | 无深度文字 | 01 | [失败：预算耗尽](../../runs/openai-decisions-complex-rgbgs-none-20261009-01/summary.json) | 250 | 106 | 0 | 31.390 | 0.689694 | 0.322039 | 0.000 |
| OpenAI 纯文字 | 无深度文字 | 02 | [失败：预算耗尽](../../runs/openai-decisions-complex-rgbgs-none-20261009-02/summary.json) | 250 | 106 | 0 | 31.390 | 0.689694 | 0.322039 | 0.000 |
| OpenAI 图文 | 无深度文字 | 01 | [成功](../../runs/openai-decisions-rgbtarget-complex-rgbgs-none-20261009-01/summary.json) | 158 | 0 | 0 | 11.750 | 0.177727 | 0.177727 | 0.834 |
| OpenAI 图文 | 无深度文字 | 02 | [成功](../../runs/openai-decisions-rgbtarget-complex-rgbgs-none-20261009-02/summary.json) | 158 | 0 | 0 | 11.750 | 0.177727 | 0.177727 | 0.834 |
| OneJev-4B 图文 | 无深度文字 | 01 | [失败：预算耗尽](../../runs/onejev-local-rgbtarget-complex-rgbgs-none-local-round-01/summary.json) | 250 | 1 | 0 | 2.122 | 9.825023 | 9.535145 | 0.000 |
| OneJev-4B 图文 | 无深度文字 | 02 | [失败：预算耗尽](../../runs/onejev-local-rgbtarget-complex-rgbgs-none-local-round-02/summary.json) | 250 | 1 | 0 | 2.122 | 9.825023 | 9.535145 | 0.000 |

## 长路线

| 方案 | 输入 | 批次 | 结果 | 动作数 | 碰撞 | 无效 | 累计路程 m | 最终距离 m | 最近距离 m | SPL |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| Jev 文字 | 数值深度 | G1 | [成功](../../runs/jev-extended-rgbgs-numeric-20261008-01/summary.json) | 252 | 0 | 4 | 30.000 | 0.161575 | 0.161575 | 0.544 |
| Jev 文字 | 数值深度 | G2 | [失败：预算耗尽](../../runs/jev-extended-rgbgs-numeric-20261008-02/summary.json) | 500 | 1 | 78 | 30.721 | 9.730200 | 9.730200 | 0.000 |
| OpenAI 纯文字 | 数值深度 | 01 | [失败：提前停止](../../runs/openai-decisions-extended-rgbgs-numeric-20261009-01/summary.json) | 194 | 0 | 0 | 20.500 | 0.308222 | 0.308222 | 0.000 |
| OpenAI 纯文字 | 数值深度 | 02 | [失败：提前停止](../../runs/openai-decisions-extended-rgbgs-numeric-20261009-02/summary.json) | 194 | 0 | 0 | 20.500 | 0.308222 | 0.308222 | 0.000 |
| OpenAI 图文 | 数值深度 | 01 | [成功](../../runs/openai-decisions-rgbtarget-extended-rgbgs-numeric-20261009-01/summary.json) | 334 | 0 | 0 | 20.000 | 0.208400 | 0.208400 | 0.816 |
| OpenAI 图文 | 数值深度 | 02 | [成功](../../runs/openai-decisions-rgbtarget-extended-rgbgs-numeric-20261009-02/summary.json) | 334 | 0 | 0 | 20.000 | 0.208400 | 0.208400 | 0.816 |
| OneJev-4B 图文 | 数值深度 | 01 | [失败：预算耗尽](../../runs/onejev-local-rgbtarget-extended-rgbgs-numeric-local-round-01/summary.json) | 500 | 29 | 0 | 37.644 | 16.466812 | 15.533697 | 0.000 |
| OneJev-4B 图文 | 数值深度 | 02 | [失败：预算耗尽](../../runs/onejev-local-rgbtarget-extended-rgbgs-numeric-local-round-02/summary.json) | 500 | 29 | 0 | 37.644 | 16.466812 | 15.533697 | 0.000 |
| Jev 文字 | 语义深度 | G1 | [失败：预算耗尽](../../runs/jev-extended-rgbgs-semantic-20261008-01/summary.json) | 500 | 0 | 18 | 57.500 | 1.776616 | 0.455551 | 0.000 |
| Jev 文字 | 语义深度 | G2 | [失败：预算耗尽](../../runs/jev-extended-rgbgs-semantic-20261008-02/summary.json) | 500 | 0 | 16 | 55.000 | 1.209574 | 0.750022 | 0.000 |
| OpenAI 纯文字 | 语义深度 | 01 | [成功](../../runs/openai-decisions-extended-rgbgs-semantic-20261009-01/summary.json) | 351 | 0 | 3 | 19.750 | 0.261363 | 0.261363 | 0.826 |
| OpenAI 纯文字 | 语义深度 | 02 | [成功](../../runs/openai-decisions-extended-rgbgs-semantic-20261009-02/summary.json) | 351 | 0 | 3 | 19.750 | 0.261363 | 0.261363 | 0.826 |
| OpenAI 图文 | 语义深度 | 01 | [成功](../../runs/openai-decisions-rgbtarget-extended-rgbgs-semantic-20261009-01/summary.json) | 313 | 0 | 0 | 19.750 | 0.258362 | 0.258362 | 0.826 |
| OpenAI 图文 | 语义深度 | 02 | [成功](../../runs/openai-decisions-rgbtarget-extended-rgbgs-semantic-20261009-02/summary.json) | 313 | 0 | 0 | 19.750 | 0.258362 | 0.258362 | 0.826 |
| OneJev-4B 图文 | 语义深度 | 01 | [失败：预算耗尽](../../runs/onejev-local-rgbtarget-extended-rgbgs-semantic-local-round-01/summary.json) | 500 | 51 | 0 | 113.144 | 16.466812 | 15.533697 | 0.000 |
| OneJev-4B 图文 | 语义深度 | 02 | [失败：预算耗尽](../../runs/onejev-local-rgbtarget-extended-rgbgs-semantic-local-round-02/summary.json) | 500 | 51 | 0 | 113.144 | 16.466812 | 15.533697 | 0.000 |
| Jev 文字 | 无深度文字 | G1 | [失败：预算耗尽](../../runs/jev-extended-rgbgs-none-20261008-01/summary.json) | 500 | 46 | 0 | 84.058 | 1.497800 | 0.397036 | 0.000 |
| Jev 文字 | 无深度文字 | G2 | [失败：预算耗尽](../../runs/jev-extended-rgbgs-none-20261008-02/summary.json) | 500 | 112 | 0 | 84.545 | 15.817625 | 13.095512 | 0.000 |
| OpenAI 纯文字 | 无深度文字 | 01 | [成功](../../runs/openai-decisions-extended-rgbgs-none-20261009-01/summary.json) | 202 | 7 | 0 | 28.071 | 0.173495 | 0.173495 | 0.581 |
| OpenAI 纯文字 | 无深度文字 | 02 | [成功](../../runs/openai-decisions-extended-rgbgs-none-20261009-02/summary.json) | 202 | 7 | 0 | 28.071 | 0.173495 | 0.173495 | 0.581 |
| OpenAI 图文 | 无深度文字 | 01 | [成功](../../runs/openai-decisions-rgbtarget-extended-rgbgs-none-20261009-01/summary.json) | 428 | 0 | 0 | 19.750 | 0.096026 | 0.096026 | 0.826 |
| OpenAI 图文 | 无深度文字 | 02 | [成功](../../runs/openai-decisions-rgbtarget-extended-rgbgs-none-20261009-02/summary.json) | 428 | 0 | 0 | 19.750 | 0.096026 | 0.096026 | 0.826 |
| OneJev-4B 图文 | 无深度文字 | 01 | [失败：预算耗尽](../../runs/onejev-local-rgbtarget-extended-rgbgs-none-local-round-01/summary.json) | 500 | 3 | 0 | 6.044 | 15.903454 | 15.533697 | 0.000 |
| OneJev-4B 图文 | 无深度文字 | 02 | [失败：预算耗尽](../../runs/onejev-local-rgbtarget-extended-rgbgs-none-local-round-02/summary.json) | 500 | 3 | 0 | 6.044 | 15.903454 | 15.533697 | 0.000 |
