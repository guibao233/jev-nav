# 碰撞与无效动作可视化（2026-09-29）

RGB 和 NavMesh 使用红色圈叉/边框表示碰撞，黄色方框叹号/边框表示无效动作；提示包含发生动作的步号及名称。地图保留已发生事件的机器人位置，高亮当前事件，切换回较早帧不会显示未来事件。

## 可以直接查看

- [真实 Jev 任务 HTML](../../runs/jev-challenge-turn-000-02/visualizations/events-20260929-01/index.html)：203 幅观察，20 次碰撞、28 次无效动作。这是已有运行的重新展示，不是新的导航实验。
- [真实 Jev 两类事件示例](event-examples.png)：第 31 步碰撞后与第 34 步无效低头后的 GS RGB / NavMesh。
- [8 帧验证 HTML](../../runs/collision-check-20260928-01/visualizations/events-20260929-01/index.html)。
- [验证 MP4](../../runs/collision-check-20260928-01/visualizations/events-20260929-01/media/rgb-depth.mp4)、[验证 GIF](../../runs/collision-check-20260928-01/visualizations/events-20260929-01/media/rgb-depth.gif)、[静态总览](../../runs/collision-check-20260928-01/visualizations/events-20260929-01/media/contact-sheet.png)。这是已有脚本仿真记录，非 Jev 能力验证。

## 时间与位置语义

`steps.jsonl` 一行的图片和位姿是本次动作执行前，而同一行的 outcome 是随后执行的结果。因此，观察 i 的高亮来自观察 i-1 的 outcome，而不是本行将执行动作的 outcome。最后终态同样显示上一动作。缺失 outcome 不会被推断为无效动作。RGB 高亮随观察更新，地图保留此前事件的位置。

地图点优先取该动作的 after_position；旧记录缺失时，取下一幅已保存观察的位置。位置指机器人执行后的位置，不表示实际墙面接触点。碰撞直接读取 collided=true，无效直接读取 valid=false，不依据模型文字或深度推断。

没有覆盖源 RGB/深度、日志或旧 HTML。新增叠加图写入生成目录的 navmap-frames-events/，目标请求保持原样；可视化历史事件只用于回放，不加入 Jev 短期记忆。

## 改动与检查

- 新增 replay_events.py；更新 map_view.py、replay.py、export_replay.py 和 visualize.py，以及文档。导航运行、参数、动作能力和模型提示没有变化。
- 37 项现有回归通过：[tests.log](tests.log)。
- 真实数据检查覆盖 211 幅观察，核对全部事件、原始字段、源图像哈希、动作前后时序、终态和缺失结果。8 帧 HTML/视频的 RGB 与地图逐像素相同。[检查脚本](verify_views.py)、[结果](verification.json)、[日志](verification.log)。
- 页面通过 Node 语法检查及实际 JS 的 DOM 桩验证，覆盖跳帧、前后按钮、键盘、播放和终态：[脚本](check_page.cjs)、[结果](page-check.log)。本地 HTTP 检查 5 类实际资源均为 200。没有真实浏览器手动验收。
- MP4 经 ffprobe 及完整解码校验：H.264/yuv420p、1920×688、30 fps、360 帧、12 秒；GIF 8 帧、12 秒。两类事件图片已目视检查。
- 两份导出各自 visualization.json 保存所用源文件哈希；21 个受保护导航代码/配置/历史记录另行核验未变。没有仿真或 API 调用。
- 修改前文件在 before/，补丁在 change.diff。

## 后续使用

```bash
python visualize.py --run runs/你的实验目录 --serve --port 8765
# 需要 MP4 / GIF 时增加 --media
```

从 jev_nav 目录运行，在 VS Code 中转发 8765 端口后用浏览器打开。新版自动生成独立目录；旧的 index.html 不会自行变化。后续新实验的默认回放也会包含这些标识。
