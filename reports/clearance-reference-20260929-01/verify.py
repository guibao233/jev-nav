"""Independent CPU validation of the task variant; no model or renderer."""
from pathlib import Path
import ast,hashlib,json,math,sys
import numpy as np
report=Path(__file__).resolve().parent;root=report.parent.parent
sys.path.insert(0,str(root))
from core import RoutePreview
from environment import load_pathfinder,direct_navmesh_connection,shortest
from map_view import relative_to_world
from run import load_config
from clearance import validate_reference_path,path_statistics
source=root/'tasks/challenge-v1-20260928/tasks.json'
variant=root/'tasks/challenge-clearance-20260929-01/tasks.json'
old_dataset=json.loads(source.read_text());new_dataset=json.loads(variant.read_text())
old=next(t for t in old_dataset['tasks'] if t['id']=='turn-000');new=new_dataset['tasks'][0]
for key in old:
    if key!='path':assert new[key]==old[key],key
assert new['shortest_path']==old['path']
assert new['path']!=old['path']
assert new_dataset['source_tasks']['sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
cfg=load_config(root/'config.json');pf=load_pathfinder(cfg)
assert math.isclose(shortest(pf,new['start'],new['goal'])[0],old['geodesic_m'],abs_tol=1e-5)
length=validate_reference_path(pf,new['path'],new['start'],new['goal'])
assert math.isclose(length,new['reference_path_length_m'],abs_tol=1e-9)
fine=path_statistics(pf,new['path'],sample_m=.01)
assert fine['extra_navmesh_clearance_min_m']>.35
assert fine['length_m']>old['geodesic_m']
route=RoutePreview(new['path'],reconnect=lambda a,b:direct_navmesh_connection(pf,a,b))
previous=0.;checked=0
for arc in np.r_[np.arange(0,route.total,.1),route.total]:
    position=route.at(arc)
    state=route.state(position,0,cfg)
    assert state['tracking']['mode']=='local'
    assert route.progress+1e-9>=previous
    previous=route.progress
    target=relative_to_world(state['current_target'],{'position':position,'yaw_rad':0})
    assert direct_navmesh_connection(pf,position,target)
    checked+=1
protected=json.loads((report/'protected-before.json').read_text())
assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==h for p,h in protected.items())
result={'source_task_fields_unchanged_except_path':True,'shortest_path_preserved':True,
 'original_geodesic_m':old['geodesic_m'],'new_reference_length_m':length,
 'reference_length_increase_percent':100*(length/old['geodesic_m']-1),
 'fine_reference_statistics':fine,'validated_segments':len(new['path'])-1,
 'minimum_segment_length_m':float(np.linalg.norm(np.diff(new['path'],axis=0),axis=1).min()),
 'ideal_following_states_and_direct_targets_checked':checked,
 'protected_files_unchanged':len(protected),'api_calls':0,'gpu_runs':0,
 'evidence_limit':'Reference geometry only; no claim of Jev task success or collision-free execution'}
(report/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
