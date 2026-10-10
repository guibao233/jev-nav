"""Offline log/NavMesh audit; never renders, calls an API, or edits source runs."""
from pathlib import Path
from collections import Counter
import csv, hashlib, json, math, sys

ROOT = Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav')
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/tmp/openai-ablation-audit-20261009-01')
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
from environment import load_pathfinder, shortest
from depth_language import semantic_depth

ROUTES = ['simple', 'complex', 'extended']
MODES = ['numeric', 'semantic', 'none']
RL = dict(zip(ROUTES, ['简单路线', '复杂路线', '长路线']))
ML = dict(zip(MODES, ['数值深度', '语义深度', '无深度']))
TASKS = {'simple': 'tasks/debug-10.json', 'complex': 'tasks/challenge-clearance-aligned-20260930-01/tasks.json', 'extended': 'tasks/extended-clearance-aligned-20261008-01/tasks.json'}
IDS = dict(zip(ROUTES, ['episode-000', 'turn-000', 'extended-000']))
BUDGETS = dict(zip(ROUTES, [100, 250, 500]))
BASE = {k: next(t for t in json.loads((ROOT / v).read_text())['tasks'] if t['id'] == IDS[k]) for k, v in TASKS.items()}
baseline_path = ROOT / 'reports/route-ablation-summary-20261008-01/summary.json'
baseline = json.loads(baseline_path.read_text())
hashes = {}
def protect(path):
    hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
for path in [baseline_path, *(ROOT / v for v in TASKS.values())]:
    protect(path)
for path, digest in baseline['verification']['hashes'].items():
    assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, ('changed Jev baseline', path)
    hashes[path] = digest
common = {k: v for k, v in baseline['common_config'].items() if k != 'model'}
rows, details, pairs, records_by_key = [], {}, [], {}
all_response_ids = []
for route in ROUTES:
    for mode in MODES:
        baseline_row = next(r for r in baseline['rows'] if r['route'] == route and r['input'] == mode)
        baseline_first = json.loads((ROOT / 'runs' / baseline_row['run'] / 'steps.jsonl').read_text().splitlines()[0])
        for batch in ['01', '02']:
            name = f'openai-decisions-{route}-rgbgs-{mode}-20261009-{batch}'
            folder = ROOT / 'runs' / name
            m = json.loads((folder / 'metadata.json').read_text())
            s = json.loads((folder / 'summary.json').read_text())
            cfg, task = m['config'], m['task']
            assert m['provider'] == s['provider'] == 'openai_decisions'
            assert s['is_openai_decisions_evaluation'] and not s['is_jev_evaluation']
            assert s['response_models'] == ['openai/gpt-6-luna-decisions-20261006']
            assert m['prompt_version'].startswith('seven_actions_reassociate_motion_v5')
            assert cfg['max_steps'] == BUDGETS[route] and cfg['success_m'] == .3
            assert {k: v for k, v in cfg.items() if k not in ['gpu_id', 'depth_input', 'depth_format', 'max_steps', 'model']} == common
            assert all(task[k] == BASE[route][k] for k in ['start', 'goal', 'path', 'yaw_deg', 'pitch_deg'])
            assert m['rgb_mode'] == 'gs' and not m['rgb_provided_to_model']
            assert ('none' if m['depth_input'] == 'none' else m['depth_format']) == mode
            for filename in ['metadata.json', 'summary.json', 'steps.jsonl']:
                protect(folder / filename)
            records = [json.loads(line) for line in (folder / 'steps.jsonl').read_text().splitlines()]
            actions = records[:-1]
            records_by_key[route, mode, batch] = records
            assert len(actions) == s['steps'] and records[-1]['outcome'] is None
            assert [r['step'] for r in records] == list(range(len(records)))
            assert records[0]['request']['questions'] == baseline_first['request']['questions']
            assert records[0]['request']['state'] == baseline_first['request']['state']
            pf = load_pathfinder(dict(cfg))
            initial_d = shortest(pf, task['start'], task['goal'])[0]
            assert abs(initial_d - s['initial_geodesic_m']) < 1e-6
            travel, ds, latencies, cycles = 0., [], [], []
            for i, r in enumerate(actions):
                req, dec, outcome = r['request'], r['decision'], r['outcome']
                assert req['model'] == 'openai/gpt-6-luna-decisions'
                assert dec['response']['model'] == 'openai/gpt-6-luna-decisions-20261006'
                assert dec['choice'] == outcome['action'] == dec['response']['answers']['action']['choice']
                assert req['questions'] == baseline_first['request']['questions']
                assert math.dist(r['after_position'], records[i + 1]['pose']['position']) < 1e-6
                d = shortest(pf, r['after_position'], task['goal'])[0]
                ds.append(d)
                assert abs(d - r['metrics']['distance_to_goal_geodesic_m']) < 1e-6
                travel += math.dist(r['pose']['position'], r['after_position'])
                assert abs(travel - r['metrics']['path_length_m']) < 1e-4
                assert outcome['action'] in req['questions']['action']['criteria']
                if mode == 'none':
                    assert 'depth' not in req['state']
                elif mode == 'semantic':
                    assert semantic_depth(r['depth_numeric_debug']) == req['state']['depth']
                    assert 'depth_numeric_debug' not in json.dumps(req)
                else:
                    assert len(req['state']['depth']['sectors']) == 9
                assert not any(k in json.dumps(req) for k in ['image_url', 'data:image/', 'image/jpeg', 'image/png'])
                all_response_ids.append(dec['response']['id'])
                latencies.append(dec['latency_s']); cycles.append(r['metrics']['cycle_s'])
            collisions = sum(r['outcome']['collided'] for r in actions)
            invalid = sum(not r['outcome']['valid'] for r in actions)
            success = actions[-1]['outcome']['action'] == 'stop' and ds[-1] <= .3
            expected_status = 'success' if success else 'early_stop' if actions[-1]['outcome']['action'] == 'stop' else 'action_budget'
            assert s['status'] == expected_status
            assert s['success'] == success and s['collision_free_success'] == (success and collisions == 0)
            assert s['collisions'] == collisions and s['invalid_actions'] == invalid
            assert s['ever_within_goal_tolerance'] == (min([initial_d, *ds]) <= .3)
            assert abs(travel - s['path_length_m']) < 1e-4 and abs(ds[-1] - s['final_geodesic_m']) < 1e-6
            spl = initial_d / max(initial_d, travel) if success else 0.
            assert abs(spl - s['spl']) < 1e-6
            last_ref = actions[-1]['request']['state']['reference']
            row = {'route': route, 'input': mode, 'batch': batch, 'run': name,
                   **{k: s[k] for k in ['status', 'success', 'collision_free_success', 'steps', 'collisions', 'invalid_actions', 'path_length_m', 'initial_geodesic_m', 'final_geodesic_m', 'spl']},
                   'minimum_geodesic_m': min(ds), 'minimum_at_action': ds.index(min(ds)) + 1,
                   'stop_request_distance_m': last_ref['final_goal']['distance_m'] if actions[-1]['outcome']['action'] == 'stop' else None,
                   'reference_path_length_m': m['reference_path_length_m'], 'max_steps': cfg['max_steps'],
                   'model_latency_p50_s': s['model_request_latency']['p50_s'], 'model_latency_p95_s': s['model_request_latency']['p95_s'],
                   'elapsed_s': s['elapsed_s']}
            rows.append(row)
            counts = Counter(r['outcome']['action'] for r in actions)
            details[name] = {'action_counts': dict(counts), 'invalid_action_counts': dict(Counter(r['outcome']['action'] for r in actions if not r['outcome']['valid'])),
                             'geodesic_after_actions_m': ds, 'positions': [r['pose']['position'] for r in records],
                             'created_unix': m['created_unix'], 'cost_usd': sum(r['decision']['response'].get('usage', {}).get('cost', 0) for r in actions),
                             'left_turns_when_target_on_right': sum(r['outcome']['action'] == 'turn_left' and r['request']['state']['reference']['current_target']['bearing_deg'] < -1 for r in actions),
                             'last_request_reference': last_ref}
            print('VERIFIED', name, len(actions), flush=True)
        a, b = records_by_key[route, mode, '01'], records_by_key[route, mode, '02']
        projection = lambda records: [{'pose': r['pose'], 'request': r['request'], 'outcome': r['outcome'], 'after_position': r.get('after_position'), 'distance': r['metrics']['distance_to_goal_geodesic_m']} for r in records]
        identical = projection(a) == projection(b)
        ids_a = {r['decision']['response']['id'] for r in a[:-1]}
        ids_b = {r['decision']['response']['id'] for r in b[:-1]}
        assert identical and not (ids_a & ids_b)
        pairs.append({'route': route, 'input': mode, 'requests_poses_outcomes_distances_identical': identical,
                      'distinct_response_ids': not bool(ids_a & ids_b),
                      'answer_probabilities_identical': all(x['decision']['response']['answers'] == y['decision']['response']['answers'] for x, y in zip(a[:-1], b[:-1])),
                      'created_unix': [details[f'openai-decisions-{route}-rgbgs-{mode}-20261009-{batch}']['created_unix'] for batch in ['01', '02']]})
assert len(rows) == 18 and len(all_response_ids) == 3028 and len(set(all_response_ids)) == 3028
assert hashes == {k: hashlib.sha256((ROOT / k).read_bytes()).hexdigest() for k in hashes}
totals = {'runs': len(rows), 'steps': sum(r['steps'] for r in rows), 'successes': sum(r['success'] for r in rows), 'collision_free_successes': sum(r['collision_free_success'] for r in rows), 'collisions': sum(r['collisions'] for r in rows), 'invalid_actions': sum(r['invalid_actions'] for r in rows)}
aggregate = []
comparison = []
for route in ROUTES:
    for mode in MODES:
        group = [r for r in rows if r['route'] == route and r['input'] == mode]
        old = next(r for r in baseline['aggregate'] if r['route'] == route and r['input'] == mode)
        aggregate.append({'route': route, 'input': mode, 'runs': len(group), 'successes': sum(r['success'] for r in group), 'collision_free_successes': sum(r['collision_free_success'] for r in group), 'total_collisions': sum(r['collisions'] for r in group), 'total_invalid_actions': sum(r['invalid_actions'] for r in group)})
        comparison.append({'route': route, 'input': mode, 'jev_successes': old['successes'], 'jev_runs': old['runs'], 'openai_successes': sum(r['success'] for r in group), 'openai_runs': len(group)})
result = {'scope': 'Two logged OpenAI batches on three fixed tasks, three depth input conditions; offline audit only',
          'rows': rows, 'aggregate': aggregate, 'totals': totals, 'repeat_pairs': pairs, 'details': details, 'jev_comparison': comparison,
          'verification': {'actions_audited': len(all_response_ids), 'all_post_action_geodesics_recomputed': True, 'model_inputs_match_jev_initial_states_and_prompts': True,
                           'source_hashes_unchanged': True, 'source_hashes': hashes, 'api_calls': 0, 'used_gpu': False}}
(OUT / 'audit.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
for filename, data in [('runs.csv', rows), ('aggregate.csv', aggregate), ('jev-comparison.csv', comparison)]:
    with (OUT / filename).open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(data[0])); w.writeheader(); w.writerows(data)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig, axes = plt.subplots(1, 3, figsize=(15, 4), constrained_layout=True)
for ax, route in zip(axes, ROUTES):
    for mode, color in zip(MODES, ['#2563eb', '#16a34a', '#dc2626']):
        name = f'openai-decisions-{route}-rgbgs-{mode}-20261009-01'
        ds = details[name]['geodesic_after_actions_m']
        ax.plot(range(1, len(ds) + 1), ds, label=mode, color=color)
    ax.axhline(.3, color='black', ls='--', lw=.8, label='success tolerance')
    ax.set(title=route, xlabel='Executed actions', ylabel='Geodesic distance to goal (m)')
    ax.grid(alpha=.2); ax.legend(fontsize=8)
fig.savefig(OUT / 'goal-distance.png', dpi=160); plt.close(fig)

lines = ['# OpenAI Decisions 两轮导航消融审计', '',
         '来源：`runs/openai-decisions-{simple,complex,extended}-rgbgs-{numeric,semantic,none}-20261009-{01,02}`，共 18 轮真实模型记录。实际响应模型均为 `openai/gpt-6-luna-decisions-20261006`。', '',
         f"共 {totals['successes']}/18 成功（44.4%），{totals['collision_free_successes']}/18 成功且零碰撞（33.3%）；{totals['steps']} 个动作、{totals['collisions']} 次碰撞、{totals['invalid_actions']} 个无效动作。每类只有一个固定任务，百分比仅描述这批记录。", '',
         '## 逐条件指标', '',
         '每个条件两轮的请求正文、逐步动作、位姿和目标距离完全相同。因此下表用一行展示两轮相同的导航指标；CSV 保留全部 18 行。响应 ID 全部唯一（3028 个），运行创建时间及耗时不同；日志支持它们是两次独立请求过程，不能仅凭此判断服务确定性、缓存或底层采样设置。', '',
         '| 路线 | 输入 | 成功数 | 结果 | 动作数 | 碰撞 | 无效动作 | 累计路程 m | 最终距离 m | SPL |',
         '|---|---|---:|---|---:|---:|---:|---:|---:|---:|']
status = {'success': '成功', 'early_stop': '失败：提前停止', 'action_budget': '失败：预算耗尽'}
for row in rows:
    if row['batch'] != '01': continue
    lines.append(f"| {RL[row['route']]} | [{ML[row['input']]}](../../runs/{row['run']}/summary.json) | {2 if row['success'] else 0}/2 | {status[row['status']]} | {row['steps']} | {row['collisions']} | {row['invalid_actions']} | {row['path_length_m']:.3f} | {row['final_geodesic_m']:.6f} | {row['spl']:.3f} |")
lines += ['', '## 失败和效率观察', '',
          '- 简单数值：最小距离 3.227464 m（第 4 动作），之后逐渐偏离；62 次左转、2 次右转、17 次后退，末尾连续 9 次左转且无平移。第 7 动作目标 bearing=-28.80°（右侧），却左转，后续多次左转继续扩大方向偏差。说明此次跟随/恢复行为失败，不能把它全部解释为终点停止问题。',
          '- 简单语义：第 45 动作距目标 0.332596 m，尚未进入容差；第 46 动作继续前进至 0.335350 m，第 47–51 动作继续远离。初始目标在右侧，执行连续左转；整轮 25 次左转而没有右转，最终预算耗尽。',
          '- 简单无深度：停止请求中目标距离 0.463 m，真实 NavMesh 距离 0.462650 m，明确超过 0.30 m；此前有 17 次碰撞，属于容差外提前停止。',
          '- 复杂数值：86 动作、零碰撞、零无效动作。复杂语义也成功且零碰撞，但 156 动作；46 次俯仰动作及 62 次左转造成更高动作成本，9 个无效动作全部为超俯仰范围（6 次抬头、3 次低头）。语义路程略短不等于动作效率更高。',
          '- 复杂无深度：第 61 动作最接近至 0.322039 m，但未进入成功范围；终点附近反复前进/后退并受阻，累计 106 次碰撞，末尾仍在约 0.60–0.69 m 往返。',
          '- 长数值：零碰撞并基本完成跟随，但在 0.308222 m 停止，距成功阈值仅多 8.22 mm。请求明确给出 0.308 m，因此不是显示四舍五入或欧氏/路径距离不同引起的合规停止，按既定评估应记失败。',
          '- 长语义：351 动作成功且零碰撞，累计路程 19.750 m，接近 19.613 m 的参考路径；228 次左转、43 次俯仰动作，运动路径较短但动作/时间成本高。',
          '- 长无深度：202 动作成功，但 7 次碰撞，路程 28.071 m，SPL 0.581，低于长语义的 0.826。不能把较少动作直接等同于避障能力更好。', '',
          '以上左转倾向是日志观察，尚不能区分模型方向理解、提示词/候选顺序偏好、深度条件或服务设置的因果作用；没有据此修改策略。所有失败均未曾进入 0.30 m 成功范围。', '',
          '![距离随动作变化](goal-distance.png)', '', '## 与此前 Jev 相同任务比较', '',
          '同一七动作 v5 提示词、参考路径、起终点及初始姿态，共同配置一致，仅模型/输入模式/渲染 GPU 等实验字段不同。逐模式的初始请求正文去掉 model 后核查相同。Jev 历史组包含可比失败记录，复杂数值有 3 次，其余 2 次；历史运行时间不同，且部分回放使用 mesh RGB，RGB 均不发给模型。', '',
          '| 路线 | 输入 | Jev 成功/运行 | OpenAI 成功/运行 |', '|---|---|---:|---:|']
for c in comparison:
    lines.append(f"| {RL[c['route']]} | {ML[c['input']]} | {c['jev_successes']}/{c['jev_runs']} | {c['openai_successes']}/{c['openai_runs']} |")
lines += ['', 'OpenAI 在这两个有深度的复杂任务条件、长路线语义条件上完成得更好；简单路线明显退步。长数值的失败主要落在停止边界，不能简单说整体跟随能力差。无深度长路线虽成功，仍不能声称具备可靠避障。单个任务和两次完全相同轨迹不支持一般性能排名。', '',
          '## 请求延迟（秒）', '', '| 路线 | 输入 | 第一轮 P50/P95 | 第二轮 P50/P95 |', '|---|---|---:|---:|']
for route in ROUTES:
    for mode in MODES:
        a, b = [r for r in rows if r['route'] == route and r['input'] == mode]
        lines.append(f"| {RL[route]} | {ML[mode]} | {a['model_latency_p50_s']:.3f}/{a['model_latency_p95_s']:.3f} | {b['model_latency_p50_s']:.3f}/{b['model_latency_p95_s']:.3f} |")
lines += ['', '第二轮 P50 普遍约 1.44–1.50 s，第一轮约 1.31–1.38 s；导航相同但 API 端到端延迟不同。这里不是纯模型计算耗时，也不能由此推断整个闭环实时能力。', '',
          '## 实验与核查边界', '',
          '- 简单/复杂/长路线最短距离约 4.196/9.798/16.323 m，参考长度 4.196/11.711/19.613 m；动作预算 100/250/500。成功需模型输出 stop 且 NavMesh 距离 ≤0.30 m。保留原阈值，不将近成功改记成功。',
          '- 有深度条件使用 mesh 深度，GS RGB 仅供回放；无深度仍有参考路线、目标、本体状态、最近自身动作反馈，属于当前策略的深度输入消融。',
          '- 碰撞是 Habitat NavMesh 移动过滤 collided；无效动作含超俯仰限制。累计路程包括往返，不计原地旋转/观察。SPL 使用原最短距离而非安全余量参考路径长度。',
          '- 已重算全部 3028 个动作的 NavMesh 距离、累计路程、碰撞/无效计数、停止成功条件和 SPL；核查三种实际输入、模型身份、步序、位姿连续性、逐条件与 Jev 的初始输入及提示词一致性。原始文件哈希保持不变。没有重新渲染、调用 API、修改导航代码或重跑实验。',
          '- [18 轮完整 CSV](runs.csv)、[聚合 CSV](aggregate.csv)、[Jev 对照 CSV](jev-comparison.csv)、[结构化审计及源哈希](audit.json)、[复核脚本](audit.py)。']
(OUT / 'README.md').write_text('\n'.join(lines) + '\n')
print('PASS', json.dumps(totals), 'protected files', len(hashes), flush=True)
