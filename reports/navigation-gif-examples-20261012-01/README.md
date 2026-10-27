# 代表性导航序列 GIF

选取固定四模型对比中的 8 个成功或失败行为案例，用已有 GS RGB 与 NavMesh 记录离线生成。不是新的模型实验；片段按展示行为选择，不用于重新计算成功率或代表全部条件。所有选择的来源、范围和指标见下表及 export.json。

左侧为 RGB，右侧为 NavMesh。图文组优先显示该步实际发送的标注 JPEG；文字组 RGB 只供回放。红框/红圈叉表示上一动作后的碰撞，黄框/感叹号表示无效动作；事件叠加只用于展示，没有发送给模型。NavMesh 中蓝线为参考路线，橙线为累计执行轨迹，粉色 T 为当步局部目标，白箭头为身体朝向，绿色 S / 红色 G 为起终点。

每个原观察保留一帧，固定 5 帧/秒，末帧停留 0.8 秒；播放时间不是模型调用或实际实验耗时。没有插值、平滑、删除转向或无效动作帧。GIF 循环回到开头仅是播放设置，不是机器人自动重启。

## 展示序列

| 序列 | 范围（原观察索引，从0开始） | 整轮结果 | 片段动作 / 碰撞 / 无效 | GIF时长 | 文件 |
|---|---|---|---|---:|---|
| Jev 文字｜简单路线｜数值深度 | 全程 0–18 | 成功 | 18 / 0 / 0 | 4.4s | [GIF](gifs/01-jev-simple-success.gif) / [静态预览](posters/01-jev-simple-success.png) |
| OpenAI 纯文字｜复杂路线｜数值深度 | 全程 0–86 | 成功 | 86 / 0 / 0 | 18.0s | [GIF](gifs/02-openai-text-complex-success.gif) / [静态预览](posters/02-openai-text-complex-success.png) |
| OpenAI 图文｜复杂路线｜语义深度 | 全程 0–94 | 成功 | 94 / 0 / 1 | 19.6s | [GIF](gifs/03-openai-rgb-complex-success.gif) / [静态预览](posters/03-openai-rgb-complex-success.png) |
| OpenAI 图文｜长路线｜语义深度 | 局部片段 269–313 | 成功 | 44 / 0 / 0 | 9.6s | [GIF](gifs/04-openai-rgb-marker-and-stop.gif) / [静态预览](posters/04-openai-rgb-marker-and-stop.png) |
| OpenAI 纯文字｜复杂路线｜无深度文字 | 局部片段 121–156 | 失败：action_budget | 35 / 25 / 0 | 7.8s | [GIF](gifs/05-openai-text-collision.gif) / [静态预览](posters/05-openai-text-collision.png) |
| OneJev-4B 图文｜简单路线｜数值深度 | 全程 0–100 | 失败：action_budget | 100 / 19 / 0 | 20.8s | [GIF](gifs/06-onejev-forward-backward.gif) / [静态预览](posters/06-onejev-forward-backward.png) |
| OneJev-4B 图文｜复杂路线｜无深度文字 | 局部片段 9–57 | 失败：action_budget | 48 / 0 / 0 | 10.4s | [GIF](gifs/07-onejev-stationary-turns.gif) / [静态预览](posters/07-onejev-stationary-turns.png) |
| Jev 文字｜长路线｜语义深度 | 局部片段 440–500 | 失败：action_budget | 60 / 0 / 8 | 12.8s | [GIF](gifs/08-jev-long-route-failure.gif) / [静态预览](posters/08-jev-long-route-failure.png) |

## 案例说明

- **Jev 文字｜简单路线｜数值深度**：完整过程：快速跟随并主动停止。 来源 [jev-simple-rgbgs-numeric-20261008-01](../../runs/jev-simple-rgbgs-numeric-20261008-01/summary.json)。
- **OpenAI 纯文字｜复杂路线｜数值深度**：完整过程：经过转角，零碰撞到达并停止。 来源 [openai-decisions-complex-rgbgs-numeric-20261009-01](../../runs/openai-decisions-complex-rgbgs-numeric-20261009-01/summary.json)。
- **OpenAI 图文｜复杂路线｜语义深度**：完整过程：转向、低头观察、路径跟随与停止；含一次无效俯仰。 来源 [openai-decisions-rgbtarget-complex-rgbgs-semantic-20261009-01](../../runs/openai-decisions-rgbtarget-complex-rgbgs-semantic-20261009-01/summary.json)。
- **OpenAI 图文｜长路线｜语义深度**：局部片段：最后接近与停止，包含第307次决策前的粉色圆环示例。 来源 [openai-decisions-rgbtarget-extended-rgbgs-semantic-20261009-01](../../runs/openai-decisions-rgbtarget-extended-rgbgs-semantic-20261009-01/summary.json)。
- **OpenAI 纯文字｜复杂路线｜无深度文字**：局部片段：35次动作窗口中碰撞最多的连续片段，展示受阻后的重复尝试。 来源 [openai-decisions-complex-rgbgs-none-20261009-01](../../runs/openai-decisions-complex-rgbgs-none-20261009-01/summary.json)。
- **OneJev-4B 图文｜简单路线｜数值深度**：完整过程：接近终点后反复前进/后退，伴随碰撞，预算耗尽。 来源 [onejev-local-rgbtarget-simple-rgbgs-numeric-local-round-01](../../runs/onejev-local-rgbtarget-simple-rgbgs-numeric-local-round-01/summary.json)。
- **OneJev-4B 图文｜复杂路线｜无深度文字**：局部片段：连续48次原地左转，位置保持不变；整轮最终失败。 来源 [onejev-local-rgbtarget-complex-rgbgs-none-local-round-01](../../runs/onejev-local-rgbtarget-complex-rgbgs-none-local-round-01/summary.json)。
- **Jev 文字｜长路线｜语义深度**：局部片段：最后60次动作，终点附近绕行与无效俯仰，预算耗尽。 来源 [jev-extended-rgbgs-semantic-20261008-01](../../runs/jev-extended-rgbgs-semantic-20261008-01/summary.json)。

无深度图文组仍有 RGB；GIF 中的导航地图仅供解释，没有作为图片发送给模型。最终状态/成功率依据整轮 summary.json，而非片段结束位置。OneJev 原地转圈片段的首帧会显示片段开始前一个动作的碰撞，所选48个转向动作本身没有碰撞。片段中的当前距离是上一动作完成后、与当前 RGB 位姿一致的 NavMesh 距离；下一动作尚未发生，避免将其碰撞结果提前叠在当前观察。

[浏览所有 GIF](index.html) · [静态总览](contact-sheet.png) · [片段与源哈希](export.json) · [逐帧来源/事件/目标](frame-manifest.json) · [复现脚本](export_gifs.py)

PNG/GIF 可直接用图片查看器或 VS Code 打开。index.html 不需要 JavaScript、服务器或模型服务。复现只需现有 habitat-gs 环境，传入新的目录：

```bash
conda activate habitat-gs
python reports/navigation-gif-examples-20261012-01/export_gifs.py /tmp/navigation-gif-recheck
```
