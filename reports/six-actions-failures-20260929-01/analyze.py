import json,math,sys,hashlib,collections
from pathlib import Path
import numpy as np
root=Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav');sys.path.insert(0,str(root))
from environment import load_pathfinder,shortest
from core import RoutePreview,relative
first=root/'runs/jev-challenge-turn-000-six-actions-01';m=json.loads((first/'metadata.json').read_text());cfg=m['config'].copy();pf=load_pathfinder(cfg);pts=np.asarray(m['task']['path']);route=RoutePreview(pts)
assert hashlib.sha256((Path(cfg['scene_dir'])/'shuyuan.navmesh').read_bytes()).hexdigest()==m['assets']['shuyuan.navmesh']['sha256']
arc=np.arange(0,route.total,.05);samples=[route.at(a) for a in arc];clearance=np.array([pf.distance_to_closest_obstacle(p,2.) for p in samples])
def full_offset(pos):
 v=pts[1:]-pts[:-1];t=np.clip(np.sum((pos-pts[:-1])*v,axis=1)/np.sum(v*v,axis=1),0,1)
 return float(np.min(np.linalg.norm(pos-(pts[:-1]+v*t[:,None]),axis=1)))
def forward(yaw):return np.array([-math.sin(yaw),0,-math.cos(yaw)])
def step(pos,yaw,d=.25):
 end=np.asarray(pf.try_step_no_sliding(pos,pos+d*forward(yaw)))
 return float(np.linalg.norm(end-pos)),float(np.linalg.norm(end-(pos+d*forward(yaw))))
result={'path_clearance':{'definition':'extra clearance to NavMesh boundary; NavMesh already eroded for agent radius','sample_spacing_m':.05,'count':len(clearance),'min_m':float(clearance.min()),'median_m':float(np.median(clearance)),'fraction_below_0_10_m':float(np.mean(clearance<.1)),'fraction_below_0_20_m':float(np.mean(clearance<.2)),'vertex_clearance_m':[float(pf.distance_to_closest_obstacle(p,2.)) for p in pts]},'runs':{}}
for suffix in ['01','02','03']:
 p=root/('runs/jev-challenge-turn-000-six-actions-'+suffix);meta=json.loads((p/'metadata.json').read_text());rows=[json.loads(x) for x in (p/'steps.jsonl').read_text().splitlines()];a=[x for x in rows if x.get('outcome')];route=RoutePreview(meta['task']['path']);cfg=meta['config'];history=[];max_pose_error=0.;max_yaw_error=0.;non_nav=0
 for i,r in enumerate(a):
  state=r['request']['state'];pos=np.asarray(r['pose']['position']);yaw=r['pose']['yaw_rad'];after=np.asarray(r['after_position']);act=r['outcome']['action']
  assert state['reference']==route.state(pos,yaw,cfg)
  assert state['reference']['final_goal']==relative(meta['task']['goal'],pos,yaw)
  assert state['recent_actions']==history[-5:]
  assert r['decision']['response']['answers']['action']['choice']==r['decision']['choice']==act
  assert np.allclose(after,rows[i+1]['pose']['position'],atol=1e-6)
  end=np.asarray(pf.try_step_no_sliding(pos,pos+.25*forward(yaw))) if act=='move_forward' else pos
  max_pose_error=max(max_pose_error,float(np.linalg.norm(end-after)))
  dy=math.radians(15 if act=='turn_left' else -15 if act=='turn_right' else 0)
  error=rows[i+1]['pose']['yaw_rad']-(yaw+dy);max_yaw_error=max(max_yaw_error,abs(math.degrees(math.atan2(math.sin(error),math.cos(error)))))
  non_nav+=int(not pf.is_navigable(after));history.append(r['outcome'])
 collisions=[r for r in a if r['outcome']['collided']]
 first_collision=collisions[0];last=a[-1]
 stats={'summary':json.loads((p/'summary.json').read_text()),'max_recomputed_pose_error_m':max_pose_error,'max_recomputed_yaw_error_deg':max_yaw_error,'non_navigable_after_positions':non_nav,'first_collision_step_1based':first_collision['step']+1,'first_collision_full_route_offset_before_m':full_offset(np.array(first_collision['pose']['position'])),'first_collision_full_route_offset_after_m':full_offset(np.array(first_collision['after_position'])),'progress_end_m':route.progress,'collision_unknown_depth_count':sum(r['request']['state']['depth']['move_checks']['move_forward']['status']=='unknown' for r in collisions),'collision_without_collision_in_last5_count':sum(not any(h['collided'] for h in r['request']['state']['recent_actions']) for r in collisions),'collision_steps_with_last5_all_turns':[r['step']+1 for r in collisions if len(r['request']['state']['recent_actions'])==5 and all(h['action'].startswith('turn_') for h in r['request']['state']['recent_actions'])],'first_collision_extra_navmesh_clearance_m':pf.distance_to_closest_obstacle(first_collision['after_position'],2.),'models':sorted(set(r['decision']['response']['model'] for r in a))}
 indices=[13,246] if suffix=='01' else [13,149] if suffix=='02' else [13,173,239]
 probes=[]
 for i in indices:
  r=a[i];pos=np.asarray(r['pose']['position']);yaw=r['pose']['yaw_rad'];good=[]
  for offset in range(-180,181,15):
   moved,error=step(pos,yaw+math.radians(offset))
   if error<.001:good.append(offset)
  back_moved,back_error=step(pos,yaw,-.25)
  probes.append({'step_1based':i+1,'position':pos.tolist(),'logged_action':r['outcome']['action'],'logged_moved_m':r['outcome']['actual_translation_m'],'extra_navmesh_clearance_m':pf.distance_to_closest_obstacle(pos,2.),'backward_0_25m_query':{'actual_m':back_moved,'endpoint_error_m':back_error},'forward_0_25m_full_step_possible_yaw_offsets_deg':good,'nearest_escape_turn_abs_deg':min(map(abs,good)) if good else None,'recent_actions':r['request']['state']['recent_actions']})
 stats['offline_navmesh_escape_probes']=probes
 result['runs'][suffix]=stats
Path('/tmp/jev-six-failure-audit-20260929/analysis.json').write_text(json.dumps(result,indent=2))
print('PATH',json.dumps(result['path_clearance']))
for suffix,stats in result['runs'].items():
 print('RUN',suffix,json.dumps({k:v for k,v in stats.items() if k not in ['summary','offline_navmesh_escape_probes']}))
 for probe in stats['offline_navmesh_escape_probes']:print('PROBE',json.dumps({k:v for k,v in probe.items() if k!='recent_actions'}))
