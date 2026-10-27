import hashlib,json,time
from pathlib import Path

root=Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav')
deploy=root/'local_models/omnijev-4b'
packages=[('adapter','tinnel123/OmniJev','ffe5f436eaf22e20e2f041f8e74e121fd057a6cb'),('base','Qwen/Qwen3.5-4B','851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a')]
release=json.loads((deploy/'adapter/release_manifest.json').read_text())
files={}
for folder,repo,revision in packages:
    listing=json.loads(Path('/tmp/omnijev-'+folder+'-pinned-metadata.json').read_text())
    assert listing['sha']==revision
    for item in listing['siblings']:
        name=item['rfilename']
        if name in ('.gitattributes','release_manifest.json','README.md','results_v11.json','results_v11_zh.md'):continue
        path=deploy/folder/name;size=item['size']
        assert path.stat().st_size==size,('size mismatch',str(path),path.stat().st_size,size)
        sha256=hashlib.sha256();gitblob=hashlib.sha1()
        gitblob.update(('blob '+str(size)+'\0').encode())
        with path.open('rb') as stream:
            for block in iter(lambda:stream.read(8*1024*1024),b''):
                sha256.update(block);gitblob.update(block)
        digest=sha256.hexdigest()
        expected=release.get('files',{}).get(name,{}).get('sha256') if folder=='adapter' else None
        expected=expected or item.get('lfs',{}).get('sha256')
        if expected:assert digest==expected,('SHA256 mismatch',str(path))
        if not item.get('lfs'):assert gitblob.hexdigest()==item['blobId'],('git blob mismatch',str(path))
        rel=folder+'/'+name
        files[rel]={'bytes':size,'sha256':digest,'upstream_sha256':expected,'upstream_git_blob':item['blobId'],'revision':revision,'repo_id':repo}
        print('PASS',rel,size,flush=True)
manifest={'files':files,'packages':[{'folder':f,'repo_id':r,'revision':v} for f,r,v in packages],
          'endpoint':'https://huggingface.co','created_unix':time.time(),'downloaded_by':'user',
          'verification':'upstream LFS SHA256 and git blob SHA1 for non-LFS files'}
Path('/tmp/omnijev-user-weights-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('PASS',len(files),'pinned runtime files; no model forward',flush=True)
