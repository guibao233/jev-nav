from pathlib import Path
import hashlib
import json
import math

root=Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav').resolve()
deploy=root/'local_models/onejev-4b'
metadata=json.loads((deploy/'upstream-files.json').read_text())
revision=json.loads((deploy/'deployment.json').read_text())['model_revision']
assert metadata['sha']==revision
entries={x['rfilename']:x for x in metadata['siblings']}
names=['config.json','generation_config.json','processor_config.json','tokenizer_config.json','chat_template.jinja','tokenizer.json','model.safetensors']
files={}
for name in names:
    path=deploy/'weights'/name
    entry=entries[name]
    assert path.is_file(), 'missing '+name
    assert path.stat().st_size==entry['size'], 'size mismatch '+name
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''):digest.update(chunk)
    lfs=entry.get('lfs')
    blob=None
    if lfs:
        assert digest.hexdigest()==lfs['sha256'], 'official LFS SHA256 mismatch '+name
    else:
        data=path.read_bytes()
        blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        assert blob==entry['blobId'], 'official Git blob mismatch '+name
    files[name]={'bytes':path.stat().st_size,'sha256':digest.hexdigest(),
        'upstream_lfs_sha256':lfs['sha256'] if lfs else None,'upstream_git_blob_sha1':blob}
    print('VERIFIED',name,files[name]['bytes'],digest.hexdigest(),flush=True)
with (deploy/'weights/model.safetensors').open('rb') as f:
    header_bytes=int.from_bytes(f.read(8),'little')
    assert 0<header_bytes<16*1024*1024
    header=json.loads(f.read(header_bytes))
tensors={k:v for k,v in header.items() if k!='__metadata__'}
offsets=sorted(v['data_offsets'] for v in tensors.values())
assert offsets[0][0]==0
assert all(a[1]==b[0] for a,b in zip(offsets,offsets[1:]))
assert offsets[-1][1]+header_bytes+8==files['model.safetensors']['bytes']
dtype_bytes={'BF16':2,'F16':2,'F32':4,'F64':8,'I64':8,'I32':4,'I16':2,'I8':1,'U8':1,'BOOL':1}
for v in tensors.values():
    assert math.prod(v['shape'])*dtype_bytes[v['dtype']]==v['data_offsets'][1]-v['data_offsets'][0]
receipt={'model':'OmniJev/OneJev-4B','revision':revision,'files':files,
    'safetensors_header_valid':True,'tensor_count':len(tensors),
    'tensor_dtypes':sorted({v['dtype'] for v in tensors.values()}),
    'weights_origin':'user supplied complete model.safetensors; no resumed partial used',
    'gpu_initialized':False}
(deploy/'weights-manifest.json').write_text(json.dumps(receipt,indent=2)+'\n')
(root/'reports/onejev-local-deployment-20261010-01/weights-user-supplied-check.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('ALL_SEVEN_FILES_VERIFIED',receipt['tensor_count'],receipt['tensor_dtypes'],flush=True)
