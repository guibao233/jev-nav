# 新增长距离复杂路线：extended-000

最终任务入口：[tasks.json](tasks.json)。这是静态规划与 CPU NavMesh 检查结果，尚未执行 Jev，不代表模型导航成功。

| 指标 | 原复杂路线 turn-000 | 新路线 extended-000 |
|---|---:|---:|
| NavMesh 最短距离 | 9.80 m | 16.32 m |
| 提供给模型的参考路线长度 | 11.71 m | 19.61 m |
| 原最短路径中 >=30 度转折 | 2 | 4 |

起点 XYZ：`[4.764145374298096, -0.125, 8.730498313903809]`；终点 XYZ：`[-2.4024908542633057, -0.125, 3.816352605819702]`。初始 yaw=-84.42 度，pitch=0 度，与首个局部目标对齐。最短/直线绕行比 1.88。

沿现有 NavMesh 的居中参考路线，每 0.025 m 采样测得额外边界余量最小 0.258 m，P10 0.457 m，中位 0.710 m。原 NavMesh 已计入半径约 0.10 m 的机器人；这些量是额外 NavMesh 边界余量，不是 mesh 碰撞保证，也不保证实际 Jev 轨迹保持同样余量。

## 预览

- [路线及初始朝向、首目标、前方采样点](route.png)。图中 >=30 度转折数来自原最短路径。
- [居中路线与原最短路线对照](route-comparison.png)。蓝实线为参考路线，紫虚线为原最短路线。
- [CPU 验证记录](validation.json)。所有 13 段直连检查通过，长度、端点、源文件哈希和初始对齐通过。

## 运行

在 habitat-gs 环境并配置好 OPENROUTER_API_KEY 后，运行 [commands.sh](commands.sh) 可按数值、语义、无深度顺序执行三组真实模型测试。三组共用一个任务、500 步预算、七动作、当前提示词和目标更新策略；只改变输入模式。该脚本尚未执行。

```bash
conda activate habitat-gs
bash /data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav/tasks/extended-clearance-aligned-20261008-01/commands.sh
```

输出目录分别为 runs/jev-extended-rgbgs-numeric-20261008-01、runs/jev-extended-rgbgs-semantic-20261008-01、runs/jev-extended-rgbgs-none-20261008-01。重复实验请修改输出后缀，保留所有结果。GPU 可用性变化时编辑 commands.sh 的 CUDA_VISIBLE_DEVICES。

`--rgb gs` 仅用于回放，RGB 不发送给模型；所有带深度条件仍使用 mesh 深度。预算必须显式传入 `--max-steps 500`，运行器不会自动读取任务文件里的 suggested_max_steps。SPL 基准仍是原最短距离 16.32 m。

## 生成来源

种子 20261008，最大连通区域；接受第 165 对端点，筛选条件为最短 16–20 m、至少三次 >=30 度转折、绕行比 >=1.35、平面高度跨度 <=0.02 m、起终点额外余量 >=0.25 m；随后必须通过现有居中规划器及额外余量 >=0.10 m 检查。没有根据 Jev 表现选择。

使用既有 ClearancePlanner，网格 0.10 m、余量衰减尺度 0.20 m、权重 4、padding 2 m。初始朝向由既有 prepare_initial_heading.py 对齐。../extended-v2-20261008-01 保存原任务、筛选脚本和居中中间结果。第 42 对候选在网格规划失败后排除，未作为执行任务。既有任务、导航代码、配置、资产及历史实验未修改。
