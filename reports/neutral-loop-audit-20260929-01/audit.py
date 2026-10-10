"""Read-only CPU audit of a saved Jev run; outputs only into this report."""
from pathlib import Path
from collections import Counter
import csv
import hashlib
import json
import math
import sys
import numpy as np

report=Path(__file__).resolve().parent
root=report.parent.parent
sys.path.insert(0,str(root))
from core import RoutePreview, depth_facts
from environment import load_pathfinder, shortest
from jev import make_request
run=root/'runs/jev-challenge-turn-000-neutral-02'
meta=json.loads((run/'metadata.json').read_text())
summary=json.loads((run/'summary.json').read_text())
rows=[json.loads(l) for l in (run/'steps.jsonl').open()]
a=[r for r in rows if r.get('outcome')]
cfg=meta['config']
protected=[*root.glob('*.py'),*root.glob('config*.json'),*(run/x for x in ('metadata.json','steps.jsonl','summary.json','index.html'))]
before={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
route=RoutePreview(meta['task']['path'])
progress=[]; targets=[]; nearest=[]
for r in a:
    assert make_request(r['request']['state'],cfg)==r['request']
    assert route.state(r['pose']['position'],r['pose']['yaw_rad'],cfg)==r['request']['state']['reference']
    progress.append(route.progress)
    t=min(route.total,route.progress+cfg['target_lookahead_m'])
    corners=[float(s) for s in route.arcs[1:-1] if s>route.progress+.12]
    if corners: t=min(t,corners[0])
    targets.append(route.at(t))
    pos=np.asarray(r['pose']['position'])
    candidates=[]
    for i,length in enumerate(route.lengths):
        v=route.points[i+1]-route.points[i]
        fraction=float(np.clip(np.dot(pos-route.points[i],v)/np.dot(v,v),0,1))
        q=route.points[i]+fraction*v
        candidates.append((float(np.linalg.norm(pos-q)),float(route.arcs[i]+fraction*length),q.tolist()))
    nearest.append(min(candidates))
last_move=max(i for i,r in enumerate(a) if np.linalg.norm(np.array(r['after_position'])-r['pose']['position'])>1e-6)
static=a[last_move+1:]
p=np.asarray(static[0]['pose']['position'])
assert all(np.array_equal(r['pose']['position'],p) and np.array_equal(r['after_position'],p) for r in static)
turns={'turn_left','turn_right'}
turn_switches=sum(a[i-1]['outcome']['action'] in turns and a[i]['outcome']['action'] in turns and a[i-1]['outcome']['action']!=a[i]['outcome']['action'] for i in range(last_move+2,len(a)))
spans=[];start=None
for i,r in enumerate(a):
    action=r['outcome']['action']
    good=action in turns and (start is None or action != a[i-1]['outcome']['action'])
    if not good and start is not None:
        spans.append((start+1,i,i-start)); start=None
    if action in turns and start is None:start=i
if start is not None:spans.append((start+1,len(a),len(a)-start))
longest=max(spans,key=lambda x:x[2])
freeze_start=len(progress)-1
while freeze_start>0 and abs(progress[freeze_start-1]-progress[-1])<1e-12:freeze_start-=1
pf=load_pathfinder(dict(cfg))
probes=[]
for yaw_deg in sorted({round(math.degrees(r['pose']['yaw_rad']),5) for r in static}):
    yaw=math.radians(yaw_deg);direction=np.array([-math.sin(yaw),0,-math.cos(yaw)])
    for name,sign in [('move_forward',1),('move_backward',-1)]:
        desired=p+sign*cfg['move_m']*direction
        end=np.asarray(pf.try_step(p,desired))
        probes.append({'yaw_deg':yaw_deg,'action':name,'requested_m':cfg['move_m'],'actual_m':float(np.linalg.norm(end-p)),
            'endpoint_error_m':float(np.linalg.norm(end-desired)),'end_navigable':bool(pf.is_navigable(end)),
            'geodesic_to_goal_m':shortest(pf,end,meta['task']['goal'])[0]})
for step in [85,86,150,151]:
    r=a[step-1]
    with np.load(run/'frames'/f'{step-1:05d}-depth.npz') as frame:
        assert depth_facts(frame['depth_m'],r['pose']['pitch_deg'],cfg)==r['request']['state']['depth']
answer=lambda r:r['decision']['response']['answers']['action']
back_probs=[answer(r)['probabilities']['move_backward'] for r in static]
conf=[answer(r)['confidence'] for r in static]
result={
 'run':str(run.relative_to(root)), 'step_numbering':'one-based; steps.jsonl step + 1',
 'summary':summary,'prompt_version':meta['prompt_version'],'actual_models':sorted({r['decision']['response']['model'] for r in a}),
 'action_counts':dict(Counter(r['outcome']['action'] for r in a)),
 'events':[{'step':r['step']+1,'outcome':r['outcome']} for r in a if r['outcome']['collided'] or not r['outcome']['valid']],
 'last_translation_step':last_move+1,'stationary_start_step':last_move+2,'stationary_end_step':len(a),'stationary_steps':len(static),
 'stationary_position':p.tolist(),'stationary_action_counts':dict(Counter(r['outcome']['action'] for r in static)),
 'adjacent_opposite_turn_pairs_in_stationary_tail':turn_switches,'longest_strict_alternating_turn_span':{'start':longest[0],'end':longest[1],'steps':longest[2]},
 'stationary_yaw_counts_deg':dict(Counter(round(math.degrees(r['pose']['yaw_rad']),2) for r in static)),
 'stationary_forward_status_counts':dict(Counter(r['request']['state']['depth']['move_checks']['move_forward']['status'] for r in static)),
 'stationary_backward_status_counts':dict(Counter(r['request']['state']['depth']['move_checks']['move_backward']['status'] for r in static)),
 'stationary_backward_probability_min_median_max':list(map(float,[min(back_probs),np.median(back_probs),max(back_probs)])),
 'stationary_confidence_min_median_max':list(map(float,[min(conf),np.median(conf),max(conf)])),
 'route_progress_final_m':route.progress,'route_progress_frozen_from_step':freeze_start+1,
 'final_logged_local_reference_distance_m':a[-1]['request']['state']['reference']['distance_from_local_reference_m'],
 'nearest_whole_path_distance_m':nearest[-1][0],'nearest_whole_path_arc_m':nearest[-1][1],'nearest_whole_path_world':nearest[-1][2],
 'current_target_world':targets[-1].tolist(),'current_target_distance_m':float(np.linalg.norm(targets[-1]-p)),
 'navmesh_position_navigable':bool(pf.is_navigable(p)),
 'navmesh_boundary_clearance_m':float(pf.distance_to_closest_obstacle(p,2)),
 'nearest_path_connector':shortest(pf,p,nearest[-1][2]), 'current_target_connector':shortest(pf,p,targets[-1]),
 'cpu_navmesh_probes':probes,'probe_limit':'NavMesh movement filtering only; no new mesh rendering, model calls or full recovery rollout',
 'saved_request_and_route_exact_matches':len(a),'depth_facts_exact_matches_steps':[85,86,150,151],
 'retrying_requests':sum(r['decision']['attempts']>1 for r in a),'api_calls_in_audit':0,'gpu_runs_in_audit':0,
}
with (report/'timeline.csv').open('w',newline='') as f:
    writer=csv.writer(f)
    writer.writerow(['step','action','translation_m','collided','valid','yaw_deg','pitch_deg','goal_geodesic_after_m','tracked_arc_before_m','nearest_whole_path_arc_before_m','nearest_whole_path_distance_before_m','logged_local_distance_m','target_distance_m','target_bearing_deg','forward_status','backward_status','confidence','backward_probability'])
    for i,r in enumerate(a):
        s=r['request']['state'];ref=s['reference'];o=r['outcome']
        writer.writerow([i+1,o['action'],o['actual_translation_m'],o['collided'],o['valid'],math.degrees(r['pose']['yaw_rad']),r['pose']['pitch_deg'],r['metrics']['distance_to_goal_geodesic_m'],progress[i],nearest[i][1],nearest[i][0],ref['distance_from_local_reference_m'],ref['current_target']['distance_m'],ref['current_target']['bearing_deg'],s['depth']['move_checks']['move_forward']['status'],s['depth']['move_checks']['move_backward']['status'],answer(r)['confidence'],answer(r)['probabilities']['move_backward']])
# A scientific plot from recorded quantities; saved observations are never modified.
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig,axes=plt.subplots(3,1,figsize=(12,8.5),sharex=True,constrained_layout=True)
x=np.arange(1,len(a)+1)
axes[0].plot(x,[r['metrics']['distance_to_goal_geodesic_m'] for r in a],label='Geodesic to goal (after action)')
axes[0].plot(x,progress,label='Tracked path arc (before action)')
axes[0].plot(x,[n[1] for n in nearest],label='Nearest full-path arc (audit only)',alpha=.8)
axes[0].set_ylabel('Metres');axes[0].legend(loc='upper right',fontsize=8)
axes[1].plot(x,[math.degrees(r['pose']['yaw_rad']) for r in a],lw=1,label='Body yaw before action')
axes[1].set_ylabel('Yaw (degrees)');axes[1].set_ylim(-190,190)
axes[1].legend(fontsize=8)
labels=['move_backward','move_forward','turn_left','turn_right','look_down']
colors=['#4878d0','#ee854a','#6acc64','#d65f5f','#956cb4']
for j,name in enumerate(labels):
    selected=[i+1 for i,r in enumerate(a) if r['outcome']['action']==name]
    axes[2].scatter(selected,[j]*len(selected),s=14,color=colors[j])
axes[2].set_yticks(range(len(labels)),labels)
axes[2].set_xlabel('Decision step (1-based)')
for ax in axes:
    ax.axvspan(85.5,250.5,color='#f2c14e',alpha=.16)
    ax.axvline(62,color='gray',ls='--',lw=.8)
    ax.grid(alpha=.2)
axes[0].set_title('Neutral-02 audit: path progress freezes at step 62; no translation after step 85')
fig.savefig(report/'timeline.png',dpi=150);plt.close(fig)
# Detailed local geometry view, world +X right and +Z down.
fig,ax=plt.subplots(figsize=(8,8),constrained_layout=True)
from PIL import Image
m=meta['map'];image=np.array(Image.open(run/'navmap.png'))
ax.imshow(image,extent=[m['origin_x'],m['origin_x']+image.shape[1]*m['resolution_m'],m['origin_z']+image.shape[0]*m['resolution_m'],m['origin_z']],alpha=.65)
path=route.points
ax.plot(path[:,0],path[:,2],color='#2974ee',lw=2,label='Initial reference path')
pos=np.array([r['pose']['position'] for r in a[:86]])
ax.plot(pos[:,0],pos[:,2],color='#ef9024',lw=1.7,label='Executed trajectory through step 85')
for point,label,color,marker in [(p,'Stationary robot','#111111','X'),(targets[-1],'Current target (stale)','#d81b97','D'),(np.array(nearest[-1][2]),'Nearest full-path point','#00acb8','o')]:
    ax.scatter(point[0],point[2],c=color,marker=marker,s=80,label=label,zorder=5)
for yaw_deg in [82.70431,97.70431,112.70431,127.70431]:
    yaw=math.radians(yaw_deg)
    ax.arrow(p[0],p[2],-.35*math.sin(yaw),-.35*math.cos(yaw),width=.007,head_width=.035,color='#cc3333',alpha=.65)
ax.set_xlim(-8.6,-6.55);ax.set_ylim(-8.15,-11.6)
ax.set_xlabel('World X (m)');ax.set_ylabel('World Z (m)');ax.set_aspect('equal');ax.grid(alpha=.2)
ax.set_title('Local view: robot is 0.047 m from a later path segment')
ax.legend(loc='upper right',fontsize=8)
fig.savefig(report/'local-map.png',dpi=150);plt.close(fig)
assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==h for p,h in before.items())
result['protected_files_unchanged']=len(before)
(report/'source-hashes.json').write_text(json.dumps(before,indent=2)+'\n')
(report/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('summary','cpu_navmesh_probes')},indent=2))
