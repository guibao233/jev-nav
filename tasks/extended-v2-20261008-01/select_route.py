"""CPU-only deterministic route selection using existing NavMesh and planner."""
from pathlib import Path
import sys,json,copy
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from environment import load_pathfinder,shortest
from run import load_config,asset_manifest
from prepare_challenges import route_geometry
from clearance import ClearancePlanner,path_statistics
cfg=load_config(ROOT/'config.single-gpu.json');pf=load_pathfinder(cfg);seed=20261008;pf.seed(seed)
island=max(range(pf.num_islands),key=pf.island_area);rejections=[]
for attempt in range(1,10001):
 s=np.asarray(pf.get_random_navigable_point(island_index=island));g=np.asarray(pf.get_random_navigable_point_near(s,20.,island_index=island))
 if not np.isfinite(s).all() or not np.isfinite(g).all() or not pf.is_navigable(s) or not pf.is_navigable(g) or abs(s[1]-g[1])>.02:continue
 ends=[float(pf.distance_to_closest_obstacle(p,2.)) for p in (s,g)]
 if min(ends)<.25:continue
 path=shortest(pf,s,g)
 if path is None or not 16.<=path[0]<=20.:continue
 geom=route_geometry(path[1],path[0])
 if geom['path_height_span_m']>.02 or geom['significant_turns']<3 or geom['geodesic_to_euclidean_ratio']<1.35:continue
 print('candidate',attempt,'shortest',path[0],'turns',geom['significant_turns'],flush=True)
 try:
  planner=ClearancePlanner(pf,path[1],.1,.2,4.,2.)
  reference,search=planner.plan();stats=path_statistics(pf,reference)
  if stats['extra_navmesh_clearance_min_m']<.10:raise ValueError('minimum extra clearance below 0.10m')
 except ValueError as exc:
  rejections.append({'attempt':attempt,'geodesic_m':path[0],'reason':str(exc)});print('rejected',str(exc),flush=True);continue
 task={'id':'extended-000','category':'extended','start':s.tolist(),'goal':g.tolist(),'yaw_deg':0.,'pitch_deg':0,'geodesic_m':path[0],'path':path[1],'geometry':geom,'geodesic_to_euclidean_ratio':geom['geodesic_to_euclidean_ratio'],'endpoint_extra_navmesh_clearance_m':ends}
 data={'schema':1,'seed':seed,'sampling_attempts':attempt,'sampling_policy':'first pair on largest NavMesh island passing geometry AND clearance planning; geodesic 16-20m, >=3 bends >=30deg, detour ratio >=1.35, flat <=0.02m, endpoint extra clearance >=0.25m; default 0.10m grid centered reference must have minimum extra clearance >=0.10m; no model-based selection','rejected_geometric_candidates':rejections,'suggested_max_steps':500,'budget_note':'run.py requires --max-steps 500 explicitly','scene_dir':cfg['scene_dir'],'config_at_generation':cfg,'assets':asset_manifest(cfg),'tasks':[task]}
 centered=copy.deepcopy(data);ct=centered['tasks'][0];ct['shortest_path']=copy.deepcopy(path[1]);ct['path']=reference;ct['reference_path_kind']='clearance_weighted';ct['reference_planner']=dict(planner.parameters,search=search);ct['reference_statistics']={'original_shortest':path_statistics(pf,path[1]),'clearance_weighted':stats};ct['reference_path_length_m']=stats['length_m'];centered['reference_path_kind']='clearance_weighted';centered['reference_planner_version']=planner.parameters['version'];centered['evaluation_baseline']='geodesic_m and shortest_path remain original NavMesh shortest path; path is supplied reference'
 Path('/tmp/jev-extended-selected-source-20261008.json').write_text(json.dumps(data,indent=2));Path('/tmp/jev-extended-selected-clearance-20261008.json').write_text(json.dumps(centered,indent=2))
 print('SELECTED',json.dumps({'attempt':attempt,'task':task,'reference_statistics':ct['reference_statistics'],'reference_search':search}),flush=True);break
else:raise RuntimeError('no matching route after 10000 endpoint pairs')
