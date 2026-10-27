import sys,json,hashlib,time
from pathlib import Path
import torch
from safetensors import safe_open
from transformers import AutoConfig,AutoProcessor

root=Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav')
deploy=root/'local_models/omnijev-4b'
sys.path.insert(0,str(deploy/'source'))
from mso.head import OptionScorer,OrdinalScoreHead

index=json.loads((deploy/'base/model.safetensors.index.json').read_text())
base_shapes={};shards=sorted(set(index['weight_map'].values()))
for shard in shards:
    with safe_open(deploy/'base'/shard,framework='pt',device='cpu') as stream:
        keys=list(stream.keys())
        assert set(keys)=={k for k,v in index['weight_map'].items() if v==shard}
        for key in keys:base_shapes[key]=stream.get_slice(key).get_shape()
assert len(base_shapes)==len(index['weight_map'])
cfg=AutoConfig.from_pretrained(deploy/'base',local_files_only=True)
assert cfg.model_type=='qwen3_5'
hidden=cfg.text_config.hidden_size
adapter=json.loads((deploy/'adapter/adapter_config.json').read_text())
assert adapter['base_model_name_or_path']=='Qwen/Qwen3.5-4B'
assert adapter['r']==32
with safe_open(deploy/'adapter/adapter_model.safetensors',framework='pt',device='cpu') as stream:
    adapter_shapes={k:stream.get_slice(k).get_shape() for k in stream.keys()}
for key,shape in adapter_shapes.items():
    prefix,which=key.rsplit('.lora_',1)
    base=prefix.removeprefix('base_model.model.')+'.weight'
    assert base in base_shapes,base
    out_dim,in_dim=base_shapes[base]
    expected=[adapter['r'],in_dim] if which=='A.weight' else [out_dim,adapter['r']]
    assert shape==expected,(key,shape,expected)
    assert stream is not None
meta=json.loads((deploy/'adapter/head_meta.json').read_text())
loaded={}
for name,module in [('head.pt',OptionScorer(hidden,d_hidden=min(1024,2*hidden),norm=meta['norm'])),('ord.pt',OrdinalScoreHead(hidden,d_hidden=min(512,hidden)))]:
    state=torch.load(deploy/'adapter'/name,map_location='cpu',weights_only=True)
    for key,tensor in state.items():assert torch.isfinite(tensor).all(),(name,key)
    module.load_state_dict(state,strict=True)
    loaded[name]={'keys':len(state),'strict_load':'PASS'}
emb=torch.load(deploy/'adapter/new_tok_emb.pt',map_location='cpu',weights_only=True)
assert list(emb.shape)==[2,hidden] and torch.isfinite(emb).all()
processor=AutoProcessor.from_pretrained(deploy/'adapter',local_files_only=True,max_pixels=768*28*28)
ids=processor.tokenizer.convert_tokens_to_ids(['<|opt|>','<|/opt|>'])
assert len(set(ids))==2 and all(x!=processor.tokenizer.unk_token_id for x in ids)
protected=json.loads((root/'reports/omnijev-local-deployment-20261012-01/protected-before.json').read_text())
for rel,digest in protected.items():assert hashlib.sha256((root/rel).read_bytes()).hexdigest()==digest,rel
result={'status':'PASS','base_shards':shards,'base_tensors':len(base_shapes),'adapter_tensors':len(adapter_shapes),
        'adapter_rank':adapter['r'],'hidden_size':hidden,'decision_heads':loaded,'option_token_ids':ids,
        'new_token_embedding_shape':list(emb.shape),'historical_files_unchanged':len(protected),
        'GPU_used':False,'model_forward_executed':False,'verified_unix':time.time()}
Path('/tmp/omnijev-user-weight-structure.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
