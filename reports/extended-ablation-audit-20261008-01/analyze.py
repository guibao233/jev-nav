"""Offline audit of six fixed-route Jev runs; no renderer, GPU, or API."""
from pathlib import Path
from collections import Counter
import hashlib,json,math,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from core import RoutePreview,recent_motion_summary,depth_facts
from depth_language import semantic_depth
from environment import load_pathfinder,shortest,direct_navmesh_connection
OUT=Path('/tmp/jev-extended-ablation-audit-20261008-01');OUT.mkdir(exist_ok=True)
names=[f'jev-extended-rgbgs-{mode}-20261008-0{i}' for mode in ['numeric','semantic','none'] for i in [1,2]]
protected=[ROOT/n for n in ['run.py','core.py','environment.py','jev.py','depth_language.py','config.json','config.single-gpu.json','tasks/extended-clearance-aligned-20261008-01/tasks.json']]
for name in names:protected.extend(ROOT/'runs'/name/n for n in ['metadata.json','summary.json','steps.jsonl'])
hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
base=None;results=[];all_rows={};depth_samples=0

def no_numbers(v):
 if isinstance(v,dict):return all(no_numbers(x) for x in v.values())
 if isinstance(v,list):return all(no_numbers(x) for x in v)
 return not isinstance(v,(int,float))

for name in names:
 folder=ROOT/'runs'/name;m=json.loads((folder/'metadata.json').read_text());s=json.loads((folder/'summary.json').read_text());rows=[json.loads(l) for l in (folder/'steps.jsonl').read_text().splitlines()];a=[r for r in rows if r.get('outcome')];cfg=m['config'];mode=s['depth_format']
 if base is None:base=m
 assert m['task']==base['task'] and m['assets']==base['assets'] and m['available_actions']==base['available_actions']
 assert {k:v for k,v in cfg.items() if k not in ['depth_input','depth_format']}=={k:v for k,v in base['config'].items() if k not in ['depth_input','depth_format']}
 assert m['rgb_mode']=='gs' and not m['rgb_provided_to_model'] and cfg['max_steps']==500
 assert m['provider']=='jev' and s['is_jev_evaluation']
 assert len(a)==s['steps'] and len(rows)==len(a)+1 and [r['step'] for r in rows]==list(range(len(rows)))
 assert all(math.dist(r['after_position'],rows[i+1]['pose']['position'])<1e-6 for i,r in enumerate(a))
 pf=load_pathfinder(dict(cfg));route=RoutePreview(m['task']['path'],reconnect=lambda x,y:direct_navmesh_connection(pf,x,y));history=[];distances=[];travel=0
 assert abs(shortest(pf,m['task']['start'],m['task']['goal'])[0]-s['initial_geodesic_m'])<1e-6
 selected={0,len(a)-1,*range(0,len(a),100)}
 for flag in ['collided','valid']:
  event=next((i for i,r in enumerate(a) if (r['outcome'][flag] if flag=='collided' else not r['outcome'][flag])),None)
  if event is not None:selected.add(event)
 for i,r in enumerate(a):
  o=r['outcome'];state=r['request']['state'];position=np.asarray(r['pose']['position'],dtype=np.float32)
  assert route.state(position,r['pose']['yaw_rad'],cfg)==state['reference'],(name,i,'reference mismatch')
  assert state['recent_actions']==history[-cfg['history_steps']:]
  assert state['recent_motion']==recent_motion_summary(history,cfg['history_steps'],cfg['move_m'])
  history.append(o);history=history[-cfg['history_steps']:]
  assert r['decision']['choice']==o['action']==r['decision']['response']['answers']['action']['choice']
  assert r['decision']['response']['model']=='typesafe/jev-1.13-20260917'
  d=shortest(pf,r['after_position'],m['task']['goal']);distance=None if d is None else d[0];distances.append(distance)
  assert distance is not None and abs(distance-r['metrics']['distance_to_goal_geodesic_m'])<1e-6
  travel+=math.dist(r['pose']['position'],r['after_position']);assert abs(travel-r['metrics']['path_length_m'])<1e-4
  pitch=r['pose']['pitch_deg'];expected_pitch=pitch+(cfg['pitch_deg'] if o['action']=='look_down' else -cfg['pitch_deg'] if o['action']=='look_up' else 0)
  assert o['valid']==(o['action'] in m['available_actions'] and cfg['pitch_min_deg']<=expected_pitch<=cfg['pitch_max_deg'])
  if mode=='none':assert 'depth' not in state
  elif mode=='semantic':
   assert semantic_depth(r['depth_numeric_debug'])==state['depth'] and no_numbers(state['depth'])
   assert 'depth_numeric_debug' not in json.dumps(r['request'])
  if i in selected and mode!='none':
   with np.load(folder/r['images']['depth'].replace('.png','.npz')) as saved:facts=depth_facts(saved['depth_m'],pitch,cfg)
   assert facts==(r['depth_numeric_debug'] if mode=='semantic' else state['depth'])
   depth_samples+=1
  for key in ['depth','rgb']:assert (folder/r['images'][key]).is_file()
 assert sum(r['outcome']['collided'] for r in a)==s['collisions']
 assert sum(not r['outcome']['valid'] for r in a)==s['invalid_actions']
 assert abs(travel-s['path_length_m'])<1e-4 and abs(distances[-1]-s['final_geodesic_m'])<1e-6
 reached=min(distances)<=cfg['success_m'];assert reached==s['ever_within_goal_tolerance']
 assert s['success']==(a[-1]['outcome']['action']=='stop' and distances[-1]<=cfg['success_m'])
 assert s['collision_free_success']==(s['success'] and s['collisions']==0)
 assert abs(s['spl']-(s['initial_geodesic_m']/max(s['initial_geodesic_m'],travel) if s['success'] else 0))<1e-6
 if s['success']:assert a[-2]['metrics']['distance_to_goal_geodesic_m']<=cfg['success_m']
 else:assert s['status']=='action_budget' and len(a)==500 and not reached
 best=int(np.argmin(distances));first2=next((i+1 for i,d in enumerate(distances) if d<2),None);last80=a[-80:];acts=Counter(r['outcome']['action'] for r in a);moves=sum(v for k,v in acts.items() if k.startswith('move_'))
 results.append({'run':name,'mode':mode,'repeat':name[-2:],'summary':s,'minimum_goal_distance_m':distances[best],'minimum_distance_step':best+1,'first_under_2m_step':first2,'action_counts':dict(acts),'move_attempts':moves,'invalid_action_types':dict(Counter(r['outcome']['action'] for r in a if not r['outcome']['valid'])),'motion_status_counts':dict(Counter(r['request']['state']['recent_motion']['status'] for r in a)),'last_80_net_translation_m':math.dist(last80[0]['pose']['position'],last80[-1]['after_position']),'last_80_travel_m':sum(r['outcome']['actual_translation_m'] for r in last80),'retries':sum(r['decision']['attempts']>1 for r in a),'final_reference':a[-1]['request']['state']['reference'],'last_position':a[-1]['after_position']})
 all_rows[name]=(m,a,distances)
 print('VERIFIED',name,len(a),'actions',flush=True)

aggregate={};divergences={}
for mode in ['numeric','semantic','none']:
 sub=[r for r in results if r['mode']==mode];agg={'runs':len(sub),'successes':sum(r['summary']['success'] for r in sub),'collision_free_successes':sum(r['summary']['collision_free_success'] for r in sub),'collisions':sum(r['summary']['collisions'] for r in sub),'invalid_actions':sum(r['summary']['invalid_actions'] for r in sub),'actions':sum(r['summary']['steps'] for r in sub),'move_attempts':sum(r['move_attempts'] for r in sub),'mean_spl':sum(r['summary']['spl'] for r in sub)/len(sub)};agg['collision_fraction_of_move_attempts']=agg['collisions']/agg['move_attempts'];aggregate[mode]=agg
 a=all_rows[f'jev-extended-rgbgs-{mode}-20261008-01'][1];b=all_rows[f'jev-extended-rgbgs-{mode}-20261008-02'][1]
 for x,y in zip(a,b):
  if x['decision']['choice']!=y['decision']['choice']:
   divergences[mode]={'first_different_action_step':x['step']+1,'identical_requests_at_divergence':x['request']==y['request'],'choices':[x['decision']['choice'],y['decision']['choice']]};break
assert hashes=={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
output={'scope':'one fixed extended-000 route, two repetitions per input; six completed real Jev evaluations','runs':results,'aggregate':aggregate,'repeat_divergence':divergences,'verification':{'actions':sum(r['summary']['steps'] for r in results),'all_geodesic_distances_recomputed':True,'all_reference_states_recomputed':True,'all_recent_history_recomputed':True,'all_semantic_encodings_checked':True,'raw_depth_sample_frames_checked':depth_samples,'protected_files':hashes,'source_files_unchanged':True,'api_calls':0,'used_gpu':False}}
(OUT/'audit.json').write_text(json.dumps(output,indent=2,ensure_ascii=False)+'\n')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Circle
colors={'numeric':'#18804b','semantic':'#a04bb4','none':'#d55c3e'}
navmeta=base['map'];from PIL import Image
nav=np.asarray(Image.open(ROOT/'runs'/names[0]/'navmap.png'));extent=[navmeta['origin_x'],navmeta['origin_x']+nav.shape[1]*navmeta['resolution_m'],navmeta['origin_z']+nav.shape[0]*navmeta['resolution_m'],navmeta['origin_z']]
ref=np.asarray(base['task']['path']);points=np.concatenate([np.asarray([r['pose']['position'] for r in v[1]]+[v[1][-1]['after_position']]) for v in all_rows.values()]+[ref]);lo=points[:,[0,2]].min(axis=0)-.6;hi=points[:,[0,2]].max(axis=0)+.6
fig,axes=plt.subplots(2,3,figsize=(15,10),constrained_layout=True)
for col,mode in enumerate(['numeric','semantic','none']):
 for row,repeat in enumerate(['01','02']):
  name=f'jev-extended-rgbgs-{mode}-20261008-{repeat}';m,a,ds=all_rows[name];item=next(x for x in results if x['run']==name);ax=axes[row,col];p=np.asarray([r['pose']['position'] for r in a]+[a[-1]['after_position']]);ax.imshow(nav,extent=extent);ax.plot(ref[:,0],ref[:,2],ls='--',color='#197cce',lw=1.5,label='Reference');ax.plot(p[:,0],p[:,2],color=colors[mode],lw=1.2,alpha=.8,label='Executed');start,goal=np.asarray(m['task']['start']),np.asarray(m['task']['goal']);ax.scatter(start[0],start[2],marker='s',s=35,color='#1f6b36',zorder=5,label='Start');ax.add_patch(Circle((goal[0],goal[2]),.3,fill=False,color='#a82020',lw=1.5));ax.scatter(goal[0],goal[2],marker='*',s=90,color='#a82020',zorder=5,label='Goal');ax.scatter(p[-1,0],p[-1,2],marker='x',s=70,color='black',zorder=6,label='Final position');hit=np.array([r['after_position'] for r in a if r['outcome']['collided']]);
  if len(hit):ax.scatter(hit[:,0],hit[:,2],marker='x',s=24,color='#f00000',zorder=7,label='Collision')
  ax.set_xlim(lo[0],hi[0]);ax.set_ylim(hi[1],lo[1]);ax.set_aspect('equal');s=item['summary'];ax.set_title(f"{mode} / repeat {repeat}: {s['status']}\n{s['steps']} actions, {s['collisions']} collisions, final {s['final_geodesic_m']:.2f} m",fontsize=10);ax.set_xlabel('World X (m)');ax.set_ylabel('World Z (m)');ax.grid(alpha=.15)
axes[0,0].legend(fontsize=8,loc='lower left');fig.suptitle('Extended-route input ablation: recorded trajectories',fontsize=16);fig.savefig(OUT/'trajectories.png',dpi=160);plt.close(fig)
fig,axes=plt.subplots(1,3,figsize=(15,4),sharey=True,constrained_layout=True)
for ax,mode in zip(axes,['numeric','semantic','none']):
 for repeat,color in [('01','#2166ac'),('02','#d95f02')]:
  name=f'jev-extended-rgbgs-{mode}-20261008-{repeat}';ds=all_rows[name][2];ax.plot(range(1,len(ds)+1),ds,color=color,lw=1.3,label=f'Repeat {repeat}')
 ax.axhline(.3,color='#888888',ls='--',lw=1,label='Success tolerance 0.30 m');ax.set_xlim(0,500);ax.set_ylim(0,19);ax.set_title(mode);ax.set_xlabel('Executed action number');ax.grid(alpha=.2)
axes[0].set_ylabel('NavMesh distance to final goal (m)');axes[-1].legend(fontsize=8);fig.suptitle('Goal progress: lower is closer; failures reached the 500-action limit');fig.savefig(OUT/'goal-distance.png',dpi=160);plt.close(fig)
print('AGGREGATE',json.dumps(aggregate),flush=True)
print('CHECKED',output['verification']['actions'],'actions;',depth_samples,'raw depth frames; source hashes unchanged')
