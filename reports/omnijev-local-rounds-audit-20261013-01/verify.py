"""Independent raw-record reconciliation and transport reconstruction."""
from pathlib import Path
from collections import Counter
import base64,csv,hashlib,json,math,sys
ROOT=Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav');OUT=Path(sys.argv[1])
rows=list(csv.DictReader((OUT/'runs.csv').open()));audit=json.loads((OUT/'audit.json').read_text())
global_actions=Counter();global_markers=Counter();global_projections=Counter();latencies=[];extras={};checks=0
for row in rows:
    run=ROOT/'runs'/row['run'];records=[json.loads(s) for s in (run/'steps.jsonl').read_text().splitlines()];actions=records[:-1]
    assert len(actions)==int(row['steps'])
    path=sum(math.sqrt(sum((b-a)**2 for a,b in zip(r['pose']['position'],r['after_position']))) for r in actions)
    assert abs(path-float(row['path_length_m']))<1e-6
    assert sum(bool(r['outcome']['collided']) for r in actions)==int(row['collisions'])
    assert sum(r['outcome']['valid'] is False for r in actions)==int(row['invalid_actions'])
    assert min([float(row['initial_geodesic_m'])]+[r['metrics']['distance_to_goal_geodesic_m'] for r in actions])==float(row['minimum_geodesic_m'])
    assert actions[-1]['outcome']['action']!='stop' and row['success']=='False'
    examples=[]
    for r in actions:
        image=(run/r['image_input']['path']).read_bytes();req=r['request']
        wire=dict(req,image_data_url='data:image/jpeg;base64,'+base64.b64encode(image).decode('ascii'),image_sha256=hashlib.sha256(image).hexdigest())
        digest=hashlib.sha256(json.dumps(wire,allow_nan=False).encode()).hexdigest()
        assert digest==r['wire_request_sha256']==r['decision']['request_body_sha256']
        native=json.loads(json.dumps(req['questions']))
        native['action']['instructions']+='\nNAVIGATION_STATE_JSON:\n'+json.dumps(req['state'],allow_nan=False)
        native_digest=hashlib.sha256(json.dumps(native,allow_nan=False).encode()).hexdigest()
        assert native_digest==r['decision']['response']['omnijev']['adapted_questions_sha256']
        assert wire['image_sha256']==r['decision']['response']['omnijev']['input_image_sha256']
        outcome=r['outcome'];p=r['decision']['response']['answers']['action']
        global_actions[outcome['action']]+=1;global_markers[r['image_input']['marker']['marker_kind']]+=1;global_projections[r['image_input']['marker']['projection_status']]+=1
        latencies.append(r['decision']['latency_s']);checks+=1
    nearest=min(actions,key=lambda r:r['metrics']['distance_to_goal_geodesic_m'])
    selection={0,min(19,len(actions)-1),nearest['step'],len(actions)-1}
    behind=next((r['step'] for r in actions if r['outcome']['action']=='move_forward' and abs(r['request']['state']['reference']['current_target']['bearing_deg'])>90),None)
    if behind is not None:selection.add(behind)
    detail=audit['details'][row['run']]
    stationary=detail['max_stationary_actions']['first_action']
    if stationary:selection.add(stationary-1)
    for index in sorted(selection):
        r=actions[index];state=r['request']['state'];p=r['decision']['response']['answers']['action']
        examples.append({'action_step':index+1,'action':r['outcome']['action'],'before_position':r['pose']['position'],'after_position':r['after_position'],'collided':r['outcome']['collided'],'current_target':state['reference']['current_target'],'final_goal':state['reference']['final_goal'],'reference_progress_m':state['reference']['tracking']['progress_m'],'geodesic_after_m':r['metrics']['distance_to_goal_geodesic_m'],'recent_motion':state['recent_motion'],'probabilities':p['probabilities'],'confidence':p['confidence'],'frame':r['image_input']['path']})
    extras[row['run']]={'diagnostic_examples':examples,'peak_allocated_bytes_max':max(r['decision']['response']['omnijev']['peak_allocated_bytes'] for r in actions),'native_latency_min_s':min(r['decision']['response']['omnijev']['native_inference_s'] for r in actions),'native_latency_max_s':max(r['decision']['response']['omnijev']['native_inference_s'] for r in actions)}
assert len(rows)==18 and checks==5100
result={'status':'PASS','independent_raw_metric_runs':len(rows),'independent_wire_and_native_question_checks':checks,'global_actions':dict(global_actions),'global_markers':dict(global_markers),'global_projections':dict(global_projections),'total_collisions':sum(int(r['collisions']) for r in rows),'total_invalid_actions':sum(int(r['invalid_actions']) for r in rows),'total_path_length_m':sum(float(r['path_length_m']) for r in rows),'details':extras,'GPU_used':False,'API_calls':0}
for rel,digest in audit['source_hashes'].items():assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==digest,rel
(OUT/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='details'},indent=2))
