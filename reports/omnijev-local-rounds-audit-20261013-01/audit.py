"""Read-only audit of 18 recorded OmniJev navigation runs; no GPU/API calls."""
from pathlib import Path
from collections import Counter
import csv,hashlib,io,json,math,sys,copy
import numpy as np
from PIL import Image

ROOT=Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav')
OUT=Path(sys.argv[1]);OUT.mkdir(parents=True,exist_ok=False)
sys.path.insert(0,str(ROOT))
from environment import load_pathfinder,shortest,ACTIONS
from depth_language import semantic_depth
from rgb_input import project_target
from omnijev import encode_local_request
from omnijev_server import prepare_native_request

ROUTES=['simple','complex','extended'];MODES=['numeric','semantic','none']
TASKS=dict(zip(ROUTES,['tasks/debug-10.json','tasks/challenge-clearance-aligned-20260930-01/tasks.json','tasks/extended-clearance-aligned-20261008-01/tasks.json']))
IDS=dict(zip(ROUTES,['episode-000','turn-000','extended-000']));BUDGETS=dict(zip(ROUTES,[100,250,500]))
hashes={};details={};sequences={};rows=[];timeline=[];pf=None
def protect(path):
    digest=hashlib.sha256(path.read_bytes()).hexdigest();hashes[str(path.relative_to(ROOT))]=digest;return digest
def near(a,b,tol=1e-6):assert abs(a-b)<=tol,(a,b)
def longest(items,predicate):
    best=cur=0;start=0;best_start=0
    for i,value in enumerate(items):
        if predicate(value):
            if cur==0:start=i
            cur+=1
            if cur>best:best=cur;best_start=start
        else:cur=0
    return {'length':best,'first_action':best_start+1 if best else None,'last_action':best_start+best if best else None}
for rel in ['environment.py','depth_language.py','rgb_input.py','omnijev.py','omnijev_server.py','run.py','core.py','jev.py','local_models/omnijev-4b/source/mso/infer.py','local_models/omnijev-4b/source/mso/records.py','local_models/omnijev-4b/source/mso/branch.py']:
    protect(ROOT/rel)
tasks={}
for route,path in TASKS.items():
    protect(ROOT/path);tasks[route]=next(t for t in json.loads((ROOT/path).read_text())['tasks'] if t['id']==IDS[route])
for route in ROUTES:
 for mode in MODES:
  for batch in ['01','02']:
    name=f'omnijev-local-rgbtarget-{route}-rgbgs-{mode}-local-round-{batch}';folder=ROOT/'runs'/name
    for filename in ['metadata.json','summary.json','steps.jsonl','navmap.png']:
        protect(folder/filename)
    m=json.loads((folder/'metadata.json').read_text());s=json.loads((folder/'summary.json').read_text())
    records=[json.loads(line) for line in (folder/'steps.jsonl').read_text().splitlines()]
    cfg,task=m['config'],m['task'];health=m['omnijev_service_health'];deployment=m['omnijev_deployment']
    assert m['provider']==s['provider']=='omnijev_local' and s['is_omnijev_evaluation']
    assert s['requested_model']=='tinnel123/OmniJev' and s['response_models']==['tinnel123/OmniJev']
    assert m['api_endpoint']=='http://127.0.0.1:8012/v1/systemone' and m['api_provider']=='local_mso1'
    assert health['model']=='tinnel123/OmniJev' and health['release']=='v1.1' and health['branch'] is True
    assert health['bridge_version']=='navigation_state_json_v1'
    assert health['bridge_source_sha256']==hashes['omnijev_server.py']
    assert health['deployment_sha256']==deployment['sha256']
    embedded_digest=hashlib.sha256((json.dumps(deployment['manifest'],indent=2)+'\n').encode()).hexdigest()
    assert embedded_digest==deployment['sha256']
    assert health['upstream_commit']=='5da4b5c4cd5cc2acb96d18beecbdf5972231ef1b'
    assert health['model_revision']=='ffe5f436eaf22e20e2f041f8e74e121fd057a6cb'
    assert health['base_revision']=='851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a'
    for rel,digest in deployment['manifest']['upstream_files'].items():assert protect(ROOT/'local_models/omnijev-4b/source'/rel)==digest
    assert m['rgb_mode']=='gs' and cfg['rgb_input']==m['rgb_input']==s['rgb_input']=='target_marked'
    assert m['rgb_provided_to_model'] and s['rgb_provided_to_model']
    assert m['depth_provided_to_model']==s['depth_provided_to_model']==(mode!='none')
    assert cfg['max_steps']==BUDGETS[route] and cfg['success_m']==.3
    assert cfg['move_m']==.25 and cfg['turn_deg']==15 and cfg['allow_sliding'] is True
    assert all(task[k]==tasks[route][k] for k in ['start','goal','path','yaw_deg','pitch_deg'])
    if pf is None:pf=load_pathfinder(dict(cfg))
    navmesh=Path(cfg['scene_dir'])/'shuyuan.navmesh'
    assert hashlib.sha256(navmesh.read_bytes()).hexdigest()==m['assets']['shuyuan.navmesh']['sha256']
    assert records[-1]['frame_kind']=='after_final_action' and records[-1]['request'] is None
    actions=records[:-1]
    assert len(actions)==s['steps'] and [r['step'] for r in records]==list(range(len(records)))
    near(math.dist(actions[0]['pose']['position'],task['start']),0)
    initial=shortest(pf,task['start'],task['goal'])[0];near(initial,s['initial_geodesic_m'])
    travel=0.;distances=[];latencies=[];cycles=[];counts=Counter();markers=Counter();projections=Counter()
    tokens=[];attempts=[];behind_forward=[];collided_moving=0;blocked_chosen=[];stop_prob=[];confidence=[];abstain_high=0
    post_collision_same=[];tgt_bearings=[];bearing_large_forward=[];turn_pairs=[];probvalid=[]
    sequence={k:[] for k in ['actions','poses','image_sha256','wire_sha256','prompt_sha256','probabilities','abstain','native_valid','confidence']}
    for i,r in enumerate(actions):
        req,dec,outcome=r['request'],r['decision'],r['outcome'];state=req['state'];response=dec['response'];native=response['answers']['action'];receipt=response['omnijev']
        assert req['model']==response['model']=='tinnel123/OmniJev'
        assert dec['choice']==native['choice']==outcome['action'] and dec['attempts']==1 and not dec['retry_errors']
        assert list(req['questions']['action']['criteria'])==m['available_actions']==list(ACTIONS)
        assert native['choice'] in native['probabilities']
        assert max(native['probabilities'].values())-native['probabilities'][native['choice']]<=.00011
        near(sum(native['probabilities'].values())+native['abstain'],1.,.001)
        assert math.dist(r['after_position'],records[i+1]['pose']['position'])<1e-6
        displacement=math.dist(r['pose']['position'],r['after_position']);travel+=displacement
        near(travel,r['metrics']['path_length_m'],1e-4);near(displacement,outcome['actual_translation_m'],.00051)
        distance=shortest(pf,r['after_position'],task['goal'])[0];near(distance,r['metrics']['distance_to_goal_geodesic_m']);distances.append(distance)
        if mode=='none':assert 'depth' not in state and 'depth_numeric_debug' not in r
        elif mode=='semantic':assert semantic_depth(r['depth_numeric_debug'])==state['depth']
        else:assert len(state['depth']['sectors'])==9
        im=r['image_input'];data=(folder/im['path']).read_bytes();digest=protect(folder/im['path'])
        assert digest==im['sha256'] and len(data)==im['bytes'] and im['mime_type']=='image/jpeg'
        assert r['images']['model_rgb']==im['path']
        with Image.open(io.BytesIO(data)) as image:
            assert image.format=='JPEG' and image.size==(640,480)==(im['width'],im['height']);image.verify()
        assert state['visual']['source']=='current_gs_rgb' and state['visual']['marker']==im['marker']
        projected=project_target(state['reference']['current_target'],r['pose']['pitch_deg'],cfg,im['marker']['target_height_above_agent_feet_m'])
        assert all(projected[k]==im['marker'][k] for k in projected)
        wire_bytes=encode_local_request(req,data);wire_digest=hashlib.sha256(wire_bytes).hexdigest()
        assert wire_digest==r['wire_request_sha256']==dec['request_body_sha256']
        image_data,image_hash,questions,prompt_hash=prepare_native_request(json.loads(wire_bytes))
        assert image_data==data and image_hash==receipt['input_image_sha256']==digest and receipt['images']==1
        assert receipt['adapted_questions_sha256']==prompt_hash and receipt['bridge_version']=='navigation_state_json_v1'
        assert json.loads(questions['action']['instructions'].split('\nNAVIGATION_STATE_JSON:\n')[1])==state
        assert response['usage']['input_tokens']>0 and response['usage']['output_tokens']==0
        counts[outcome['action']]+=1;markers[im['marker']['marker_kind']]+=1;projections[im['marker']['projection_status']]+=1
        latencies.append(dec['latency_s']);cycles.append(r['metrics']['cycle_s']);tokens.append(response['usage']['input_tokens']);attempts.append(dec['attempts'])
        target=state['reference']['current_target'];bearing=target['bearing_deg'];tgt_bearings.append(bearing)
        if outcome['action']=='move_forward' and abs(bearing)>90:behind_forward.append(i+1)
        if outcome['action']=='move_forward' and abs(bearing)>45:bearing_large_forward.append(i+1)
        if outcome['collided'] and displacement>1e-4:collided_moving+=1
        if i and actions[i-1]['outcome']['collided'] and outcome['action']==actions[i-1]['outcome']['action']:post_collision_same.append(i+1)
        if i and {outcome['action'],actions[i-1]['outcome']['action']}=={'turn_left','turn_right'}:turn_pairs.append(i+1)
        if 'depth' in state and state['depth'].get('move_checks',{}).get(outcome['action'],{}).get('status')=='blocked':blocked_chosen.append(i+1)
        stop_prob.append(native['probabilities']['stop']);confidence.append(native['confidence']);probvalid.append(native['valid'])
        if native['abstain']>max(native['probabilities'].values()):abstain_high+=1
        for key,value in [('actions',outcome['action']),('poses',[r['pose'],r['after_position']]),('image_sha256',digest),('wire_sha256',wire_digest),('prompt_sha256',prompt_hash),('probabilities',native['probabilities']),('abstain',native['abstain']),('native_valid',native['valid']),('confidence',native['confidence'])]:sequence[key].append(value)
        timeline.append(dict(run=name,route=route,depth_mode=mode,round=batch,action_step=i+1,action=outcome['action'],collided=outcome['collided'],valid=outcome['valid'],actual_translation_m=displacement,distance_after_m=distance,travel_m=travel,target_bearing_deg=bearing,target_distance_m=target['distance_m'],target_is_final=target['is_final'],tracking_progress_m=state['reference']['tracking']['progress_m'],camera_pitch_deg=r['pose']['pitch_deg'],projection_status=im['marker']['projection_status'],confidence=native['confidence'],chosen_probability=native['probabilities'][native['choice']],stop_probability=native['probabilities']['stop'],abstain=native['abstain'],image_path=im['path']))
    collisions=sum(r['outcome']['collided'] for r in actions);invalid=sum(not r['outcome']['valid'] for r in actions)
    success=actions[-1]['outcome']['action']=='stop' and distances[-1]<=.3
    assert s['success']==success and s['status']==('success' if success else 'early_stop' if counts['stop'] else 'action_budget')
    assert s['collisions']==collisions and s['invalid_actions']==invalid and s['collision_free_success']==(success and collisions==0)
    ever=min(initial,*distances)<=.3;assert s['ever_within_goal_tolerance']==ever and s['reached_but_not_successful_stop']==(ever and not success)
    near(travel,s['path_length_m'],1e-4);near(distances[-1],s['final_geodesic_m']);near(s['spl'],float(success)*initial/max(initial,travel),1e-6)
    for key,percentile in [('p50_s',50),('p95_s',95)]:
        near(float(np.percentile(latencies,percentile)),s['model_request_latency'][key]);near(float(np.percentile(cycles,percentile)),s['cycle_including_render_and_logging'][key])
    row=dict(run=name,route=route,depth_mode=mode,round=batch,success=success,status=s['status'],steps=len(actions),collisions=collisions,invalid_actions=invalid,path_length_m=travel,initial_geodesic_m=initial,final_geodesic_m=distances[-1],minimum_geodesic_m=min(initial,*distances),minimum_distance_action=(int(np.argmin([initial]+distances))),ever_within_goal_tolerance=ever,spl=s['spl'],verified_multimodal_requests=len(actions),request_latency_p50_s=float(np.percentile(latencies,50)),request_latency_p95_s=float(np.percentile(latencies,95)),cycle_p50_s=float(np.percentile(cycles,50)),cycle_p95_s=float(np.percentile(cycles,95)))
    rows.append(row);sequences[name]=sequence
    stationary=longest(actions,lambda r:math.dist(r['pose']['position'],r['after_position'])<1e-4)
    alternating=longest(list(enumerate(actions)),lambda ir:ir[0]>0 and {ir[1]['outcome']['action'],actions[ir[0]-1]['outcome']['action']}=={'turn_left','turn_right'})
    details[name]=dict(action_counts=dict(counts),marker_counts=dict(markers),projection_counts=dict(projections),max_consecutive_left=longest(actions,lambda r:r['outcome']['action']=='turn_left'),max_consecutive_right=longest(actions,lambda r:r['outcome']['action']=='turn_right'),max_stationary_actions=stationary,max_opposite_turn_transition_streak=alternating,opposite_turn_transitions=len(turn_pairs),forward_with_target_behind_steps=behind_forward,forward_with_target_abs_bearing_over45_steps=bearing_large_forward,repeat_same_action_after_collision_steps=post_collision_same,blocked_move_chosen_steps=blocked_chosen,collisions_with_displacement=collided_moving,collisions_without_displacement=collisions-collided_moving,input_tokens_min=min(tokens),input_tokens_max=max(tokens),total_attempts=sum(attempts),native_valid_false=sum(not x for x in probvalid),abstain_larger_than_all_actions=abstain_high,stop_probability_min=min(stop_prob),stop_probability_max=max(stop_prob),confidence_mean=float(np.mean(confidence)),service_health=health,deployment_sha256=deployment['sha256'],config=cfg,task=task,map=m['map'],reference_path_length_m=m['reference_path_length_m'],positions=[r['pose']['position'] for r in records],collision_positions=[r['after_position'] for r in actions if r['outcome']['collided']],invalid_positions=[r['after_position'] for r in actions if not r['outcome']['valid']])
    print(name,'verified',len(actions),'requests',flush=True)
pairs={}
for route in ROUTES:
 for mode in MODES:
    prefix=f'omnijev-local-rgbtarget-{route}-rgbgs-{mode}-local-round-';a,b=sequences[prefix+'01'],sequences[prefix+'02']
    pairs[f'{route}/{mode}']={k:a[k]==b[k] for k in a}
aggregates=[]
for route in ROUTES:
 for mode in MODES:
    selected=[r for r in rows if r['route']==route and r['depth_mode']==mode]
    entry=dict(route=route,depth_mode=mode,runs=2,successes=sum(r['success'] for r in selected),success_rate=sum(r['success'] for r in selected)/2)
    for key in ['steps','collisions','invalid_actions','path_length_m','initial_geodesic_m','final_geodesic_m','minimum_geodesic_m','request_latency_p50_s','request_latency_p95_s']:
        entry[key+'_mean']=sum(r[key] for r in selected)/2;entry[key+'_min']=min(r[key] for r in selected);entry[key+'_max']=max(r[key] for r in selected)
    aggregates.append(entry)
for filename,data in [('runs.csv',rows),('aggregate.csv',aggregates),('timeline.csv',timeline)]:
    with (OUT/filename).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
audit=dict(scope='18 saved OmniJev v1.1 local RGB+text runs; read-only CPU audit',verified_runs=len(rows),verified_multimodal_requests=sum(r['verified_multimodal_requests'] for r in rows),successes=sum(r['success'] for r in rows),round_pair_identity=pairs,details=details,source_hashes=hashes,checks=['fixed task, pose, action budget and action candidate order','official deployment revisions and unchanged pinned source','all saved JPEG bytes SHA256, resolution and format','rebuilt wire SHA256 equals recorder and client','rebuilt full native question SHA256 equals inference receipt; complete state preserved','one current image SHA256 matches each native inference receipt','depth presence and semantic transformation','all distances recomputed by CPU NavMesh shortest path','pose continuity, translation and cumulative travel recomputed','outcome collision/invalid counts, geodesic success and SPL recomputed','latency percentiles recomputed','all protected source files rehashed after audit'],GPU_used=False,API_calls=0)
for rel,digest in hashes.items():assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==digest,rel
(OUT/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'verified_runs':len(rows),'verified_multimodal_requests':audit['verified_multimodal_requests'],'successes':audit['successes'],'total_collisions':sum(r['collisions'] for r in rows),'round_pair_identity':pairs},indent=2))
