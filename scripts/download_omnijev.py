#!/usr/bin/env python3
"""Download pinned public OmniJev adapter/backbone with upstream SHA256 checks."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
PACKAGES=(('adapter','tinnel123/OmniJev','ffe5f436eaf22e20e2f041f8e74e121fd057a6cb'),
          ('base','Qwen/Qwen3.5-4B','851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a'))


def sha(path):
    d=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):d.update(b)
    return d.hexdigest()


def remote(url):
    last=None
    for attempt in range(3):
        try:return urllib.request.urlopen(url,timeout=40)
        except (urllib.error.URLError,TimeoutError,OSError) as exc:
            last=exc
            if attempt<2:time.sleep(1+attempt)
    raise RuntimeError('public download failed: '+type(last).__name__) from None


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--deploy',type=Path,default=ROOT/'local_models/omnijev-4b')
    p.add_argument('--endpoint',default='https://huggingface.co',help='public HF-compatible mirror, revisions and hashes remain pinned')
    p.add_argument('--check-only',action='store_true',help='offline verification of saved weights-manifest.json')
    args=p.parse_args();deploy=args.deploy.resolve();manifest_path=deploy/'weights-manifest.json'
    if args.check_only:
        manifest=json.loads(manifest_path.read_text())
        for rel,meta in manifest['files'].items():
            f=deploy/rel
            if f.stat().st_size!=meta['bytes'] or sha(f)!=meta['sha256']:raise ValueError('weight mismatch: '+rel)
        print('PASS',len(manifest['files']),'pinned weight files');return
    deploy.mkdir(parents=True,exist_ok=True);files={};jobs=[];endpoint=args.endpoint.rstrip('/')
    for folder,repo,revision in PACKAGES:
        (deploy/folder).mkdir(exist_ok=True)
        with remote(f'{endpoint}/api/models/{repo}/revision/{revision}?blobs=true') as r:listing=json.load(r)
        if listing['sha']!=revision:raise ValueError('model revision mismatch')
        release={}
        if folder=='adapter':
            with remote(f'{endpoint}/{repo}/resolve/{revision}/release_manifest.json') as r:release=json.load(r)
            (deploy/folder/'release_manifest.json').write_text(json.dumps(release,indent=2)+'\n')
        for item in listing['siblings']:
            name=item['rfilename']
            if name in ('.gitattributes','release_manifest.json','README.md','results_v11.json','results_v11_zh.md'):continue
            rel=folder+'/'+name;meta=release.get('files',{}).get(name,{})
            digest=meta.get('sha256') or item.get('lfs',{}).get('sha256')
            jobs.append((rel,repo,revision,name,item.get('size'),digest))
    def download(job):
        rel,repo,revision,name,size,expected=job;target=deploy/rel
        if target.is_file() and target.stat().st_size==size and (not expected or sha(target)==expected):
            print('Verified existing',rel,flush=True)
        else:
            part=target.with_name(target.name+'.partial');part.parent.mkdir(parents=True,exist_ok=True)
            print('Downloading',rel,'bytes',size,flush=True)
            with remote(f'{endpoint}/{repo}/resolve/{revision}/{name}') as response,part.open('wb') as f:
                for chunk in iter(lambda:response.read(4*1024*1024),b''):f.write(chunk)
            if part.stat().st_size!=size:raise ValueError('size mismatch: '+rel)
            digest=sha(part)
            if expected and digest!=expected:raise ValueError('SHA256 mismatch: '+rel)
            part.replace(target)
        return rel,{'bytes':target.stat().st_size,'sha256':sha(target),'upstream_sha256':expected,'revision':revision,'repo_id':repo}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for rel,meta in pool.map(download,jobs):files[rel]=meta
    manifest={'files':files,'packages':[{'folder':f,'repo_id':r,'revision':v} for f,r,v in PACKAGES],
              'endpoint':endpoint,'created_unix':time.time()}
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    print('PASS',len(files),'weight files downloaded and verified',flush=True)


if __name__=='__main__':main()
