# OpenAI RGB＋航点标记输入验证（2026-10-09）

已实现可选的当前 RGB 图像＋原有文字导航状态输入。默认纯文字请求保持不变。本次没有调用真实 API，不能据此报告模型导航能力或多模态在线成功率。

## 新输入与保存方式

- `--decision-model openai --rgb gs --rgb-input target_marked`：每步从同一时刻的 RGB 和位姿生成当前局部目标标记；最终目标仅在 `is_final=true` 时标记。
- 粉色圆环表示目标的相机几何投影；未进行遮挡检测，也不表示可直达。图像外和相机后方使用有文字说明的边缘箭头，不能解释成箭头所在位置就是地面目标。
- 同一图像同时考虑身体相对位置、相机实际俯仰、航点相对高度和相机内参。相机俯仰与初始化、参考路线、动作集合、步长和停止条件沿用原方案。
- 当前任务相机高度 1.5 m，局部目标通常约 0.75 m：平视时目标地面投影往往在图像下方，需模型主动下俯才能观察。不会自动改变初始俯仰。
- 与数值深度、语义深度、无深度三个条件组合；无深度＋RGB 表示没有文字深度摘要，但 RGB 仍提供视觉信息，不能与完全无环境观察混称。

协议依据：[OpenRouter 多模态 Decisions 文档](https://openrouter.ai/docs/guides/community/multimodal-decisions)。端点为 `/api/alpha/decisions`，`state` 为 `[JSON状态文字字符串, image_url部分]`，图像使用 JPEG data URL。不能使用 OpenAI 原生 `input_image` 格式，也不能把图像嵌在普通状态对象内。

`steps.jsonl` 中 `request` 保留可读文字状态；这是逻辑请求，不是含 base64 的完整网络包。`image_input.path` 指向实际发送的 `frames/NNNNN-model-rgb.jpg`，另记录该文件 SHA-256、尺寸、字节数、投影状态及标记像素。`wire_request_sha256` 对应完整网络包。实际客户端成功返回时还记录 `decision.request_body_sha256`。重建方式：

```python
from pathlib import Path
from jev import encode_request
body = encode_request(record['request'], (run_dir / record['image_input']['path']).read_bytes())
```

原 RGB 仍单独保存；输入图不带碰撞/无效动作事件标识，回放和导出才额外绘制事件。终态不发新请求，也不生成新的模型输入图。模拟烟测会准备图片，但 `is_model_evaluation=false`、`rgb_provided_to_model=false`；不能当作在线评估。

## 验证证据

| 检查 | 结果与范围 |
| --- | --- |
| 原版本回归 | 86 项通过，见 [baseline-tests.log](baseline-tests.log) |
| 完整新版本回归 | 103 项通过，见 [安装后测试](installed-tests.log) 和 [暂存版本测试](stage-tests.log) |
| 图像传输模拟 | mock HTTP 捕获发送体，解码 JPEG 与保存文件逐字节相同；保存图像/网络请求哈希一致 |
| 三种深度条件 | 数值、语义和无深度分别检查；无深度网络文字没有深度字段 |
| 默认请求不变 | 37 轮、6,880 条请求及序列化字节相同；229 个受保护文件未改，见 [default-request-parity.json](default-request-parity.json) |
| GPU mesh 烟测 | GPU 7 执行 look_down,look_down,look_down,stop；4 动作、0 碰撞、0 无效，提前停止是预设测试的预期结果 |
| 回放/媒体 | 含输入 JPEG 的便携 HTML；MP4 为 1920×688、H.264/yuv420p、225 帧、7.5 秒，导出器完整解码验证通过 |
| 九组命令 | dry-run 通过，见 [commands-rgb-target.txt](commands-rgb-target.txt)；预算 100/250/500 |

新测试先失败再实现，记录为 `red-tests.log`、`red-viewer-tests.log`、`red-marker-tests.log`、`red-smoke-identity.log`。覆盖针孔投影、前后方/相机平面、目标高度、原始像素不变、标记不被标题遮挡、缺图拒绝发送、CLI 前置校验、mock 请求保存流程、便携回放和批量命令。安装后的真实回放 JavaScript 通过 `node --check`，四幅实际输入 JPEG 及对应网络包哈希、便携副本也再次校验通过，见 [installed-artifact-check.json](installed-artifact-check.json)。没有进行原生浏览器手工交互验收。

第一次 GPU 尝试在受限沙箱中无法匹配 EGL/CUDA 设备；随后在可访问 GPU 的执行环境以同样配置成功运行。这不作为应用回归失败，没有修改 Habitat 源码或 Conda 环境。

### 实际 mesh 渲染标记结果

| 观察帧 | 俯仰 | 投影状态 | 标记 |
| --- | ---: | --- | --- |
| 0 | 0° | outside_frame | 下边缘箭头 |
| 1 | 15° | outside_frame | 下边缘箭头 |
| 2 | 30° | in_frame | 圆环 |
| 3 | 45° | in_frame | 圆环 |

[完整烟测回放](../../runs/smoke-rgb-target-20261009-01/visualizations/portable/index.html) · [MP4](../../runs/smoke-rgb-target-20261009-01/visualizations/portable/media/rgb-depth.mp4) · [GIF](../../runs/smoke-rgb-target-20261009-01/visualizations/portable/media/rgb-depth.gif)

烟测原执行位置在 `/tmp/jev-nav-rgb-target-20261009/smoke-rgb-target-verified`，完整产物复制到新 `runs/` 目录，原日志中的执行位置保留作为来源证据。三次低头之后提前停止；没有真实决策请求。

### 已有 GS RGB 的离线预览

使用历史 `openai-decisions-simple-rgbgs-semantic-20261009-01` 的第 0/3 帧，按当时相对目标、身体位姿及相机俯仰生成：

- [平视：画面外箭头](preview/frames/00000-model-rgb.jpg)
- [下俯 45°：航点圆环](preview/frames/00003-model-rgb.jpg)
- [来源与标记参数](preview/preview.json)

这是已有 GS RGB 的离线预览，没有重跑新的 GS 模型试验。新分支已完成实际 mesh 渲染，GS 在线图像发送仍需联调。

## 用户运行命令

```bash
conda activate habitat-gs
cd /data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav

# 先验证五步真实多模态接口；使用已配置的 OPENROUTER_API_KEY。
CUDA_VISIBLE_DEVICES=7 python run.py --config config.single-gpu.json run \
  --decision-model openai --rgb gs --rgb-input target_marked \
  --tasks tasks/debug-10.json --episode episode-000 \
  --out runs/openai-decisions-rgbtarget-connectivity-20261009-01 \
  --max-steps 5 --depth-input mesh --depth-format numeric

# 三种路线 × 数值/语义/无深度，先查看命令。
NAV_RGB_INPUT=target_marked CUDA_VISIBLE_DEVICES=7 \
  bash scripts/run_model_ablation.sh openai 20261009-01 --dry-run

# 两轮各九组。
NAV_RGB_INPUT=target_marked CUDA_VISIBLE_DEVICES=7 \
  bash scripts/run_model_ablation.sh openai 20261009-01
NAV_RGB_INPUT=target_marked CUDA_VISIBLE_DEVICES=7 \
  bash scripts/run_model_ablation.sh openai 20261009-02
```

新输出独立使用 `openai-decisions-rgbtarget-` 前缀。若目录已存在换批次编号。指定子集可设置 `ROUTES="simple complex"` / `MODES="numeric semantic none"`，需要更换 GPU 时覆盖 `CUDA_VISIBLE_DEVICES`。要恢复纯文字对照，省略 `NAV_RGB_INPUT` 或设为 `none`。

这是 RGB 与目标标记的联合输入实验，不能仅归因于 RGB 本身。真实多模态请求接收、模型行为、延迟和导航成绩需用户运行之后再汇总。

## 可复核文件

- [默认请求重建脚本](verify_default_requests.py)：只读取历史数据、在本报告目录写校验结果，不发送 API。
- [历史保护哈希](historical-hashes.json)、[代码变更](changes.patch)。
- `before/` 保留覆盖前源码，`after/` 保留本次安装源码，`installation.json` 保存各文件 SHA-256。
- 原历史实验、配置、任务、场景资产和模型服务配置未改写；没有安装依赖。
