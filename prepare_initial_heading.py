#!/usr/bin/env python3
"""Create tasks facing the first local reference target; no GPU or API required."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from core import RoutePreview
from run import ROOT, load_config

POLICY = 'face_first_local_target_v1'
# These settings affect RoutePreview.state(), including its initial projection.
SELECTION_KEYS = ('move_m', 'preview_m', 'sample_spacing_m', 'target_lookahead_m')


def initial_target(task, yaw_deg, cfg):
    # Fresh tracker: match the first decision after Environment.reset().
    route = RoutePreview(task['path'])
    if not np.allclose(route.points[0], task['start'], atol=.03, rtol=0):
        raise ValueError('reference path start differs from task start')
    return route.state(task['start'], math.radians(yaw_deg), cfg)['current_target']


def align_task(original, cfg):
    old_yaw = float(original['yaw_deg'])
    if not math.isfinite(old_yaw):
        raise ValueError('initial yaw must be finite')
    before = initial_target(original, old_yaw, cfg)
    # At body yaw zero, the local bearing equals the world yaw toward the target.
    # Use the runner's target selector (including corner limits), not the final goal.
    world_target = initial_target(original, 0., cfg)
    if world_target['distance_m'] <= .001:
        raise ValueError('initial local target has no usable horizontal direction')
    yaw = (world_target['bearing_deg'] + 180.) % 360. - 180.
    after = initial_target(original, yaw, cfg)
    if abs(after['bearing_deg']) > .01 or after['forward_m'] <= 0:
        raise ValueError('failed to align initial local target')
    result = copy.deepcopy(original)
    result['yaw_deg'] = yaw
    result['initial_heading'] = {
        'policy': POLICY,
        'source_yaw_deg': old_yaw,
        'aligned_yaw_deg': yaw,
        'target_before': before,
        'target_after': after,
        'selection_config': {key: cfg[key] for key in SELECTION_KEYS},
        'bearing_resolution_deg': .01,
        'scope': 'initial horizontal heading only; pitch and runtime target selection unchanged',
    }
    return result


def build_dataset(dataset, cfg, selected=None):
    tasks = dataset['tasks']
    ids = [task['id'] for task in tasks]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError('source must contain nonempty, unique task IDs')
    selected = set(ids) if selected is None else set(selected)
    if not selected or not selected.issubset(ids):
        raise ValueError(f'empty selection or unknown task IDs: {sorted(selected-set(ids))}')
    result = copy.deepcopy(dataset)
    result['tasks'] = [align_task(task, cfg) for task in tasks if task['id'] in selected]
    result['initial_heading_policy'] = POLICY
    return result


def write_bundle(out, dataset):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    (out/'tasks.json').write_text(json.dumps(dataset, indent=2, ensure_ascii=False, allow_nan=False)+'\n')
    rows = ['| 任务 | 原 yaw ° | 新 yaw ° | 原目标方位 ° | 新目标方位 ° |', '|---|---:|---:|---:|---:|']
    for task in dataset['tasks']:
        h = task['initial_heading']
        rows.append(f"| {task['id']} | {h['source_yaw_deg']:.3f} | {h['aligned_yaw_deg']:.3f} | {h['target_before']['bearing_deg']:.2f} | {h['target_after']['bearing_deg']:.2f} |")
    (out/'README.md').write_text(
        '# 初始朝向对齐任务变体\n\n'
        '只调整 yaw_deg，按运行器现有规则对准第一个局部目标（含拐角截断），精度为方位字段的 0.01°。'
        '起终点、pitch、参考路线、原最短路线与评估距离均继承源任务；没有改变提示词或后续目标更新。\n\n'
        + '\n'.join(rows) + '\n\n'
        'initial_heading 保存原朝向、生成时目标选择参数和前后目标；initial_heading_source_tasks 保存直接来源，'
        '既有 source_tasks 等规划来源字段保留。继承的 config_at_generation 仍属于源任务生成过程。\n\n'
        '这是任务初始化条件，不是一次执行动作，不消耗动作预算。仅保证初始局部目标的水平方向对齐；'
        '不保证目标地面点在画面内、无遮挡或后续时刻一直在视野内。没有调用模型。'
        '复测需使用相同的 move_m、preview_m、sample_spacing_m、target_lookahead_m；改变这些参数后应重新生成。\n'
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(ROOT/'config.json'))
    parser.add_argument('--tasks', required=True)
    parser.add_argument('--episode', action='append', help='repeat to select several; omit for all')
    parser.add_argument('--out', required=True, help='new output directory; never overwrites existing data')
    args = parser.parse_args(argv)
    out = Path(args.out)
    if out.exists():
        raise FileExistsError(out)
    source = Path(args.tasks)
    source_bytes = source.read_bytes()
    cfg = load_config(args.config)
    result = build_dataset(json.loads(source_bytes), cfg, args.episode)
    result['initial_heading_source_tasks'] = {
        'path': str(source.resolve()), 'sha256': hashlib.sha256(source_bytes).hexdigest()}
    result['initial_heading_generator_sha256'] = {
        name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        for name in ('prepare_initial_heading.py', 'core.py')}
    write_bundle(out, result)
    for task in result['tasks']:
        h = task['initial_heading']
        print(json.dumps({'episode': task['id'], 'source_yaw_deg': h['source_yaw_deg'],
                          'aligned_yaw_deg': task['yaw_deg'],
                          'target_bearing_before_deg': h['target_before']['bearing_deg'],
                          'target_bearing_after_deg': h['target_after']['bearing_deg']}), flush=True)
    print('OUTPUT', out, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
