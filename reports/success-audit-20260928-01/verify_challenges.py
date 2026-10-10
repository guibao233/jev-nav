"""Offline verification of the generated task file; no renderer or API."""
import sys,json,hashlib,math
from pathlib import Path
import numpy as np
root=Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav');sys.path.insert(0,str(root))
from environment import load_pathfinder,shortest
from core import RoutePreview
from map_view import relative_to_world
from prepare_challenges import sample_challenges,matches_tier,TIERS
folder=Path(sys.argv[1]);dataset=json.loads((folder/'tasks.json').read_text());cfg=dataset['config_at_generation'].copy();pf=load_pathfinder(cfg)
assert hashlib.sha256((Path(cfg['scene_dir'])/'shuyuan.navmesh').read_bytes()).hexdigest()==dataset['assets']['shuyuan.navmesh']['sha256']
again,_=sample_challenges(cfg.copy(),dataset['per_tier'],dataset['seed']);assert again['tasks']==dataset['tasks'] and again['sampling_attempts']==dataset['sampling_attempts']
original_pairs=set()
for name in ['debug-10.json','eval-50.json']:
 for t in json.loads((root/'tasks'/name).read_text())['tasks']:
  original_pairs.add(tuple(sorted(tuple(np.round(p,3)) for p in [t['start'],t['goal']])))
all_validation=[]
for t in dataset['tasks']:
 assert pf.is_navigable(t['start']) and pf.is_navigable(t['goal'])
 assert tuple(sorted(tuple(np.round(p,3)) for p in [t['start'],t['goal']])) not in original_pairs
 fresh=shortest(pf,t['start'],t['goal']);assert abs(fresh[0]-t['geodesic_m'])<1e-6 and np.allclose(fresh[1],t['path'])
 assert matches_tier(fresh[0],t['geometry'],TIERS[t['category']])
 pts=np.array(t['path']);polyline=sum(np.linalg.norm(b-a) for a,b in zip(pts[:-1],pts[1:]));assert abs(polyline-fresh[0])<2e-5
 route=RoutePreview(t['path']);pose_yaw=math.radians(t['yaw_deg']);previous=0.;max_target_reconstruction_error=0.;count=0
 # Feed ideal continuous positions, not a controller/physics/model rollout.
 for arc in [*np.arange(0.,route.total,.10),route.total]:
  pos=route.at(arc);state=route.state(pos,pose_yaw,cfg)
  assert route.progress>=previous and abs(route.progress-arc)<1e-4
  previous=route.progress
  corners=[x for x in route.arcs[1:-1] if x>route.progress+.12]
  target_arc=min(route.total,route.progress+cfg['target_lookahead_m'],corners[0] if corners else float('inf'))
  point=relative_to_world(state['current_target'],{'position':pos,'yaw_rad':pose_yaw})
  err=float(np.linalg.norm((np.array(point)-route.at(target_arc))[[0,2]]));assert err<.001
  max_target_reconstruction_error=max(max_target_reconstruction_error,err);count+=1
 assert state['current_target']['is_final'] and state['remaining_reference_length_m']==0.
 all_validation.append({'id':t['id'],'geodesic_m':fresh[0],'reference_vertices':len(t['path']),'geometry_probe_positions':count,'max_target_roundtrip_error_m':max_target_reconstruction_error})
result={'status':'passed','tasks':len(all_validation),'seed_reproducible':True,'navmesh_hash_matches':True,'overlap_with_basic_tasks':False,'checks':['all endpoints navigable; each shortest path recomputed','all length/turn/detour tiers satisfied','reference progress monotone on ideal sampled path','target stops at next corner with documented tolerance','final target reached at end of ideal path','same seed reproduces tasks exactly'], 'scope':'NavMesh geometry and input preparation only; NOT simulator discrete-action or Jev evaluation','per_task':all_validation}
print(json.dumps(result,indent=2))
# Only writes into a new task bundle, never overwrites verification evidence.
with (folder/'verification.json').open('x') as f: json.dump(result,f,indent=2)
