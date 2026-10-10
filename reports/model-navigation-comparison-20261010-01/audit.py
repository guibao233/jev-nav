"""Audit all fixed-policy comparable Jev/OpenAI runs. CPU only; no API/rendering."""
from pathlib import Path
from collections import Counter
import copy,csv,hashlib,json,math,sys
import numpy as np
ROOT=Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav')
OUT=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/tmp/model-navigation-comparison-20261010-01')
OUT.mkdir(parents=True,exist_ok=True);sys.path.insert(0,str(ROOT))
from environment import load_pathfinder,shortest
from jev import make_request
from depth_language import semantic_depth
ROUTES=['simple','complex','extended'];MODES=['numeric','semantic','none'];SCHEMES=['jev','openai_text','openai_rgb']
prior_paths=['reports/route-ablation-summary-20261008-01/summary.json','reports/openai-rgb-ablation-audit-20261010-01/audit.json']
hashes={};prior_hashes={}
def protect(p):
    h=hashlib.sha256(p.read_bytes()).hexdigest();hashes[str(p.relative_to(ROOT))]=h;return h
for name in prior_paths:
 protect(ROOT/name);j=json.loads((ROOT/name).read_text());v=j['verification'];prior_hashes.update(v.get('hashes',v.get('source_sha256',{})))
assert all(hashlib.sha256((ROOT/k).read_bytes()).hexdigest()==v for k,v in prior_hashes.items())
prior_jev=json.loads((ROOT/prior_paths[0]).read_text())
prior_openai=json.loads((ROOT/prior_paths[1]).read_text())
expected={r['run'] for r in [*prior_jev['rows'],*prior_openai['rows']]}
common={k:v for k,v in prior_jev['common_config'].items() if k!='model'}
TASKS={'simple':'tasks/debug-10.json','complex':'tasks/challenge-clearance-aligned-20260930-01/tasks.json','extended':'tasks/extended-clearance-aligned-20261008-01/tasks.json'}
IDS=dict(zip(ROUTES,['episode-000','turn-000','extended-000']));BUDGETS=dict(zip(ROUTES,[100,250,500]))
base={}
for route,name in TASKS.items():
 protect(ROOT/name);base[route]=next(t for t in json.loads((ROOT/name).read_text())['tasks'] if t['id']==IDS[route])
selected=[];excluded=[]
for p in sorted((ROOT/'runs').iterdir()):
 if not (p/'metadata.json').is_file() or not (p/'summary.json').is_file():continue
 m=json.loads((p/'metadata.json').read_text());s=json.loads((p/'summary.json').read_text())
 if not (s.get('is_jev_evaluation') or s.get('is_openai_decisions_evaluation')):continue
 t=m.get('task',{});route=next((k for k,v in base.items() if t.get('id')==v['id']),None)
 reason=None
 if route is None:reason='other_task'
 elif not m.get('prompt_version','').startswith('seven_actions_reassociate_motion_v5'):reason='different_policy_generation'
 elif any(t.get(k)!=base[route][k] for k in ['start','goal','path','yaw_deg','pitch_deg']):reason='different_task_pose_or_path'
 elif m['config']['max_steps']!=BUDGETS[route]:reason='different_budget'
 elif s['status'] not in ['success','early_stop','action_budget']:reason='incomplete_run'
 elif {k:v for k,v in m['config'].items() if k not in ['gpu_id','depth_input','depth_format','max_steps','model','rgb_input']}!=common:reason='different_common_config'
 if reason:excluded.append({'run':p.name,'reason':reason});continue
 scheme='jev' if s.get('is_jev_evaluation') else 'openai_rgb' if m.get('rgb_provided_to_model') else 'openai_text'
 mode='none' if m.get('depth_input',m['config'].get('depth_input','mesh'))=='none' else m.get('depth_format','numeric')
 selected.append((p,m,s,route,mode,scheme))
assert {p.name for p,*_ in selected}==expected
rows=[];details={};first_requests={};response_ids=[];pf=None;metadata_by_run={}
for p,m,s,route,mode,scheme in selected:
 cfg=m['config'];task=m['task'];records=[json.loads(l) for l in (p/'steps.jsonl').read_text().splitlines()]
 for filename in ['metadata.json','summary.json','steps.jsonl']:protect(p/filename)
 a=records[:-1];assert len(a)==s['steps'] and len(records)==len(a)+1
 assert [r['step'] for r in records]==list(range(len(records)))
 assert records[-1]['request'] is None and records[-1]['frame_kind']=='after_final_action'
 if pf is None:pf=load_pathfinder(dict(cfg))
 initial=shortest(pf,task['start'],task['goal'])[0];assert abs(initial-s['initial_geodesic_m'])<1e-6
 assert set(m['available_actions'])=={'move_forward','move_backward','turn_left','turn_right','look_up','look_down','stop'}
 ds=[];travel=0.;latencies=[];cycles=[]
 for i,r in enumerate(a):
  req,dec,o=r['request'],r['decision'],r['outcome'];state=req['state']
  assert dec['choice']==o['action']==dec['response']['answers']['action']['choice']
  assert o['action'] in req['questions']['action']['criteria']
  version='typesafe/jev-1.13-20260917' if scheme=='jev' else 'openai/gpt-6-luna-decisions-20261006'
  assert dec['response']['model']==version
  response_ids.append(dec['response']['id'])
  d=shortest(pf,r['after_position'],task['goal'])[0];assert abs(d-r['metrics']['distance_to_goal_geodesic_m'])<1e-6;ds.append(d)
  travel+=math.dist(r['pose']['position'],r['after_position']);assert abs(travel-r['metrics']['path_length_m'])<1e-4
  assert math.dist(r['after_position'],records[i+1]['pose']['position'])<1e-6
  if mode=='none':assert 'depth' not in state
  elif mode=='semantic':assert semantic_depth(r['depth_numeric_debug'])==state['depth']
  else:assert len(state['depth']['sectors'])==9
  if scheme=='openai_rgb':assert 'visual' in state and r['image_input']['path']==r['images']['model_rgb'] and r['wire_request_sha256']==dec['request_body_sha256']
  else:assert 'visual' not in state and 'image_input' not in r and not any(t in json.dumps(req) for t in ['image_url','data:image/'])
  logical=copy.deepcopy(state)
  if mode=='semantic':logical['depth']=r['depth_numeric_debug']
  assert make_request(logical,cfg)==req
  latencies.append(dec['latency_s']);cycles.append(r['metrics']['cycle_s'])
 success=a[-1]['outcome']['action']=='stop' and ds[-1]<=cfg['success_m']
 status='success' if success else 'early_stop' if a[-1]['outcome']['action']=='stop' else 'action_budget'
 collisions=sum(r['outcome']['collided'] for r in a);invalid=sum(not r['outcome']['valid'] for r in a)
 assert s['success']==success and s['status']==status
 assert s['collision_free_success']==(success and collisions==0)
 assert s['collisions']==collisions and s['invalid_actions']==invalid
 assert abs(travel-s['path_length_m'])<1e-4 and abs(ds[-1]-s['final_geodesic_m'])<1e-6
 assert abs(s['spl']-(initial/max(initial,travel) if success else 0.))<1e-6
 counts=Counter(r['outcome']['action'] for r in a)
 first_reached=next((i+1 for i,d in enumerate(ds) if d<=.3),None)
 row={'scheme':scheme,'route':route,'input':mode,'run':p.name,'batch':next((x['batch'] for x in prior_jev['rows'] if x['run']==p.name),p.name[-2:]),'rgb_replay':m['rgb_mode'],**{k:s[k] for k in ['status','success','collision_free_success','steps','collisions','invalid_actions','path_length_m','final_geodesic_m','initial_geodesic_m','spl']},'minimum_geodesic_m':min(ds),'reference_path_length_m':m['reference_path_length_m'],'first_within_goal_action':first_reached,'actions_after_first_arrival':len(a)-first_reached if first_reached else None,'turn_actions':counts['turn_left']+counts['turn_right'],'pitch_actions':counts['look_up']+counts['look_down'],'translation_attempts':counts['move_forward']+counts['move_backward'],'model_latency_p50_s':float(np.percentile(latencies,50)),'model_latency_p95_s':float(np.percentile(latencies,95)),'elapsed_s':s['elapsed_s']}
 rows.append(row)
 positions=[r['pose']['position'] for r in records];assert positions[-1]==a[-1]['after_position']
 turn_spans=[];start=None
 for i,r in enumerate(a):
  stationary=math.dist(r['pose']['position'],r['after_position'])<1e-4 and r['outcome']['action']!='stop'
  if stationary and start is None:start=i
  elif not stationary and start is not None:turn_spans.append({'first_action':start+1,'last_action':i,'count':i-start,'position':a[start]['pose']['position']});start=None
 if start is not None:turn_spans.append({'first_action':start+1,'last_action':len(a),'count':len(a)-start,'position':a[start]['pose']['position']})
 details[p.name]={'positions':positions,'distance_series_m':[initial,*ds],'action_counts':dict(counts),'collision_positions':[r['after_position'] for r in a if r['outcome']['collided']],'invalid_positions':[r['pose']['position'] for r in a if not r['outcome']['valid']],'longest_stationary_span':max(turn_spans,key=lambda x:x['count']) if turn_spans else None,'response_model':version,'final_reference':a[-1]['request']['state']['reference'],'map':m['map'],'task':task}
 clean_first=copy.deepcopy(a[0]['request']);clean_first.pop('model');clean_first['state'].pop('visual',None)
 # Initial text facts identical; RGB instructions are an intentional treatment.
 key=(route,mode)
 if key not in first_requests:first_requests[key]=clean_first
 else:
  assert clean_first['state']==first_requests[key]['state']
  assert clean_first['questions']['action']['criteria']==first_requests[key]['questions']['action']['criteria']
  if scheme!='openai_rgb':assert clean_first['questions']==first_requests[key]['questions']
 metadata_by_run[p.name]=m
 print('VERIFIED',scheme,route,mode,p.name,len(a),flush=True)
rows.sort(key=lambda r:(ROUTES.index(r['route']),MODES.index(r['input']),SCHEMES.index(r['scheme']),r['run']))
aggregates=[];representatives=[]
for route in ROUTES:
 for mode in MODES:
  for scheme in SCHEMES:
   group=[r for r in rows if (r['route'],r['input'],r['scheme'])==(route,mode,scheme)]
   assert group
   g={'scheme':scheme,'route':route,'input':mode,'runs':len(group),'successes':sum(r['success'] for r in group),'collision_free_successes':sum(r['collision_free_success'] for r in group),'total_steps':sum(r['steps'] for r in group),'total_collisions':sum(r['collisions'] for r in group),'total_invalid_actions':sum(r['invalid_actions'] for r in group),'success_rate':sum(r['success'] for r in group)/len(group)}
   for field in ['steps','collisions','invalid_actions','path_length_m','final_geodesic_m','spl']:
    vals=[r[field] for r in group];g['mean_'+field]=float(np.mean(vals));g['min_'+field]=min(vals);g['max_'+field]=max(vals)
   aggregates.append(g)
   # Outcome-blind deterministic choice: first GS batch, fallback oldest recorded creation time.
   gs01=[r for r in group if '-rgbgs-' in r['run'] and r['run'].endswith('-01')]
   assert len(gs01)==1,(scheme,route,mode,gs01)
   rep=dict(gs01[0],selection='first_GS_batch_01_not_selected_by_outcome')
   representatives.append(rep);protect(ROOT/'runs'/rep['run']/'navmap.png')
totals=[]
for scheme in SCHEMES:
 group=[r for r in rows if r['scheme']==scheme];agg=[r for r in aggregates if r['scheme']==scheme]
 totals.append({'scheme':scheme,'runs':len(group),'successes':sum(r['success'] for r in group),'collision_free_successes':sum(r['collision_free_success'] for r in group),'steps':sum(r['steps'] for r in group),'collisions':sum(r['collisions'] for r in group),'invalid_actions':sum(r['invalid_actions'] for r in group),'macro_success_rate_equal_conditions':float(np.mean([r['success_rate'] for r in agg]))})
assert len(rows)==55 and len(representatives)==27 and sum(r['steps'] for r in rows)==10160
assert len(response_ids)==len(set(response_ids))==10160
assert all(hashlib.sha256((ROOT/k).read_bytes()).hexdigest()==v for k,v in hashes.items())
assert all(hashlib.sha256((ROOT/k).read_bytes()).hexdigest()==v for k,v in prior_hashes.items())
result={'scope':'same fixed routes and seven-action v5 policy; all completed comparable runs including failures','rows':rows,'aggregate':aggregates,'representatives':representatives,'totals':totals,'details':details,'excluded':excluded,'verification':{'runs':len(rows),'actions_recomputed':10160,'source_sha256':hashes,'prior_source_files_unchanged':len(prior_hashes),'prior_source_hashes':prior_hashes,'initial_text_state_and_action_criteria_match':True,'selection_policy':'first GS batch 01 in each condition, independent of success; OpenAI pairs are identical; Jev repeats remain in full metrics','api_calls':0,'used_gpu':False}}
(OUT/'audit.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
for filename,data in [('runs.csv',rows),('aggregate.csv',aggregates),('representatives.csv',representatives),('totals.csv',totals),('excluded.csv',excluded)]:
 with (OUT/filename).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
print('PASS',json.dumps(totals),'protected current',len(hashes),'prior',len(prior_hashes),flush=True)
