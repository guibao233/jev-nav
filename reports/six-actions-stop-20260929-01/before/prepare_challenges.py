#!/usr/bin/env python3
"""Sample longer reference paths and export static route previews. No GPU or API."""
import argparse
import hashlib
import json
import math
from html import escape
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from core import RoutePreview
from environment import load_pathfinder, shortest
from map_view import FONT_PATH, draw_map
from run import ROOT, asset_manifest, load_config


TIERS = {
    "control": {"label": "长直线对照", "min_m": 6., "max_m": 10.,
                "min_turns": 0, "max_turns": 0, "min_ratio": 1., "max_ratio": 1.02},
    "turn": {"label": "中距离转弯", "min_m": 6., "max_m": 10.,
             "min_turns": 1, "max_turns": 2, "min_ratio": 1.10},
    "long": {"label": "长距离多转弯", "min_m": 10., "max_m": 15.,
             "min_turns": 2, "min_ratio": 1.15},
    "extended": {"label": "更长绕行", "min_m": 15., "max_m": 20.,
                 "min_turns": 3, "min_ratio": 1.20},
}
TURN_THRESHOLD_DEG = 30.


def route_geometry(points, geodesic_m):
    """Count >=30 degree X/Z heading changes at original NavMesh path vertices.

    Duplicate horizontal vertices are removed only for measurements, never from
    the reference path. These are geometric bends, not semantic room corners.
    """
    pts = np.asarray(points, dtype=float)
    if (pts.ndim != 2 or pts.shape[1] != 3 or len(pts) < 2 or
            not np.isfinite(pts).all() or not math.isfinite(geodesic_m) or geodesic_m <= 0):
        raise ValueError("expected a finite positive-length XYZ path")
    vec = np.diff(pts[:, [0, 2]], axis=0)
    lengths = np.linalg.norm(vec, axis=1)
    directions = vec[lengths > 1e-6] / lengths[lengths > 1e-6, None]
    if len(directions) == 0:
        raise ValueError("path has no horizontal displacement")
    angles = np.degrees(np.arccos(np.clip(np.sum(directions[:-1]*directions[1:], axis=1), -1, 1)))
    euclidean = float(np.linalg.norm(pts[-1]-pts[0]))
    return {"euclidean_m": euclidean,
            "geodesic_to_euclidean_ratio": float(geodesic_m / max(euclidean, 1e-6)),
            "significant_turns": int(np.count_nonzero(angles >= TURN_THRESHOLD_DEG-1e-7)),
            "turn_threshold_deg": TURN_THRESHOLD_DEG,
            "turn_angles_deg": angles.tolist(), "total_abs_turn_deg": float(angles.sum()),
            "path_vertices": len(pts), "path_height_span_m": float(np.ptp(pts[:, 1]))}


def matches_tier(distance, geometry, tier):
    return (tier["min_m"] <= distance <= tier["max_m"] and
            tier["min_turns"] <= geometry["significant_turns"] <= tier.get("max_turns", math.inf) and
            tier["min_ratio"]-1e-6 <= geometry["geodesic_to_euclidean_ratio"] <= tier.get("max_ratio", math.inf))


def sample_challenges(cfg, per_tier, seed, max_attempts=50000):
    if per_tier <= 0 or max_attempts <= 0:
        raise ValueError("per-tier and max-attempts must be positive")
    pf = load_pathfinder(cfg)
    pf.seed(seed)
    rng = np.random.default_rng(seed)
    island = max(range(pf.num_islands), key=pf.island_area)
    buckets = {name: [] for name in TIERS}
    seen = set()
    for attempt in range(1, max_attempts+1):
        start = np.asarray(pf.get_random_navigable_point(island_index=island))
        goal = np.asarray(pf.get_random_navigable_point_near(start, 20., island_index=island))
        if not np.isfinite(start).all() or not np.isfinite(goal).all():
            continue
        if not pf.is_navigable(start) or not pf.is_navigable(goal) or abs(start[1]-goal[1]) > .25:
            continue
        clearance = [float(pf.distance_to_closest_obstacle(p, .25)) for p in (start, goal)]
        if min(clearance) < .10:
            continue
        path = shortest(pf, start, goal)
        if path is None or not 6. <= path[0] <= 20.:
            continue
        geometry = route_geometry(path[1], path[0])
        if geometry["path_height_span_m"] > .25:
            continue
        # Deduplicate endpoint pairs including reversed direction.
        key = tuple(sorted(tuple(np.round(p, 3)) for p in (start, goal)))
        if key in seen:
            continue
        for name, tier in TIERS.items():
            if len(buckets[name]) >= per_tier or not matches_tier(path[0], geometry, tier):
                continue
            task = {"id": f"{name}-{len(buckets[name]):03d}", "category": name,
                    "start": start.tolist(), "goal": goal.tolist(),
                    "yaw_deg": float(rng.uniform(-180, 180)), "pitch_deg": 0,
                    "geodesic_m": path[0], "path": path[1],
                    "geodesic_to_euclidean_ratio": geometry["geodesic_to_euclidean_ratio"],
                    "geometry": geometry,
                    "endpoint_extra_navmesh_clearance_m_capped_at_0_25": clearance}
            buckets[name].append(task)
            seen.add(key)
            break
        if all(len(group) == per_tier for group in buckets.values()):
            break
    if not all(len(group) == per_tier for group in buckets.values()):
        counts = {name: len(group) for name, group in buckets.items()}
        raise RuntimeError(f"insufficient matching paths after {max_attempts} attempts: {counts}")
    dataset = {"schema": 1, "seed": seed, "sampling_attempts": attempt,
               "sampling_policy": "first qualifying unique pairs per tier; random initial yaw; no model-based selection",
               "category_definition": "original polyline X/Z bends >=30 deg plus geodesic length and detour ratio",
               "tiers": TIERS, "per_tier": per_tier,
               "suggested_max_steps": 500,
               "budget_note": "run.py does not read suggested_max_steps; pass --max-steps 500 explicitly",
               "scene_dir": str(Path(cfg["scene_dir"]).resolve()),
               "agent_radius_m": cfg["agent_radius_m"], "agent_height_m": cfg["agent_height_m"],
               "config_at_generation": cfg.copy(), "assets": asset_manifest(cfg),
               "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "tasks": [task for group in buckets.values() for task in group]}
    return dataset, pf


def route_image(pf, task, cfg):
    """Show the planned initial target/preview, explicitly not an executed run."""
    resolution = .05
    nav = pf.get_topdown_view(resolution, float(task["start"][1]))
    pixels = np.full((*nav.shape, 3), 32, dtype=np.uint8)
    pixels[nav.astype(bool)] = [215, 219, 226]
    low, _ = pf.get_bounds()
    meta = {"task": task, "map": {"origin_x": float(low[0]), "origin_z": float(low[2]),
            "resolution_m": resolution, "width": nav.shape[1], "height": nav.shape[0]}}
    yaw = math.radians(task["yaw_deg"])
    record = {"pose": {"position": task["start"], "yaw_rad": yaw},
              "request": {"state": {"reference": RoutePreview(task["path"]).state(task["start"], yaw, cfg)}}}
    panel = draw_map(Image.fromarray(pixels), meta, [record], 0)
    image = Image.new("RGB", (640, 536), "#131923")
    image.paste(panel, (0, 56))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(FONT_PATH, 17)
    g = task["geometry"]
    draw.text((12, 3), f"{task['id']} | {task['geodesic_m']:.2f} m | ≥30°转折 {g['significant_turns']} | 绕行比 {g['geodesic_to_euclidean_ratio']:.2f}", font=font, fill="white")
    draw.text((12, 29), "计划预览：尚未执行 Jev；T/青点为初始输入预览", font=font, fill="#ffd27c")
    return image


def write_bundle(out, dataset, pf, cfg):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    (out/"maps").mkdir()
    (out/"tasks.json").write_text(json.dumps(dataset, indent=2, ensure_ascii=False, allow_nan=False)+"\n")
    tasks = dataset["tasks"]
    tiles = []
    table = ["| 任务 ID | 最短距离 m | ≥30° 转折数 | 绕行比 |", "|---|---:|---:|---:|"]
    cards = []
    for task in tasks:
        image = route_image(pf, task, cfg)
        image.save(out/"maps"/(task["id"]+".png"))
        tiles.append(image)
        g = task["geometry"]
        table.append(f"| {task['id']} | {task['geodesic_m']:.2f} | {g['significant_turns']} | {g['geodesic_to_euclidean_ratio']:.2f} |")
        cards.append(f'<article><h2>{escape(task["id"])} · {TIERS[task["category"]]["label"]}</h2><a href="maps/{task["id"]}.png"><img src="maps/{task["id"]}.png" width="640" height="536"></a></article>')
    columns = min(dataset["per_tier"], 3)
    overview = Image.new("RGB", (640*columns, 536*math.ceil(len(tiles)/columns)), "#131923")
    for i, tile in enumerate(tiles):
        overview.paste(tile, (640*(i % columns), 536*(i//columns)))
    overview.save(out/"overview.png")
    (out/"index.html").write_text('<!doctype html><html lang="zh"><meta charset="utf-8"><title>Jev 长路线任务预览</title><style>body{background:#131923;color:#e4e9ef;font:16px system-ui;margin:24px}main{display:flex;flex-wrap:wrap;gap:16px}img{max-width:100%;height:auto}a{color:#91bbff}h2{font-size:19px}</style><h1>Jev 长路线任务预览</h1><p>任务几何已验证，尚未运行模型。蓝线：固定最短路径；S/G：起终点；白箭头：初始朝向；T/青点：计划的初始局部目标与路径预览。</p><p>转折数是原路径顶点处 ≥30° 的水平朝向变化次数，不等同于房间或墙角数量。NavMesh 连续可达不保证离散动作无碰撞成功。</p><main>'+''.join(cards)+'</main></html>')
    try:
        task_arg = (out/"tasks.json").resolve().relative_to(ROOT)
    except ValueError:
        task_arg = (out/"tasks.json").resolve()
    import shlex
    command = f"python run.py run --tasks {shlex.quote(str(task_arg))} --episode turn-000 \\\n  --out runs/jev-challenge-turn-000-01 --rgb gs --max-steps 500"
    readme = f"""# 长路线固定任务集

这是尚未运行模型的计划任务，不能当作导航结果。种子 {dataset['seed']}，每档 {dataset['per_tier']} 条，共 {len(tasks)} 条，采样 {dataset['sampling_attempts']} 次。按固定种子接受首批符合几何条件且端点不重复的路线，没有根据 Jev 表现筛选。

- control：6–10 m，零个 ≥30° 转折，绕行比 ≤1.02，作为长度对照。
- turn：6–10 m，1–2 个 ≥30° 转折，绕行比 ≥1.10。
- long：10–15 m，至少 2 个 ≥30° 转折，绕行比 ≥1.15。
- extended：15–20 m，至少 3 个 ≥30° 转折，绕行比 ≥1.20。

绕行比 = NavMesh 最短距离 / 起终点三维直线距离。转折只统计原最短路径顶点处的水平角度变化；不修改、简化原路线。端点在同一连通区域，端点额外 NavMesh 边界留白 ≥0.10 m，全路径高度跨度 ≤0.25 m。这里确认连续几何可达，不承诺 0.25 m 平移、15° 转向能够无碰撞完成。初始朝向与基础任务一样随机。

## 查看路线

打开 [静态预览](index.html) 或 [路线总览](overview.png)，也可单独查看 `maps/*.png`。粉色 T 和青色采样点是由现有 RoutePreview 为起始状态计算的计划输入，没有发送 API。底图按每条任务的起始高度投影。

{chr(10).join(table)}

## 运行与比较

在 jev_nav 目录、habitat-gs 环境及已配置 OPENROUTER_API_KEY 的终端运行。建议顺序 control-000 → turn-000 → long-000 → extended-000；随后运行每档其余两条，并保留所有失败。先尝试带转弯的任务可用：

```bash
{command}
python visualize.py --run runs/jev-challenge-turn-000-01 --serve --port 8765
```

替换 `--episode` 及 `--out` 即可切换任务；输出目录必须未存在。所有档位显式使用 `--max-steps 500`，与审核的成功运行保持一致；`run.py` 不会读取数据集中的 suggested_max_steps。仍用默认九动作、3 m 路径预览、0.75 m 当前目标、mesh 深度和最近 5 步自身历史。无重规划、无规则动作替换。为保持可比性，不在此任务集上同时修改提示词或深度处理。

每档目前只有 3 条，适合摸底，不足以推断稳定成功率。比较无碰撞成功、总成功、碰撞、无效动作、总决策步数、SPL、首次到达后的停止延迟及请求 P50/P95；SPL 只衡量平移轨迹，不计原地转向/观察耗时。单个成功不能证明模型充分利用深度；需要对照才能确定贡献。
"""
    (out/"README.md").write_text(readme)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT/"config.json"))
    parser.add_argument("--per-tier", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260930)
    parser.add_argument("--max-attempts", type=int, default=50000)
    parser.add_argument("--out", required=True, help="new output directory; refuses overwrite")
    args = parser.parse_args()
    if args.per_tier <= 0 or args.max_attempts <= 0:
        parser.error("--per-tier and --max-attempts must be positive")
    out = Path(args.out)
    if out.exists():
        parser.error(f"output already exists: {out}")
    cfg = load_config(args.config)
    dataset, pf = sample_challenges(cfg, args.per_tier, args.seed, args.max_attempts)
    write_bundle(out, dataset, pf, cfg)
    print("TASKS", out/"tasks.json", "count", len(dataset["tasks"]))
    print("PREVIEW", out/"index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
