"""Extend the frozen 55-run comparison with 18 local OneJev runs. CPU-only audit."""
from pathlib import Path
from collections import Counter
import base64, copy, csv, hashlib, io, json, math, sys
import numpy as np
from PIL import Image
ROOT=Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav')
OUT=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent
OUT.mkdir(parents=True,exist_ok=True);sys.path.insert(0,str(ROOT))
from environment import load_pathfinder,shortest
from depth_language import semantic_depth
from jev import encode_request
from rgb_input import project_target
ROUTES=['simple','complex','extended'];MODES=['numeric','semantic','none']
SCHEMES=['jev','openai_text','openai_rgb','onejev_rgb']
TASKS=dict(zip(ROUTES,['tasks/debug-10.json','tasks/challenge-clearance-aligned-20260930-01/tasks.json','tasks/extended-clearance-aligned-20261008-01/tasks.json']))
IDS=dict(zip(ROUTES,['episode-000','turn-000','extended-000']));BUDGETS=dict(zip(ROUTES,[100,250,500]))
hashes={};prior_hashes={};code_drift=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def protect(p):
 h=sha(p)
 key=str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)
 hashes[key]=h;return h
def near(a,b,tol=1e-6):assert abs(a-b)<=tol,(a,b)
prior_name='reports/model-navigation-comparison-20261010-01/audit.json'
local_name='reports/onejev-local-rounds-audit-01/audit.json'
for name in [prior_name,local_name]:protect(ROOT/name)
prior=json.loads((ROOT/prior_name).read_text());local=json.loads((ROOT/local_name).read_text())
# Historical code legitimately changed during local-provider integration. Preserve
# historical hashes, record code drift, and require original run/task evidence intact.
for group in [prior['verification']['source_sha256'],prior['verification']['prior_source_hashes'],local['source_hashes']]:
 for name,digest in group.items():
  p=ROOT/name
  if sha(p)!=digest:
   assert not name.startswith(('runs/','tasks/')),(name,'historical experiment changed')
   code_drift.append(dict(path=name,historical_sha256=digest,current_sha256=sha(p)))
  else:prior_hashes[name]=digest
for name in ['run.py','core.py','environment.py','jev.py','onejev.py','rgb_input.py','depth_language.py']:
 protect(ROOT/name)
fixed={}
for route,name in TASKS.items():
 protect(ROOT/name);fixed[route]=next(t for t in json.loads((ROOT/name).read_text())['tasks'] if t['id']==IDS[route])
eligible=[dict(run=r['run'],route=r['route'],mode=r['input'],scheme=r['scheme'],batch=r['batch']) for r in prior['rows']]
for route in ROUTES:
 for mode in MODES:
  for batch in ['01','02']:
   eligible.append(dict(run=f'onejev-local-rgbtarget-{route}-rgbgs-{mode}-local-round-{batch}',route=route,mode=mode,scheme='onejev_rgb',batch=batch))
assert len(eligible)==len({r['run'] for r in eligible})==73
rows=[];details={};first_facts={};vision_questions={};pf=None;common=None
all_actions=0;image_calls=Counter();marker_counts=Counter();full_sequences={}
for spec in eligible:
 name,route,mode,scheme=spec['run'],spec['route'],spec['mode'],spec['scheme'];p=ROOT/'runs'/name
 for filename in ['metadata.json','summary.json','steps.jsonl']:protect(p/filename)
 m=json.loads((p/'metadata.json').read_text());s=json.loads((p/'summary.json').read_text())
 records=[json.loads(x) for x in (p/'steps.jsonl').read_text().splitlines()]
 a=records[:-1];cfg=m['config'];task=m['task'];all_actions+=len(a)
 assert len(a)==s['steps'] and [r['step'] for r in records]==list(range(len(records)))
 assert records[-1]['frame_kind']=='after_final_action' and records[-1]['request'] is None
 assert all(task[k]==fixed[route][k] for k in ['start','goal','path','yaw_deg','pitch_deg'])
 assert m['prompt_version'].startswith('seven_actions_reassociate_motion_v5')
 assert cfg['max_steps']==BUDGETS[route]
 assert list(m['available_actions'])==['move_forward','move_backward','turn_left','turn_right','look_up','look_down','stop']
 c={k:v for k,v in cfg.items() if k not in ['gpu_id','depth_input','depth_format','max_steps','model','rgb_input','onejev_url','onejev_timeout_s']}
 if common is None:common=c
 assert common==c,('different geometric/strategy config',name)
 vision=scheme in ['openai_rgb','onejev_rgb']
 assert bool(m.get('rgb_provided_to_model',False))==vision
 if 'depth_provided_to_model' in s:assert s['depth_provided_to_model']==(mode!='none')
 if vision:assert cfg['rgb_input']=='target_marked' and m['rgb_mode']=='gs'
 if pf is None:pf=load_pathfinder(dict(cfg));protect(Path(cfg['scene_dir'])/'shuyuan.navmesh')
 assert sha(Path(cfg['scene_dir'])/'shuyuan.navmesh')==m['assets']['shuyuan.navmesh']['sha256']
 initial=shortest(pf,task['start'],task['goal'])[0];near(initial,s['initial_geodesic_m'])
 near(math.dist(records[0]['pose']['position'],task['start']),0.)
 travel=0.;ds=[];counts=Counter();latencies=[];cycles=[];collisions=[];invalids=[];markers=Counter();projections=Counter();stationary=[];start=None
 model='typesafe/jev-1.13-20260917' if scheme=='jev' else 'OmniJev/OneJev-4B' if scheme=='onejev_rgb' else 'openai/gpt-6-luna-decisions-20261006'
 if 'response_models' in s:assert s['response_models']==[model]
 pair_seq=[]
 for i,r in enumerate(a):
  req,dec,o=r['request'],r['decision'],r['outcome'];state=req['state']
  assert dec['response']['model']==model and o['action']==dec['choice']==dec['response']['answers']['action']['choice']
  assert o['action'] in req['questions']['action']['criteria']
  assert math.dist(r['after_position'],records[i+1]['pose']['position'])<1e-6
  d=shortest(pf,r['after_position'],task['goal'])[0];near(d,r['metrics']['distance_to_goal_geodesic_m']);ds.append(d)
  travel+=math.dist(r['pose']['position'],r['after_position']);near(travel,r['metrics']['path_length_m'],1e-4)
  if mode=='none':assert 'depth' not in state
  elif mode=='semantic':assert semantic_depth(r['depth_numeric_debug'])==state['depth']
  else:assert len(state['depth']['sectors'])==9
  if vision:
   im=r['image_input'];b=(p/im['path']).read_bytes();digest=protect(p/im['path'])
   assert digest==im['sha256'] and len(b)==im['bytes'] and r['images']['model_rgb']==im['path']
   with Image.open(io.BytesIO(b)) as image:
    assert image.format=='JPEG' and image.size==(640,480);image.verify()
   assert state['visual']['marker']==im['marker'] and state['visual']['source']=='current_gs_rgb'
   projection=project_target(state['reference']['current_target'],r['pose']['pitch_deg'],cfg,im['marker']['target_height_above_agent_feet_m'])
   assert all(projection[k]==im['marker'][k] for k in projection)
   if scheme=='onejev_rgb':
    wire=copy.deepcopy(req);wire['state']['visual']['image']='<image:1>'
    wire['media']=[{'type':'image','data':'data:image/jpeg;base64,'+base64.b64encode(b).decode('ascii')}]
    wire=json.dumps(wire,allow_nan=False).encode()
    assert dec['response']['qev']['media']['images']==1
   else:wire=encode_request(req,b)
   assert hashlib.sha256(wire).hexdigest()==r['wire_request_sha256']==dec['request_body_sha256']
   image_calls[scheme]+=1;markers[im['marker']['marker_kind']]+=1;projections[im['marker']['projection_status']]+=1
  else:
   assert 'visual' not in state and 'image_input' not in r
  counts[o['action']]+=1
  if o['collided']:collisions.append(r['after_position'])
  if not o['valid']:invalids.append(r['pose']['position'])
  latencies.append(dec['latency_s']);cycles.append(r['metrics']['cycle_s'])
  still=math.dist(r['pose']['position'],r['after_position'])<1e-4 and o['action']!='stop'
  if still and start is None:start=i
  elif not still and start is not None:
   stationary.append(dict(first_action=start+1,last_action=i,count=i-start));start=None
  pair_seq.append(dict(request=req,pose=r['pose'],after=r['after_position'],outcome=o,answers=dec['response']['answers'],image_sha256=r.get('image_input',{}).get('sha256'),wire_sha256=r.get('wire_request_sha256')))
 if start is not None:stationary.append(dict(first_action=start+1,last_action=len(a),count=len(a)-start))
 success=a[-1]['outcome']['action']=='stop' and ds[-1]<=cfg['success_m']
 status='success' if success else 'early_stop' if a[-1]['outcome']['action']=='stop' else 'action_budget'
 assert s['success']==success and s['status']==status
 assert s['collisions']==len(collisions) and s['invalid_actions']==len(invalids)
 assert s['collision_free_success']==(success and not collisions)
 assert s['ever_within_goal_tolerance']==(min(initial,*ds)<=cfg['success_m'])
 near(travel,s['path_length_m'],1e-4);near(ds[-1],s['final_geodesic_m'])
 near(s['spl'],initial/max(initial,travel) if success else 0.)
 latency=s.get('model_request_latency') or s.get('jev_request_latency')
 for k,q in [('p50_s',50),('p95_s',95)]:
  near(float(np.percentile(latencies,q)),latency[k]);near(float(np.percentile(cycles,q)),s['cycle_including_render_and_logging'][k])
 first_reached=next((i+1 for i,d in enumerate(ds) if d<=.3),None)
 row=dict(scheme=scheme,route=route,input=mode,run=name,batch=spec['batch'],rgb_replay=m['rgb_mode'],status=status,success=success,collision_free_success=success and not collisions,steps=len(a),collisions=len(collisions),invalid_actions=len(invalids),path_length_m=s['path_length_m'],final_geodesic_m=ds[-1],initial_geodesic_m=initial,spl=s['spl'],minimum_geodesic_m=min(initial,*ds),reference_path_length_m=m['reference_path_length_m'],first_within_goal_action=first_reached,actions_after_first_arrival=len(a)-first_reached if first_reached else None,turn_actions=counts['turn_left']+counts['turn_right'],pitch_actions=counts['look_up']+counts['look_down'],translation_attempts=counts['move_forward']+counts['move_backward'],model_latency_p50_s=float(np.percentile(latencies,50)),model_latency_p95_s=float(np.percentile(latencies,95)),elapsed_s=s['elapsed_s'],rgb_provided_to_model=vision,response_model=model)
 rows.append(row)
 details[name]=dict(positions=[r['pose']['position'] for r in records],distance_series_m=[initial,*ds],action_counts=dict(counts),collision_positions=collisions,invalid_positions=invalids,longest_stationary_span=max(stationary,key=lambda x:x['count']) if stationary else None,marker_counts=dict(markers),projection_counts=dict(projections),response_model=model,map=m['map'],task=task)
 clean=copy.deepcopy(a[0]['request']);clean.pop('model');clean['state'].pop('visual',None)
 key=(route,mode)
 if key in first_facts:
  assert clean['state']==first_facts[key]['state'] and clean['questions']['action']['criteria']==first_facts[key]['questions']['action']['criteria']
 else:first_facts[key]=clean
 if vision:
  if key in vision_questions:assert clean['questions']==vision_questions[key]
  else:vision_questions[key]=clean['questions']
 if scheme!='jev':full_sequences[name]=pair_seq
 print('VERIFIED',scheme,route,mode,name,len(a),flush=True)
rows.sort(key=lambda r:(ROUTES.index(r['route']),MODES.index(r['input']),SCHEMES.index(r['scheme']),r['run']))
aggregates=[];representatives=[]
for route in ROUTES:
 for mode in MODES:
  for scheme in SCHEMES:
   group=[r for r in rows if (r['route'],r['input'],r['scheme'])==(route,mode,scheme)]
   g=dict(scheme=scheme,route=route,input=mode,runs=len(group),successes=sum(r['success'] for r in group),collision_free_successes=sum(r['collision_free_success'] for r in group),total_steps=sum(r['steps'] for r in group),total_collisions=sum(r['collisions'] for r in group),total_invalid_actions=sum(r['invalid_actions'] for r in group),success_rate=sum(r['success'] for r in group)/len(group))
   for field in ['steps','collisions','invalid_actions','path_length_m','final_geodesic_m','spl']:
    vals=[r[field] for r in group];g['mean_'+field]=float(np.mean(vals));g['min_'+field]=min(vals);g['max_'+field]=max(vals)
   aggregates.append(g)
   rep=next(r for r in group if '-rgbgs-' in r['run'] and r['run'].endswith('-01'))
   representatives.append(dict(rep,selection='first_GS_batch_01_not_selected_by_outcome'));protect(ROOT/'runs'/rep['run']/'navmap.png')
totals=[]
for scheme in SCHEMES:
 group=[r for r in rows if r['scheme']==scheme];groups=[g for g in aggregates if g['scheme']==scheme]
 totals.append(dict(scheme=scheme,runs=len(group),successes=sum(r['success'] for r in group),collision_free_successes=sum(r['collision_free_success'] for r in group),steps=sum(r['steps'] for r in group),collisions=sum(r['collisions'] for r in group),invalid_actions=sum(r['invalid_actions'] for r in group),macro_success_rate_equal_conditions=float(np.mean([g['success_rate'] for g in groups]))))
pairs={}
for scheme in SCHEMES[1:]:
 for route in ROUTES:
  for mode in MODES:
   names=[r['run'] for r in rows if (r['scheme'],r['route'],r['input'])==(scheme,route,mode)]
   assert len(names)==2 and full_sequences[names[0]]==full_sequences[names[1]]
   pairs[f'{scheme}/{route}/{mode}']='requests, poses, outcomes, probabilities and image/wire hashes identical; timings/response IDs excluded'
assert all_actions==15260 and len(representatives)==len(aggregates)==36
for name,digest in {**prior_hashes,**hashes}.items():assert sha(ROOT/name)==digest,name
result=dict(scope='frozen historical 55-run comparison plus exactly 18 local OneJev rounds',rows=rows,aggregate=aggregates,representatives=representatives,totals=totals,details=details,excluded=prior['excluded'],verification=dict(runs=73,actions_recomputed=all_actions,source_sha256=hashes,prior_source_hashes=prior_hashes,historical_code_drift=code_drift,common_config=common,initial_text_facts_and_action_criteria_match=True,openai_onejev_initial_visual_questions_match=True,identical_pairs=pairs,verified_image_requests=dict(image_calls),selection_policy='first GS batch 01 in each condition, independent of outcome; all 73 runs retained',api_calls=0,used_gpu=False))
(OUT/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
for filename,data in [('runs.csv',rows),('aggregate.csv',aggregates),('representatives.csv',representatives),('totals.csv',totals),('excluded.csv',prior['excluded'])]:
 with (OUT/filename).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
print('PASS',json.dumps(totals),all_actions,'actions; image requests',dict(image_calls),flush=True)
