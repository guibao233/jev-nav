from pathlib import Path
import json,hashlib,sys,time
from PIL import Image
import torch
from transformers import AutoProcessor
root=Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav');stage=root;deploy=root/'local_models/omnijev-4b'
sys.path.insert(0,str(stage));sys.path.insert(0,str(deploy/'source'))
from omnijev_server import prepare_native_request
from jev import encode_request
from mso.infer import MSO1
from mso.records import Collator
proc=AutoProcessor.from_pretrained(deploy/'adapter',local_files_only=True,max_pixels=768*28*28)
native=MSO1.__new__(MSO1);native.dev=torch.device('cpu');native.dtype=torch.float32;native.proc=proc;native.coll=Collator(proc,768*28*28);native.pad_tok='<|image_pad|>';native._cache={};native._cache_n=1
rows=[]
for route in ['simple','complex','extended']:
 for mode in ['numeric','semantic','none']:
  run=root/'runs'/f'openai-decisions-rgbtarget-{route}-rgbgs-{mode}-20261009-01'
  meta=json.loads((run/'metadata.json').read_text());records=[json.loads(l) for l in (run/'steps.jsonl').read_text().splitlines()];live=[r for r in records if r.get('request')]
  selected={live[0]['step']:live[0],live[-1]['step']:live[-1],max(live,key=lambda r:len(json.dumps(r['request'])))['step']:max(live,key=lambda r:len(json.dumps(r['request'])))}
  for index,r in selected.items():
   image=run/r['image_input']['path'];image_bytes=image.read_bytes();assert hashlib.sha256(image_bytes).hexdigest()==r['image_input']['sha256']
   wire=json.loads(encode_request(dict(r['request'],model='tinnel123/OmniJev'),image_bytes))
   data,digest,questions,prompt_hash=prepare_native_request(wire)
   assert data==image_bytes and list(questions['action']['criteria'])==list(r['request']['questions']['action']['criteria'])
   state=json.loads(questions['action']['instructions'].split('\nNAVIGATION_STATE_JSON:\n')[1]);assert state==r['request']['state']
   keys,opts,ids,spans,pix=native._encode_many(str(image),None,questions,['action'])
   assert len(keys[0])==7 and len(spans[0][0])==7 and len(spans[0][1])==7
   assert 'pixel_values' in pix and pix['pixel_values'].numel()>0
   row={'route':route,'mode':mode,'source_run':run.name,'step':index,'image_sha256':digest,'wire_request_sha256':hashlib.sha256(encode_request(dict(r['request'],model='tinnel123/OmniJev'),image_bytes)).hexdigest(),'adapted_questions_sha256':prompt_hash,'input_tokens_packed_sequence':len(ids[0]),'image_grid_thw':pix['image_grid_thw'].tolist(),'pixel_values_shape':list(pix['pixel_values'].shape),'candidate_count':len(keys[0]),'depth_in_native_state':'depth' in state,'full_state_preserved':True}
   rows.append(row);print(json.dumps({k:row[k] for k in ['route','mode','step','input_tokens_packed_sequence','image_grid_thw']}) ,flush=True)
out=stage/'reports/omnijev-local-deployment-20261012-01/cpu-input-audit.json'
out.write_text(json.dumps({'status':'PASS','model_inference_executed':False,'GPU_used':False,'processor':'pinned native MSO1._encode_many','observations':rows},indent=2)+'\n')
print('PASS',len(rows),'real archived RGB+state inputs; no model forward')
