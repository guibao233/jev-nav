import sys,json,math
from pathlib import Path
import numpy as np
root=Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav');sys.path.insert(0,str(root))
from environment import load_pathfinder,shortest
cfg=json.loads((root/'config.json').read_text());pf=load_pathfinder(cfg);result=[]
for suffix,index in [('01',246),('02',149),('03',173)]:
 p=root/('runs/jev-challenge-turn-000-six-actions-'+suffix);r=json.loads((p/'steps.jsonl').read_text().splitlines()[index]);pos=np.asarray(r['pose']['position'],dtype=np.float32);yaw=r['pose']['yaw_rad'];valid=[]
 for offset in range(-180,180,15):
  angle=yaw+math.radians(offset);direction=np.array([-math.sin(angle),0,-math.cos(angle)],dtype=np.float32);end=pos+.25*direction
  if not pf.is_navigable(end):continue
  path=shortest(pf,pos,end)
  if path is None or abs(path[0]-.25)>.002:continue
  slide=np.asarray(pf.try_step(pos,end));no_slide=np.asarray(pf.try_step_no_sliding(pos,end))
  nudge=pos+.001*direction;nudged_end=nudge+.25*direction;after_nudge=np.asarray(pf.try_step_no_sliding(nudge,nudged_end))
  valid.append({'relative_turn_deg':offset,'end':end.tolist(),'end_extra_clearance_m':pf.distance_to_closest_obstacle(end,1.),'nav_shortest_m':path[0],'shortest_vertices':len(path[1]),'try_step_error_m':float(np.linalg.norm(slide-end)),'no_sliding_actual_m':float(np.linalg.norm(no_slide-pos)),'no_sliding_error_m':float(np.linalg.norm(no_slide-end)),'after_1mm_inward_shift_no_sliding_error_m':float(np.linalg.norm(after_nudge-nudged_end)),'inward_shift_navigable':pf.is_navigable(nudge)})
 result.append({'run':suffix,'step_1based':index+1,'position':pos.tolist(),'yaw_deg':math.degrees(yaw),'valid_straight_0_25m_endpoint_count':len(valid),'examples':valid})
 print(json.dumps(result[-1],indent=2))
Path('/tmp/jev-six-failure-audit-20260929/boundary-probes.json').write_text(json.dumps(result,indent=2))
