# 九方向语义深度：实现与验证

按已确认设计，给现有路径辅助导航增加语言深度表达，以两个现有目标进行实验。只完成模块与脚本验证；真实 Jev 运行由用户执行。

## 输入表达

原 core.depth_facts 的 mesh 反投影、俯仰补偿、地面/身体高度过滤、障碍支持检查、九扇区和前后扫掠体判断均保持。新增 depth_language.py 将原数值摘要转换为语言；提示词统一保持英文，避免同时引入整套语言变化。

| 水平最近已观测障碍距离 d | 英文表达 | 中文含义 |
|---|---|---|
| d ≤ 0.5 m | very close | 非常近 |
| 0.5 < d ≤ 1 m | close | 很近 |
| 1 < d ≤ 2 m | moderately near | 较近 |
| 2 < d ≤ 4 m | far | 较远 |
| d > 4 m | very far | 很远 |

采用已有两位小数摘要距离，不改变底层采样。九扇区按原来的右至左顺序命名，第五个为 straight ahead；边缘只表示前向视场边缘，不假装观察到正左/正右/后方。no_obstacle_seen/unknown 不映射为 far/clear。near_floor、表面观测范围、valid_fraction、运动体积覆盖分别转换为文字，status 保留 blocked/unknown/clear；描述与提示词强调距离不是安全余量，也不是动作建议。

--depth-format numeric 为默认，semantic 为本次实验；depth-input none 优先，继续不给深度输入。semantic 要求九扇区，错误配置在模型/渲染启动前拒绝。当前七动作和停止条件相同；新增语义说明，版本 seven_actions_reassociate_motion_v5_semantic_depth_v1。

request.state.depth 是真正发送给 Jev 的语义内容，其内部没有数值。steps.jsonl 顶层 depth_numeric_debug 保存原精确摘要，未加入 request；metadata 保存距离阈值和表达版本，同样不发给模型。路线目标数值、本体参数、历史和碰撞反馈继续提供。任务、NavMesh、相机初始姿态和动作能力均未改变。

## 目标与对照

| 实验 | 任务文件 / ID | 距离 | 初始姿态 | 预算 |
|---|---|---|---|---|
| 简单 | tasks/debug-10.json / episode-000 | 原最短约 4.20 m | 原 yaw≈10.95°，pitch=0° | 100 |
| 复杂 | tasks/challenge-clearance-aligned-20260930-01/tasks.json / turn-000 | 原最短≈9.80 m，参考≈11.71 m | 对齐 yaw=−90.39°，pitch=0° | 250 |

每条路线用当前 numeric 与 semantic 各跑一轮，其他参数相同。简单路线历史成功轮是九动作，不能直接作为当前七动作语义版的公平对照。复杂路线可参考已有当前 v5 baseline，但新一轮 numeric 能减少不同批次的干扰。单次运行只能说明个案；若需要成功率结论，建议同任务重复并扩展任务集合。

## 执行命令

在 habitat-gs Conda 环境下：

```bash
cd /data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav
# 在 habitat-gs 环境、jev_nav 目录运行。每条路线依次跑 numeric 和 semantic。
# 如果输出目录已存在，请改末尾编号；不会覆盖旧实验。

# 简单路线：原 debug episode-000，最短距离约 4.20 m，100 步预算。
for format in numeric semantic; do
  CUDA_VISIBLE_DEVICES=7 python run.py --config config.single-gpu.json run \
    --tasks tasks/debug-10.json --episode episode-000 \
    --out "runs/jev-simple-${format}-20261008-01" \
    --rgb mesh --max-steps 100 --depth-input mesh --depth-format "$format"
done

# 复杂路线：居中 + 初始身体朝向对齐的 turn-000，250 步预算。
for format in numeric semantic; do
  CUDA_VISIBLE_DEVICES=7 python run.py --config config.single-gpu.json run \
    --tasks tasks/challenge-clearance-aligned-20260930-01/tasks.json --episode turn-000 \
    --out "runs/jev-complex-${format}-20261008-01" \
    --rgb mesh --max-steps 250 --depth-input mesh --depth-format "$format"
done

```

上述共四轮真实模型任务；本次工具验证没有执行这些命令。--rgb mesh 降低显存压力；如需 GS 回放，可将两组都换成 gs，RGB 都不发给 Jev。每次使用新输出目录。

```bash
python visualize.py --run runs/jev-simple-semantic-20261008-01 --serve --port 8765
# 关闭上述服务后再运行下面一个，或改端口。
python visualize.py --run runs/jev-complex-semantic-20261008-01 --serve --port 8765
```

查看 request.state.depth.sectors 的 direction/distance_band/description，以及 near_floor 和 move_checks。numeric_debug 用于审核阈值与几何，不是模型实际接收内容。建议比较成功/停止、碰撞、无效动作、转向循环、实际路程和最终距离。

## 验证证据

- [初始红测试](tests-red.txt)、[完整 76 项回归](tests.txt)、[修改前后默认请求核对](historical-requests.json)。
- [独立验证脚本](verify.py) / [结果](verification.json)：从原始 NPZ 重算 8 份真实语义请求；检查方向、数值隔离、简单两组状态与动作一致，133 个受保护文件保持。
- [三个预设动作进程记录](smoke-process.json)，每组 move_forward,look_down,turn_left,stop，共 4 步、0 碰撞/无效、预期 early_stop，正常退出。子进程删除 API 密钥，未调用 Jev。
- [简单 numeric 回放](../../runs/smoke-semantic-simple-numeric-20261008-01/index.html)、[简单 semantic 回放](../../runs/smoke-semantic-simple-semantic-20261008-01/index.html)、[复杂 semantic 回放](../../runs/smoke-semantic-complex-semantic-20261008-01/index.html)。
- [便携复杂语义 HTML](viewer-complex/index.html)、[MP4](viewer-complex/media/rgb-depth.mp4)、[GIF](viewer-complex/media/rgb-depth.gif)：5 幅观察，H.264/yuv420p 1920×688、225 帧、7.5 秒；完整解码、GIF 时长、源哈希和 JS 语法通过。没有浏览器手工交互验证。
- [修改快照](implementation.patch)、before/ 与 [原文件保护清单](protected-before.json)。

本次新增的是语言表达条件，不能预先保证减少碰撞或提高成功率；模型效果等待用户运行上述四轮。
