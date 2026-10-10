"""Read-only native NavMesh and multimodal-wire audit; no renderer/API calls."""
from pathlib import Path
from collections import Counter
import copy, csv, hashlib, io, json, math, sys
from PIL import Image
import numpy as np
ROOT = Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav')
OUT = Path(sys.argv[1]) if len(sys.argv)>1 else Path('/tmp/openai-rgb-ablation-audit-20261010-01')
OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT))
from environment import load_pathfinder, shortest
from jev import make_request, encode_request
from depth_language import semantic_depth
from rgb_input import project_target
ROUTES=['simple','complex','extended']; MODES=['numeric','semantic','none']; BATCHES=['01','02']
TASKS={'simple':'tasks/debug-10.json','complex':'tasks/challenge-clearance-aligned-20260930-01/tasks.json','extended':'tasks/extended-clearance-aligned-20261008-01/tasks.json'}
IDS=dict(zip(ROUTES,['episode-000','turn-000','extended-000']))
BUDGETS=dict(zip(ROUTES,[100,250,500])); hashes={}
def protect(path):
    rel=str(path.relative_to(ROOT)); digest=hashlib.sha256(path.read_bytes()).hexdigest(); hashes[rel]=digest; return digest
def near(a,b,tol=1e-6): assert abs(a-b)<=tol,(a,b)
def pct(values): return dict(p50_s=float(np.percentile(values,50)),p95_s=float(np.percentile(values,95)))
base_audit=ROOT/'reports/openai-ablation-audit-20261009-01/audit.json'
protect(base_audit)
old_audit=json.loads(base_audit.read_text())
# Historical audit hashes establish that the selected baseline evidence stayed intact.
prior_hashes=old_audit['verification']['source_hashes']
for path,digest in prior_hashes.items():
    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest, ('changed historical baseline',path)
for name in ['environment.py','jev.py','rgb_input.py','core.py','run.py','depth_language.py']:
    protect(ROOT/name)
base_tasks={}
for route,path in TASKS.items():
    protect(ROOT/path)
    base_tasks[route]=next(t for t in json.loads((ROOT/path).read_text())['tasks'] if t['id']==IDS[route])
rows=[]; details={}; recs={}; raw_records={}; ids={'rgb':[],'text':[]}; pf=None
for arm in ['text','rgb']:
 for route in ROUTES:
  for mode in MODES:
   for batch in BATCHES:
    name=f"openai-decisions-{'rgbtarget-' if arm=='rgb' else ''}{route}-rgbgs-{mode}-20261009-{batch}"
    folder=ROOT/'runs'/name
    for filename in ['metadata.json','summary.json','steps.jsonl']: protect(folder/filename)
    m=json.loads((folder/'metadata.json').read_text()); s=json.loads((folder/'summary.json').read_text()); cfg=m['config']; task=m['task']
    assert m['provider']==s['provider']=='openai_decisions'
    assert s['is_openai_decisions_evaluation'] and not s['is_jev_evaluation']
    assert s['response_models']==['openai/gpt-6-luna-decisions-20261006']
    assert m['rgb_mode']=='gs' and bool(m['rgb_provided_to_model'])==(arm=='rgb')
    assert (m['depth_input']=='none' and mode=='none') or m['depth_format']==mode
    assert cfg['max_steps']==BUDGETS[route] and cfg['success_m']==.3
    assert all(task[k]==base_tasks[route][k] for k in ['start','goal','path','yaw_deg','pitch_deg'])
    if pf is None: pf=load_pathfinder(dict(cfg))
    assert hashlib.sha256((Path(cfg['scene_dir'])/'shuyuan.navmesh').read_bytes()).hexdigest()==m['assets']['shuyuan.navmesh']['sha256']
    records=[json.loads(l) for l in (folder/'steps.jsonl').read_text().splitlines()]
    actions=records[:-1]
    assert records[-1]['frame_kind']=='after_final_action' and records[-1]['request'] is None
    assert len(actions)==s['steps'] and [r['step'] for r in records]==list(range(len(records)))
    initial=shortest(pf,task['start'],task['goal'])[0]; near(initial,s['initial_geodesic_m'])
    ds=[]; travel=0.; latencies=[]; cycles=[]; markers=Counter(); image_bytes=[]; image_digests=[]; costs=[]
    for i,r in enumerate(actions):
        req,dec,outcome=r['request'],r['decision'],r['outcome']; state=req['state']
        assert dec['choice']==outcome['action']==dec['response']['answers']['action']['choice']
        assert outcome['action'] in req['questions']['action']['criteria']
        assert req['model']==cfg['model']=='openai/gpt-6-luna-decisions'
        assert dec['response']['model']==s['response_models'][0]
        assert math.dist(r['after_position'],records[i+1]['pose']['position'])<1e-6
        d=shortest(pf,r['after_position'],task['goal'])[0]; near(d,r['metrics']['distance_to_goal_geodesic_m']); ds.append(d)
        travel+=math.dist(r['pose']['position'],r['after_position']); near(travel,r['metrics']['path_length_m'],1e-4)
        if mode=='none': assert 'depth' not in state and 'depth_numeric_debug' not in r
        elif mode=='semantic': assert semantic_depth(r['depth_numeric_debug'])==state['depth']
        else: assert len(state['depth']['sectors'])==9
        if arm=='rgb':
            assert cfg['rgb_input']=='target_marked' and m['request_representation']=='readable_text_state_plus_image_manifest'
            im=r['image_input']; path=folder/im['path']; b=path.read_bytes(); digest=protect(path)
            assert digest==im['sha256'] and len(b)==im['bytes']
            with Image.open(io.BytesIO(b)) as image:
                assert image.format=='JPEG' and image.size==(im['width'],im['height'])==(cfg['resolution'][1],cfg['resolution'][0])
                image.verify()
            assert r['images']['model_rgb']==im['path'] and im['mime_type']=='image/jpeg'
            assert state['visual']['marker']==im['marker'] and state['visual']['source']=='current_gs_rgb'
            target=state['reference']['current_target']
            projection=project_target(target,r['pose']['pitch_deg'],cfg,im['marker']['target_height_above_agent_feet_m'])
            assert all(projection[k]==im['marker'][k] for k in projection)
            wire=encode_request(req,b)
            assert hashlib.sha256(wire).hexdigest()==r['wire_request_sha256']==dec['request_body_sha256']
            markers[im['marker']['projection_status']]+=1; image_bytes.append(len(b)); image_digests.append(digest)
        else:
            assert 'visual' not in state and 'image_input' not in r
            assert 'No depth or image' in req['questions']['action']['instructions'] if mode=='none' else True
        rebuilt_state=copy.deepcopy(state)
        if mode=='semantic': rebuilt_state['depth']=r['depth_numeric_debug']
        assert make_request(rebuilt_state,cfg)==req, ('prompt or transformations drift',name,i)
        ids[arm].append(dec['response']['id']); latencies.append(dec['latency_s']); cycles.append(r['metrics']['cycle_s'])
        costs.append(dec['response'].get('usage',{}).get('cost',0.))
    collisions=sum(r['outcome']['collided'] for r in actions); invalid=sum(not r['outcome']['valid'] for r in actions)
    success=actions[-1]['outcome']['action']=='stop' and ds[-1]<=.3
    status='success' if success else 'early_stop' if actions[-1]['outcome']['action']=='stop' else 'action_budget'
    assert s['status']==status and s['success']==success and s['collision_free_success']==(success and collisions==0)
    assert s['collisions']==collisions and s['invalid_actions']==invalid
    assert s['ever_within_goal_tolerance']==(min([initial,*ds])<=.3)
    near(travel,s['path_length_m'],1e-4); near(ds[-1],s['final_geodesic_m'])
    spl=initial/max(initial,travel) if success else 0.; near(spl,s['spl'])
    for key,val in pct(latencies).items(): near(val,s['model_request_latency'][key])
    for key,val in pct(cycles).items(): near(val,s['cycle_including_render_and_logging'][key])
    counts=Counter(r['outcome']['action'] for r in actions)
    stationary_max=stationary=0
    for r in actions:
        stationary=stationary+1 if math.dist(r['pose']['position'],r['after_position'])<1e-4 and r['outcome']['action']!='stop' else 0
        stationary_max=max(stationary_max,stationary)
    first_reached=next((i+1 for i,d in enumerate(ds) if d<=.3),None)
    if arm=='rgb':
        assert success and first_reached==len(actions)-1
        assert actions[-1]['request']['state']['reference']['current_target']['is_final']
        assert actions[-1]['request']['state']['reference']['final_goal']['distance_m']<=.3
    collision_events=[{'action_number':i+1,'action':r['outcome']['action'],'position_before':r['pose']['position'],'position_after':r['after_position'],'outcome':r['outcome'],'target':r['request']['state']['reference']['current_target'],'distance_after_m':ds[i]} for i,r in enumerate(actions) if r['outcome']['collided']]
    invalid_events=[{'action_number':i+1,'action':r['outcome']['action'],'pitch_deg':r['pose']['pitch_deg'],'result':r['outcome']['result']} for i,r in enumerate(actions) if not r['outcome']['valid']]
    row={'arm':arm,'route':route,'input':mode,'batch':batch,'run':name,**{k:s[k] for k in ['status','success','collision_free_success','steps','collisions','invalid_actions','path_length_m','initial_geodesic_m','final_geodesic_m','spl']},'reference_path_length_m':m['reference_path_length_m'],'first_within_goal_action':first_reached,'actions_after_first_arrival':len(actions)-first_reached if first_reached else None,'model_latency_p50_s':pct(latencies)['p50_s'],'model_latency_p95_s':pct(latencies)['p95_s'],'cycle_p50_s':pct(cycles)['p50_s'],'cycle_p95_s':pct(cycles)['p95_s'],'total_request_latency_s':sum(latencies),'elapsed_s':s['elapsed_s'],'cost_usd':sum(costs),'stationary_action_fraction':(counts['turn_left']+counts['turn_right']+counts['look_down']+counts['look_up'])/len(actions)}
    rows.append(row)
    details[name]={'action_counts':dict(counts),'marker_projection_counts':dict(markers),'pitch_counts':dict(Counter(r['pose']['pitch_deg'] for r in actions)),'maximum_stationary_streak':stationary_max,'collision_events':collision_events,'invalid_events':invalid_events,'distance_series_m':[initial,*ds],'positions':[r['pose']['position'] for r in records],'created_unix':m['created_unix'],'minimum_geodesic_m':min(ds),'minimum_at_action':ds.index(min(ds))+1,'last_reference':actions[-1]['request']['state']['reference'],'image_sizes_bytes':{'mean':float(np.mean(image_bytes)),'min':min(image_bytes),'max':max(image_bytes)} if image_bytes else None,'left_turns_when_target_on_right':sum(r['outcome']['action']=='turn_left' and r['request']['state']['reference']['current_target']['bearing_deg'] < -1 for r in actions)}
    recs[arm,route,mode,batch]=[{'pose':r['pose'],'request':r['request'],'outcome':r['outcome'],'after_position':r.get('after_position'),'distance':r['metrics']['distance_to_goal_geodesic_m'],'image_sha256':r.get('image_input',{}).get('sha256')} for r in records]
    raw_records[arm,route,mode,batch]=(m,records)
    print('VERIFIED',arm,route,mode,batch,len(actions),flush=True)
pairs=[]; comparison=[]
for route in ROUTES:
 for mode in MODES:
    for arm in ['text','rgb']:
        a,b=recs[arm,route,mode,'01'],recs[arm,route,mode,'02']
        ra,rb=raw_records[arm,route,mode,'01'][1],raw_records[arm,route,mode,'02'][1]
        ids_a={r['decision']['response']['id'] for r in ra[:-1]}; ids_b={r['decision']['response']['id'] for r in rb[:-1]}
        pairs.append({'arm':arm,'route':route,'input':mode,'requests_poses_actions_distances_and_image_hashes_identical':a==b,'probabilities_identical':all(x['decision']['response']['answers']==y['decision']['response']['answers'] for x,y in zip(ra[:-1],rb[:-1])),'response_ids_disjoint':not bool(ids_a&ids_b)})
    ma,ra=raw_records['text',route,mode,'01']; mb,rb=raw_records['rgb',route,mode,'01']
    cfg_a,cfg_b=dict(ma['config']),dict(mb['config']);cfg_b.pop('rgb_input');assert cfg_a==cfg_b
    assert ma['task']==mb['task'] and ma['available_actions']==mb['available_actions']
    sa,sb=ra[0]['request']['state'],dict(rb[0]['request']['state']);sb.pop('visual');assert sa==sb
    assert ra[0]['request']['questions']['action']['criteria']==rb[0]['request']['questions']['action']['criteria']
    ar=[r for r in rows if r['arm']=='text' and r['route']==route and r['input']==mode]; br=[r for r in rows if r['arm']=='rgb' and r['route']==route and r['input']==mode]
    item={'route':route,'input':mode,'text_successes':sum(r['success'] for r in ar),'rgb_successes':sum(r['success'] for r in br),'text_collision_free_successes':sum(r['collision_free_success'] for r in ar),'rgb_collision_free_successes':sum(r['collision_free_success'] for r in br)}
    for field in ['steps','collisions','invalid_actions','path_length_m','final_geodesic_m','spl','model_latency_p50_s','elapsed_s']:
        item['text_mean_'+field]=float(np.mean([r[field] for r in ar]));item['rgb_mean_'+field]=float(np.mean([r[field] for r in br]));item['delta_'+field]=item['rgb_mean_'+field]-item['text_mean_'+field]
    comparison.append(item)
assert len(rows)==36
for arm in ids: assert len(ids[arm])==len(set(ids[arm]))
assert set(ids['rgb']).isdisjoint(ids['text'])
assert hashes=={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in hashes}
assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==digest for p,digest in prior_hashes.items())
totals={}
for arm in ['text','rgb']:
    group=[r for r in rows if r['arm']==arm]
    totals[arm]={'runs':len(group),**{field:sum(r[field] for r in group) for field in ['success','collision_free_success','steps','collisions','invalid_actions','cost_usd']},'unique_response_ids':len(set(ids[arm])),'sum_path_length_m':sum(r['path_length_m'] for r in group),'sum_request_latency_s':sum(r['total_request_latency_s'] for r in group)}
aggregate=[]
for arm in ['text','rgb']:
 for dimension,values in [('route',ROUTES),('input',MODES)]:
  for value in values:
   group=[r for r in rows if r['arm']==arm and r[dimension]==value]
   aggregate.append({'arm':arm,'dimension':dimension,'value':value,'runs':len(group),'successes':sum(r['success'] for r in group),'collision_free_successes':sum(r['collision_free_success'] for r in group),'steps':sum(r['steps'] for r in group),'collisions':sum(r['collisions'] for r in group),'invalid_actions':sum(r['invalid_actions'] for r in group)})
result={'totals':totals,'rows':rows,'comparison':comparison,'aggregate':aggregate,'pairs':pairs,'details':details,'verification':{'source_sha256':hashes,'protected_files':len(hashes),'verified_image_and_wire_hashes':len(ids['rgb']),'jpeg_format_and_resolution_verified':len(ids['rgb']),'historical_baseline_hashes_unchanged':len(prior_hashes),'navmesh_sha256':hashlib.sha256((Path(cfg['scene_dir'])/'shuyuan.navmesh').read_bytes()).hexdigest(),'navmesh_recomputed_actions':sum(len(x) for x in ids.values()),'api_calls':0,'rerendered':False,'inputs_not_changed':True,'comparison_caveat':'RGB + marker + matching visual prompt are a joint treatment, with only one fixed task per route class and repeated identical trajectories.'}}
(OUT/'audit.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
def writecsv(name,data):
 with (OUT/name).open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
writecsv('runs.csv',rows);writecsv('comparison.csv',comparison);writecsv('aggregate.csv',aggregate)
print('PASS',json.dumps(totals), 'protected files',len(hashes))
