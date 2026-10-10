"""Offline audit of the recorded sliding run. No renderer or API calls."""
from pathlib import Path
import hashlib
import json
import math
import sys
from collections import Counter
import numpy as np

REPORT = Path(__file__).resolve().parent
ROOT = REPORT.parent.parent
sys.path.insert(0,str(ROOT))
from core import RoutePreview
from environment import load_pathfinder, shortest

run = ROOT/'runs/jev-challenge-turn-000-sliding-01'
metadata = json.loads((run/'metadata.json').read_text())
summary = json.loads((run/'summary.json').read_text())
records = [json.loads(x) for x in (run/'steps.jsonl').read_text().splitlines()]
rows = [r for r in records if r.get('outcome')]
cfg = metadata['config']
protected = [run/n for n in ['metadata.json','summary.json','steps.jsonl','navmap.png']]
protected += [ROOT/n for n in ['core.py','environment.py','run.py','jev.py','config.json']]
hashes = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
pf = load_pathfinder(cfg)
route = RoutePreview(metadata['task']['path'])
series = []
filter_errors = []
for r in rows:
    position = np.asarray(r['pose']['position'],dtype=np.float32)
    ref = r['request']['state']['reference']
    recalc = route.state(position,r['pose']['yaw_rad'],cfg)
    assert recalc == ref, r['step']
    best = (float('inf'),0.)
    for i,length in enumerate(route.lengths):
        arc = route.arcs[i]+np.clip(np.dot(position-route.points[i],(route.points[i+1]-route.points[i])/length),0,length)
        best = min(best,(float(np.linalg.norm(position-route.at(arc))),float(arc)))
    near = route.at(best[1]);connector = shortest(pf,position,near)
    outcome = r['outcome'];action = outcome['action']
    if action == 'move_forward':
        yaw = r['pose']['yaw_rad']
        desired = position+cfg['move_m']*np.array([-math.sin(yaw),0,-math.cos(yaw)],dtype=np.float32)
        predicted = np.asarray(pf.try_step(position,desired))
        filter_errors.append(float(np.linalg.norm(predicted-r['after_position'])))
    assert action == r['decision']['choice']
    assert pf.is_navigable(r['after_position'])
    series.append({'step_1based':r['step']+1,'position':position.tolist(),'action':action,
        'actual_m':outcome['actual_translation_m'],'collided':outcome['collided'],
        'logged_progress_m':float(route.progress),'global_nearest_arc_m':best[1],
        'global_nearest_distance_m':best[0],
        'distance_from_local_window_m':ref['distance_from_local_reference_m'],
        'current_target':ref['current_target'],
        'goal_geodesic_after_action_m':r['metrics']['distance_to_goal_geodesic_m'],
        'nearest_route_point':near.tolist(),'nearest_route_connector_m':connector[0] if connector else None,
        'nearest_route_connector_vertices':len(connector[1]) if connector else None,
        'forward_check':r['request']['state']['depth']['move_checks']['move_forward'],
        'history_contains_collision':any(h['collided'] for h in r['request']['state']['recent_actions'])})
forward = [x for x in series if x['action']=='move_forward']
collision = [x for x in series if x['collided']]
result = {'source_run':str(run),'summary':summary,'config':cfg,
    'all_logged_reference_states_recomputed':True,'all_post_action_positions_navigable':True,
    'forward_filter_max_error_m':max(filter_errors),'forward_count':len(forward),
    'forward_with_target_behind_count':sum(abs(x['current_target']['bearing_deg'])>90 for x in forward),
    'forward_moving_under_0_05_m':[x['step_1based'] for x in forward if x['actual_m']<.05],
    'action_counts':dict(Counter(x['action'] for x in series)),
    'depth_forward_status_counts':dict(Counter(x['forward_check']['status'] for x in series)),
    'blocked_forward_choices':sum(x['forward_check']['status']=='blocked' and x['action']=='move_forward' for x in series),
    'collision_steps':[x['step_1based'] for x in collision],
    'collision_without_recent_collision_count':sum(not x['history_contains_collision'] for x in collision),
    'progress_changes':[{'step_1based':x['step_1based'],'progress_m':x['logged_progress_m']} for i,x in enumerate(series) if i==0 or abs(x['logged_progress_m']-series[i-1]['logged_progress_m'])>1e-6],
    'nearest_goal':min(series,key=lambda x:x['goal_geodesic_after_action_m']),
    'critical_steps':[series[i-1] for i in [1,14,93,95,96,115,116,117,118,119,120,250]],
    'series':series,'reran_simulator':False,'called_jev':False}
(REPORT/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
(REPORT/'source_hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image
fig = plt.figure(figsize=(15,8),layout='constrained')
grid = fig.add_gridspec(2,2,width_ratios=[1.05,1])
ax = fig.add_subplot(grid[:,0]);progress_ax = fig.add_subplot(grid[0,1]);distance_ax = fig.add_subplot(grid[1,1])
with Image.open(run/'navmap.png') as im: nav=np.asarray(im.convert('RGB'))
info=metadata['map'];res=info['resolution_m'];x0,z0=info['origin_x'],info['origin_z']
ax.imshow(nav,extent=(x0,x0+nav.shape[1]*res,z0+nav.shape[0]*res,z0),interpolation='nearest')
path=np.asarray(metadata['task']['path']);positions=np.asarray([r['pose']['position'] for r in records])
ax.plot(path[:,0],path[:,2],color='#2675ed',lw=3,label='Initial shortest route')
ax.plot(positions[:,0],positions[:,2],color='#e98a17',lw=1.6,alpha=.85,label='Executed trajectory')
coll_pos=np.asarray([rows[x['step_1based']-1]['after_position'] for x in collision])
ax.scatter(coll_pos[:,0],coll_pos[:,2],c='#e13944',marker='x',s=50,label='Collision feedback')
ax.scatter(path[0,0],path[0,2],c='#04ab66',s=75,edgecolors='black',zorder=5,label='Start')
ax.scatter(path[-1,0],path[-1,2],c='#e13944',s=100,marker='*',edgecolors='black',zorder=5,label='Final goal')
ax.scatter(path[1,0],path[1,2],c='#c900ad',s=85,marker='D',edgecolors='black',zorder=5,label='Frozen target (step 93+)')
s=series[116];p=s['position']
ax.scatter(p[0],p[2],s=150,facecolors='none',edgecolors='#02adb8',lw=3,zorder=6)
ax.annotate('Step 117: 2.1 cm from route\nNearest arc 3.13 m, logged 0.40 m',(p[0],p[2]),xytext=(-14.2,-7.5),arrowprops={'arrowstyle':'->'},fontsize=10,bbox={'facecolor':'white','alpha':.9,'edgecolor':'none'})
ax.set_xlim(min(positions[:,0].min(),path[:,0].min())-.7,max(positions[:,0].max(),path[:,0].max())+.7)
ax.set_ylim(max(positions[:,2].max(),path[:,2].max())+.7,min(positions[:,2].min(),path[:,2].min())-.7)
ax.set_aspect('equal');ax.set_xlabel('World X (m)');ax.set_ylabel('World Z (m, down)');ax.set_title('Recorded route, motion, and collisions')
ax.legend(loc='lower right',fontsize=8)
steps=np.arange(1,len(series)+1)
progress_ax.plot(steps,[x['global_nearest_arc_m'] for x in series],color='#888888',label='Nearest full-route arc (diagnostic, not credited progress)')
progress_ax.plot(steps,[x['logged_progress_m'] for x in series],color='#2675ed',lw=2.5,label='Actual logged route progress')
progress_ax.set_ylabel('Route arc length (m)');progress_ax.set_title('Progress remains frozen after step 93');progress_ax.legend(fontsize=8)
distance_ax.plot(steps,[x['distance_from_local_window_m'] for x in series],color='#e98a17',label='Distance to old local search window')
distance_ax.plot(steps,[x['global_nearest_distance_m'] for x in series],color='#02adb8',label='Distance to entire route')
distance_ax.axhline(.5,ls=':',color='black',alpha=.5,label='0.5 m acceptance threshold')
distance_ax.set_ylabel('Distance (m)');distance_ax.set_xlabel('Decision step (1-based)');distance_ax.legend(fontsize=8)
for panel in [progress_ax,distance_ax]:panel.axvline(117,color='#555555',ls='--',alpha=.5);panel.grid(alpha=.2)
fig.suptitle('Jev sliding-01: execution is mobile, but route recovery and decisions fail',fontsize=14)
fig.savefig(REPORT/'trajectory-and-progress.png',dpi=150);plt.close(fig)
for name,digest in hashes.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
print(json.dumps({k:v for k,v in result.items() if k not in ['series','critical_steps','config','nearest_goal']},indent=2))
