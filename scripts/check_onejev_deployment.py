#!/usr/bin/env python3
"""Verify pinned local deployment before loading weights; no downloads."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8011)
    args=parser.parse_args()
    deploy=ROOT/'local_models/onejev-4b'
    manifest=json.loads((deploy/'deployment.json').read_text())
    weights=json.loads((deploy/'weights-manifest.json').read_text())
    assert manifest['model']=='OmniJev/OneJev-4B'
    assert weights['revision']==manifest['model_revision']
    assert (deploy/'requirements.lock.txt').is_file(),'dependency lock missing'
    commit=subprocess.check_output(['git','-C',str(deploy/'source'),'rev-parse','HEAD'],text=True).strip()
    assert commit==manifest['qev_commit'],'qev source revision changed'
    dirty=subprocess.check_output(['git','-C',str(deploy/'source'),'status','--porcelain'],text=True)
    assert not dirty.strip(),'qev source has uncommitted changes'
    lock=(deploy/'requirements.lock.txt').read_bytes()
    assert hashlib.sha256(lock).hexdigest()==manifest['requirements_lock_sha256'],'dependency lock changed'
    from importlib import metadata
    for name,version in manifest['packages'].items():
        assert metadata.version(name)==version,'installed package changed: '+name
    import qev
    package=Path(qev.__file__).resolve().parent
    for name,expected in manifest['qev_package_files'].items():
        assert hashlib.sha256((package/name).read_bytes()).hexdigest()==expected,'installed qev source changed: '+name
    for name,expected in weights['files'].items():
        path=deploy/'weights'/name
        assert path.stat().st_size==expected['bytes'],'weight size changed: '+name
        digest=hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda:f.read(8*1024*1024),b''):digest.update(block)
        assert digest.hexdigest()==expected['sha256'],'weight hash changed: '+name
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',args.port))
    import torch
    assert torch.cuda.is_available(),'CUDA unavailable in OneJev environment'
    assert torch.cuda.device_count()==1,'expose exactly one MODEL_GPU'
    free,total=torch.cuda.mem_get_info(0)
    receipt={'created_unix':time.time(),'physical_gpu':os.environ['CUDA_VISIBLE_DEVICES'],
        'cuda_device':0,'gpu_name':torch.cuda.get_device_name(0),'free_bytes_before_load':free,
        'total_gpu_bytes':total,'port':args.port,'deployment_sha256':hashlib.sha256((deploy/'deployment.json').read_bytes()).hexdigest()}
    path=deploy/'logs'/f'startup-{time.time_ns()}.json'
    path.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt),flush=True)


if __name__=='__main__':main()
