import sys,json,hashlib,math,collections
from pathlib import Path
import numpy as np
root=Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav');sys.path.insert(0,str(root))
from core import depth_facts,RoutePreview
from environment import load_pathfinder,shortest
p=root/'runs/jev-first-5steps-03'
meta=json.loads((p/'metadata.json').read_text());cfg=meta['config'].copy()
rows=[json.loads(s) for s in (p/'steps.jsonl').read_text().splitlines()];actions=[r for r in rows if r.get('outcome')]
summary=json.loads((p/'summary.json').read_text());pf=load_pathfinder(cfg);route=RoutePreview(meta['task']['path'])
hashes={str(q.relative_to(root)):hashlib.sha256(q.read_bytes()).hexdigest() for q in [p/'metadata.json',p/'steps.jsonl',p/'summary.json',root/'config.json',root/'tasks/debug-10.json',root/'tasks/eval-50.json']}
nav=Path(cfg['scene_dir'])/'shuyuan.navmesh';assert hashlib.sha256(nav.read_bytes()).hexdigest()==meta['assets']['shuyuan.navmesh']['sha256']
travel=0.;history=[];errors=[];first_reached=None
for n,r in enumerate(actions):
 state=r['request']['state'];o=r['outcome'];d=r['decision'];before=np.array(r['pose']['position']);after=np.array(r['after_position'])
 assert r['step']==n and state['task']['step']==n+1
 assert d['choice']==o['action']==d['response']['answers']['action']['choice']
 assert state['recent_actions']==history[-cfg['history_steps']:]
 assert state['reference']==route.state(before,r['pose']['yaw_rad'],cfg)
 raw=p/Path(r['images']['depth']).with_suffix('.npz')
 with np.load(raw) as data: assert depth_facts(data['depth_m'],r['pose']['pitch_deg'],cfg)==state['depth']
 assert np.allclose(rows[n+1]['pose']['position'],after,atol=1e-6)
 check=shortest(pf,after,meta['task']['goal']);assert check is not None
 errors.append(abs(check[0]-r['metrics']['distance_to_goal_geodesic_m']))
 assert errors[-1]<1e-6
 travel+=float(np.linalg.norm(after-before));assert abs(travel-r['metrics']['path_length_m'])<1e-6
 if first_reached is None and check[0]<=cfg['success_m']: first_reached=n+1
 history.append(o)
assert rows[-1]['request'] is None and len(rows)==len(actions)+1
assert summary['steps']==len(actions) and summary['collisions']==sum(r['outcome']['collided'] for r in actions)
assert summary['invalid_actions']==sum(not r['outcome']['valid'] for r in actions)
assert actions[-1]['outcome']['action']=='stop' and summary['status']=='success'
assert actions[-1]['metrics']['distance_to_goal_geodesic_m']<=cfg['success_m']
initial=shortest(pf,meta['task']['start'],meta['task']['goal'])[0]
assert abs(initial-summary['initial_geodesic_m'])<1e-6 and abs(travel-summary['path_length_m'])<1e-6
spl=initial/max(initial,travel);assert abs(spl-summary['spl'])<1e-6
result={'source_run':str(p),'source_sha256':hashes,'checks_passed':['NavMesh SHA256','all 36 stored raw depths reproduce input depth facts exactly','all 36 reference inputs reproduce from fixed initial path','all 36 choices equal API answer and executed action','all 36 histories contain only previous own local outcomes','all 36 after poses match next observations','all 36 geodesic distances independently recalculated','travel, SPL, collision and invalid counts independently recalculated','explicit final stop within tolerance'],
 'summary':summary,'max_steps':cfg['max_steps'],'reference_vertices':len(meta['task']['path']),'reference_has_bends':len(meta['task']['path'])>2,'action_counts':dict(collections.Counter(r['outcome']['action'] for r in actions)),
 'invalid_steps_1based':[r['step']+1 for r in actions if not r['outcome']['valid']],
 'first_within_goal_tolerance_step_1based':first_reached,'extra_decisions_after_first_reach':len(actions)-first_reached,
 'max_local_reference_distance_m':max(r['request']['state']['reference']['distance_from_local_reference_m'] for r in actions),
 'forward_depth_status_counts':dict(collections.Counter(r['request']['state']['depth']['move_checks']['move_forward']['status'] for r in actions)),
 'moving_with_forward_depth_status':dict(collections.Counter(r['request']['state']['depth']['move_checks']['move_forward']['status'] for r in actions if r['outcome']['action']=='move_forward')),
 'actual_models':sorted(set(r['decision']['response']['model'] for r in actions)),
 'api_attempts':sum(r['decision']['attempts'] for r in actions),'logged_usage_cost_usd':sum(r['decision']['response']['usage']['cost'] for r in actions),
 'decision_cycle_sum_s':sum(r['metrics']['cycle_s'] for r in actions),
 'max_distance_check_error_m':max(errors)}
Path('/tmp/jev-nav-challenge/audit.json').write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'},indent=2))
