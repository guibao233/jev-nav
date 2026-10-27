"""Audit saved local OneJev runs on CPU; no API, renderer, or source mutation."""
from pathlib import Path
from collections import Counter
import base64, copy, csv, hashlib, io, json, math, sys
import numpy as np
from PIL import Image

ROOT = Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav')
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
from environment import load_pathfinder, shortest
from depth_language import semantic_depth
from rgb_input import project_target

ROUTES = ['simple', 'complex', 'extended']
MODES = ['numeric', 'semantic', 'none']
TASKS = dict(zip(ROUTES, ['tasks/debug-10.json', 'tasks/challenge-clearance-aligned-20260930-01/tasks.json', 'tasks/extended-clearance-aligned-20261008-01/tasks.json']))
IDS = dict(zip(ROUTES, ['episode-000', 'turn-000', 'extended-000']))
BUDGETS = dict(zip(ROUTES, [100, 250, 500]))
hashes, details, sequences, rows = {}, {}, {}, []
pf = None
def protect(path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    hashes[str(path.relative_to(ROOT))] = digest
    return digest
def near(a, b, tol=1e-6):
    assert abs(a-b) <= tol, (a, b)
def longest(values, predicate):
    best = cur = 0
    for value in values:
        cur = cur + 1 if predicate(value) else 0
        best = max(best, cur)
    return best

for p in ['environment.py', 'depth_language.py', 'rgb_input.py', 'onejev.py', 'run.py', 'local_models/onejev-4b/source/qev/mm_engine.py', 'local_models/onejev-4b/source/qev/answers.py']:
    protect(ROOT/p)
base_tasks = {}
for route, p in TASKS.items():
    protect(ROOT/p)
    base_tasks[route] = next(t for t in json.loads((ROOT/p).read_text())['tasks'] if t['id'] == IDS[route])

for route in ROUTES:
 for mode in MODES:
  for batch in ['01', '02']:
    name = f'onejev-local-rgbtarget-{route}-rgbgs-{mode}-local-round-{batch}'
    folder = ROOT/'runs'/name
    for filename in ['metadata.json', 'summary.json', 'steps.jsonl']:
        protect(folder/filename)
    m = json.loads((folder/'metadata.json').read_text())
    s = json.loads((folder/'summary.json').read_text())
    records = [json.loads(line) for line in (folder/'steps.jsonl').read_text().splitlines()]
    cfg, task = m['config'], m['task']
    assert m['provider'] == s['provider'] == 'onejev_local'
    assert s['requested_model'] == 'OmniJev/OneJev-4B'
    assert s['response_models'] == ['OmniJev/OneJev-4B'] and s['is_onejev_evaluation']
    assert m['api_endpoint'] == 'http://127.0.0.1:8011/v1/systemone'
    assert m['onejev_service_health'] == {'status':'ok','model':'OmniJev/OneJev-4B','fork_mode':'batched','prompt_version':'qev-labels-v2'}
    assert m['rgb_mode'] == 'gs' and cfg['rgb_input'] == m['rgb_input'] == s['rgb_input'] == 'target_marked'
    assert m['rgb_provided_to_model'] and s['rgb_provided_to_model']
    assert m['depth_provided_to_model'] == s['depth_provided_to_model'] == (mode != 'none')
    assert cfg['max_steps'] == BUDGETS[route] and cfg['success_m'] == .3
    assert all(task[k] == base_tasks[route][k] for k in ['start','goal','path','yaw_deg','pitch_deg'])
    if pf is None:
        pf = load_pathfinder(dict(cfg))
    assert hashlib.sha256((Path(cfg['scene_dir'])/'shuyuan.navmesh').read_bytes()).hexdigest() == m['assets']['shuyuan.navmesh']['sha256']
    assert records[-1]['frame_kind'] == 'after_final_action' and records[-1]['request'] is None
    actions = records[:-1]
    assert len(actions) == s['steps'] and [r['step'] for r in records] == list(range(len(records)))
    near(math.dist(actions[0]['pose']['position'], task['start']), 0)
    initial = shortest(pf, task['start'], task['goal'])[0]
    near(initial, s['initial_geodesic_m'])
    travel = 0.
    distances, latencies, cycles, counts, markers, projections = [], [], [], Counter(), Counter(), Counter()
    image_tokens, attempts, behind_forward = [], [], []
    sequence = {k:[] for k in ['actions','poses','image_sha256','wire_sha256','prompt_sha256','probabilities']}
    for i, r in enumerate(actions):
        req, dec, outcome = r['request'], r['decision'], r['outcome']
        state, response = req['state'], dec['response']
        assert req['model'] == response['model'] == 'OmniJev/OneJev-4B'
        assert dec['choice'] == response['answers']['action']['choice'] == outcome['action']
        assert list(req['questions']['action']['criteria']) == m['available_actions']
        assert math.dist(r['after_position'], records[i+1]['pose']['position']) < 1e-6
        travel += math.dist(r['pose']['position'], r['after_position'])
        near(travel, r['metrics']['path_length_m'], 1e-4)
        distance = shortest(pf, r['after_position'], task['goal'])[0]
        near(distance, r['metrics']['distance_to_goal_geodesic_m'])
        distances.append(distance)
        if mode == 'none':
            assert 'depth' not in state and 'depth_numeric_debug' not in r
        elif mode == 'semantic':
            assert semantic_depth(r['depth_numeric_debug']) == state['depth']
        else:
            assert len(state['depth']['sectors']) == 9
        im = r['image_input']
        b = (folder/im['path']).read_bytes()
        digest = protect(folder/im['path'])
        assert digest == im['sha256'] and len(b) == im['bytes']
        assert im['mime_type'] == 'image/jpeg' and r['images']['model_rgb'] == im['path']
        with Image.open(io.BytesIO(b)) as image:
            assert image.format == 'JPEG' and image.size == (640,480) == (im['width'],im['height'])
            image.verify()
        assert state['visual']['source'] == 'current_gs_rgb' and state['visual']['marker'] == im['marker']
        projection = project_target(state['reference']['current_target'], r['pose']['pitch_deg'], cfg, im['marker']['target_height_above_agent_feet_m'])
        assert all(projection[k] == im['marker'][k] for k in projection)
        wire = copy.deepcopy(req)
        wire['state']['visual']['image'] = '<image:1>'
        wire['media'] = [{'type':'image','data':'data:image/jpeg;base64,'+base64.b64encode(b).decode('ascii')}]
        wire_digest = hashlib.sha256(json.dumps(wire, allow_nan=False).encode()).hexdigest()
        assert wire_digest == r['wire_request_sha256'] == dec['request_body_sha256']
        qev = response['qev']
        assert qev['media']['images'] == 1 and qev['media']['videos'] == 0
        assert qev['prompt_version'] == 'qev-labels-v2' and qev['fork_mode'] == 'batched'
        counts[outcome['action']] += 1
        markers[im['marker']['marker_kind']] += 1
        projections[im['marker']['projection_status']] += 1
        latencies.append(dec['latency_s']); cycles.append(r['metrics']['cycle_s'])
        image_tokens.append(response['usage']['input_tokens']); attempts.append(dec['attempts'])
        if outcome['action'] == 'move_forward' and abs(state['reference']['current_target']['bearing_deg']) > 90:
            behind_forward.append(i+1)
        for k, value in [('actions',outcome['action']),('poses',[r['pose'],r['after_position']]),('image_sha256',digest),('wire_sha256',wire_digest),('prompt_sha256',qev['prompt_sha256']),('probabilities',response['answers']['action']['probabilities'])]:
            sequence[k].append(value)
    collisions = sum(r['outcome']['collided'] for r in actions)
    invalid = sum(not r['outcome']['valid'] for r in actions)
    success = actions[-1]['outcome']['action'] == 'stop' and distances[-1] <= .3
    assert s['success'] == success and s['status'] == ('success' if success else 'early_stop' if counts['stop'] else 'action_budget')
    assert s['collisions'] == collisions and s['invalid_actions'] == invalid
    assert s['ever_within_goal_tolerance'] == (min(initial,*distances) <= .3)
    near(travel,s['path_length_m'],1e-4); near(distances[-1],s['final_geodesic_m'])
    for key, percentile in [('p50_s',50),('p95_s',95)]:
        near(float(np.percentile(latencies,percentile)),s['model_request_latency'][key])
        near(float(np.percentile(cycles,percentile)),s['cycle_including_render_and_logging'][key])
    row = dict(run=name,route=route,depth_mode=mode,round=batch,success=success,status=s['status'],steps=len(actions),collisions=collisions,invalid_actions=invalid,path_length_m=travel,initial_geodesic_m=initial,final_geodesic_m=distances[-1],minimum_geodesic_m=min(initial,*distances),ever_within_goal_tolerance=s['ever_within_goal_tolerance'],rgb_input='target_marked',verified_multimodal_requests=len(actions),request_latency_p50_s=s['model_request_latency']['p50_s'],request_latency_p95_s=s['model_request_latency']['p95_s'])
    rows.append(row); sequences[name] = sequence
    details[name] = dict(action_counts=dict(counts),marker_counts=dict(markers),projection_counts=dict(projections),max_consecutive_left=longest(actions,lambda r:r['outcome']['action']=='turn_left'),max_stationary_actions=longest(actions,lambda r:math.dist(r['pose']['position'],r['after_position'])<1e-4),forward_with_target_behind_steps=behind_forward,input_tokens_min=min(image_tokens),input_tokens_max=max(image_tokens),total_attempts=sum(attempts),service_health=m['onejev_service_health'],deployment_sha256=m['onejev_deployment']['sha256'],config=cfg,reference_path_length_m=m['reference_path_length_m'])
    print(name,'verified',len(actions),'requests',flush=True)

pairs = {}
for route in ROUTES:
 for mode in MODES:
    prefix = f'onejev-local-rgbtarget-{route}-rgbgs-{mode}-local-round-'
    a, b = sequences[prefix+'01'], sequences[prefix+'02']
    pairs[f'{route}/{mode}'] = {k:a[k]==b[k] for k in a}
aggregates = []
for route in ROUTES:
 for mode in MODES:
    selected = [r for r in rows if r['route']==route and r['depth_mode']==mode]
    entry = dict(route=route,depth_mode=mode,runs=2,successes=sum(r['success'] for r in selected),success_rate=sum(r['success'] for r in selected)/2)
    for k in ['steps','collisions','invalid_actions','path_length_m','initial_geodesic_m','final_geodesic_m','minimum_geodesic_m']:
        entry[k+'_mean'] = sum(r[k] for r in selected)/2
        entry[k+'_min'] = min(r[k] for r in selected)
        entry[k+'_max'] = max(r[k] for r in selected)
    aggregates.append(entry)
for filename, data in [('runs.csv',rows),('aggregate.csv',aggregates)]:
    with (OUT/filename).open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
audit = dict(scope='18 saved OneJev local RGB+text runs; CPU-only read-only audit',verified_runs=len(rows),verified_multimodal_requests=sum(r['verified_multimodal_requests'] for r in rows),successes=sum(r['success'] for r in rows),round_pair_identity=pairs,details=details,source_hashes=hashes,checks=['fixed task inputs and action budgets','saved JPEG bytes SHA256, format and resolution','independent reconstructed wire SHA256 matches recorder and client','service media.images=1 on every successful response','depth mode presence/transformation','NavMesh shortest distances recomputed on CPU','pose continuity and cumulative travel recomputed','outcome collision/invalid counts and stop success recomputed','latency percentiles recomputed','all source files rehashed after audit'])
for relative,digest in hashes.items():
    assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==digest,relative
(OUT/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(dict(verified_runs=audit['verified_runs'],verified_multimodal_requests=audit['verified_multimodal_requests'],successes=audit['successes'],pair_identity=pairs,aggregate=aggregates),ensure_ascii=False,indent=2))
