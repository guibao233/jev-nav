"""CPU-only saved-trajectory regression; not a new policy rollout."""
from pathlib import Path
import ast, copy, csv, hashlib, json, math, sys
import numpy as np
report=Path(__file__).resolve().parent
root=report.parent.parent
sys.path.insert(0,str(root))
from core import RoutePreview,recent_motion_summary
from environment import load_pathfinder,direct_navmesh_connection,shortest
from jev import make_request,PROMPT_VERSION
old_core={};exec(compile((report/'before/core.py').read_text(),'before/core.py','exec'),old_core)
old_jev={};exec(compile((report/'before/jev.py').read_text(),'before/jev.py','exec'),old_jev)
run=root/'runs/jev-challenge-turn-000-neutral-02'
meta=json.loads((run/'metadata.json').read_text());cfg=meta['config'];pf=load_pathfinder(dict(cfg))
a=[r for line in (run/'steps.jsonl').open() if (r:=json.loads(line)).get('request')]
checks=[]
def connection(start,end):
    valid=direct_navmesh_connection(pf,start,end)
    checks.append({'start':np.asarray(start).tolist(),'end':np.asarray(end).tolist(),'connected':valid})
    return valid
route=RoutePreview(meta['task']['path'],reconnect=connection)
events=[];new_states=[];motion_errors=[];samples=[]
for i,r in enumerate(a):
    state=copy.deepcopy(r['request']['state'])
    state['reference']=route.state(r['pose']['position'],r['pose']['yaw_rad'],cfg)
    state['recent_motion']=recent_motion_summary(state['recent_actions'],cfg['history_steps'],cfg['move_m'])
    new_states.append(state)
    if state['reference']['tracking']['mode']=='reassociated':
        events.append({'step':i+1,'tracking':state['reference']['tracking'],'local_distance_m':state['reference']['distance_from_local_reference_m']})
    old_request=old_jev['make_request'](state,cfg);new_request=make_request(state,cfg)
    assert new_request['questions']['action']['criteria']==old_request['questions']['action']['criteria']
    prefix='Choose one next action'
    assert new_request['questions']['action']['instructions'].split(prefix)[0]==old_request['questions']['action']['instructions'].split(prefix)[0]
    for key in ('depth','robot','recent_actions','task'):
        assert new_request['state'][key]==r['request']['state'][key]
    h=state['recent_actions'];count=len(h)
    actual=float(np.linalg.norm(np.array(r['pose']['position'])-a[i-count]['pose']['position']))
    motion_errors.append(abs(actual-state['recent_motion']['net_translation_m']))
    assert motion_errors[-1]<.004
    samples.append({'step':i+1,'old_remaining_m':r['request']['state']['reference']['remaining_reference_length_m'],
       'new_remaining_m':state['reference']['remaining_reference_length_m'], 'new_tracking_mode':state['reference']['tracking']['mode'],
       'new_progress_m':state['reference']['tracking']['progress_m'],'motion_status':state['recent_motion']['status'],
       'net_translation_m':state['recent_motion']['net_translation_m'],'opposite_turn_pairs':state['recent_motion']['opposite_turn_pairs']})
    if i+1 in (82,150):
        (report/f'request-step-{i+1:03d}.json').write_text(json.dumps(new_request,indent=2)+'\n')
assert all(samples[i]['new_progress_m']<=samples[i+1]['new_progress_m'] for i in range(len(samples)-1))
assert route.progress>4.7
assert new_states[149]['recent_motion']['status']=='turn_oscillation'
assert new_states[149]['recent_motion']['opposite_turn_pairs']==4
assert new_states[149]['reference']['current_target']['left_m']<0
assert a[149]['request']['state']['reference']['current_target']['left_m']>0
with (report/'saved-trajectory.csv').open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(samples[0]));writer.writeheader();writer.writerows(samples)
# Staying on the original routes must retain the original waypoint behavior.
ideal_states=0
challenge=json.loads((root/'tasks/challenge-v1-20260928/tasks.json').read_text())
for task in challenge['tasks']:
    old=old_core['RoutePreview'](task['path'])
    fresh=RoutePreview(task['path'],reconnect=connection)
    for arc in np.r_[np.arange(0,fresh.total,.1),fresh.total]:
        position=fresh.at(arc)
        expected=old.state(position,0,cfg)
        actual=fresh.state(position,0,cfg)
        tracking=actual.pop('tracking')
        assert actual==expected
        assert tracking['mode']=='local'
        ideal_states+=1
# A real NavMesh corner can have reachable endpoints but a forbidden straight connector.
blocked_corner=None
shape=RoutePreview(meta['task']['path'])
for corner in shape.arcs[1:-1]:
    for distance in (.1,.2,.3,.4,.5,.7):
        start=shape.at(max(0,corner-distance));end=shape.at(min(shape.total,corner+distance))
        separation=float(np.linalg.norm(start-end))
        if separation>.5:continue
        path=shortest(pf,start,end)
        if path and path[0]>separation+.01 and not direct_navmesh_connection(pf,start,end):
            blocked_corner={'start':start.tolist(),'end':end.tolist(),'straight_distance_m':separation,'geodesic_m':path[0]}
            break
    if blocked_corner:break
assert blocked_corner is not None,'Expected an obstructed real NavMesh corner for the negative control'
def definition(text,name):
    return ast.dump(next(n for n in ast.parse(text).body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name==name))
for file,names in [('core.py',['depth_points','_sweep_mask','_sweep_visibility','depth_facts']),('environment.py',['Environment']),('jev.py',['JevClient','ServiceFailure'])]:
    old=(report/'before'/file).read_text();new=(root/file).read_text()
    for name in names: assert definition(old,name)==definition(new,name)
protected=json.loads((report/'protected-before.json').read_text())
assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==h for p,h in protected.items())
result={'prompt_version':PROMPT_VERSION,'saved_states_checked':len(a),'reassociation_events':events,
 'final_old_remaining_m':a[-1]['request']['state']['reference']['remaining_reference_length_m'],
 'final_new_remaining_m':new_states[-1]['reference']['remaining_reference_length_m'],
 'final_new_progress_m':route.progress,'first_motion_oscillation_step':next(s['step'] for s in samples if s['motion_status']=='turn_oscillation'),
 'step_150_recent_motion':new_states[149]['recent_motion'],
 'max_net_motion_error_vs_world_poses_m':max(motion_errors),'normal_route_states_unchanged':ideal_states,
 'challenge_routes_checked':len(challenge['tasks']),'real_navmesh_rejected_shortcut':blocked_corner,
 'criteria_stop_rule_depth_actions_api_unchanged':True,'protected_files_unchanged':len(protected),
 'api_calls':0,'gpu_runs':0,'evidence_limit':'Saved original poses/actions only; no new Jev behavior inferred'}
(report/'offline-verification.json').write_text(json.dumps(result,indent=2)+'\n')
(report/'connector-checks.json').write_text(json.dumps(checks,indent=2)+'\n')
print(json.dumps(result,indent=2))
