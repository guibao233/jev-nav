#!/usr/bin/env python3
"""Check pinned files, packages and optional allocated GPU without downloading."""
import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import socket
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from download_omnijev import sha,PACKAGES


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',type=int,default=8012);p.add_argument('--cpu-only',action='store_true');args=p.parse_args()
    d=ROOT/'local_models/omnijev-4b';m=json.loads((d/'deployment.json').read_text());w=json.loads((d/'weights-manifest.json').read_text())
    assert m['model']=='tinnel123/OmniJev' and m['release']=='v1.1'
    assert [(x['folder'],x['repo_id'],x['revision']) for x in w['packages']]==list(PACKAGES),'weight revisions changed'
    assert hashlib.sha256((d/'requirements.lock.txt').read_bytes()).hexdigest()==m['requirements_lock_sha256'],'package lock changed'
    for name,version in m['packages'].items():assert metadata.version(name)==version,'installed package changed: '+name
    for name,digest in m['upstream_files'].items():assert sha(d/'source'/name)==digest,'source changed: '+name
    for name,expected in w['files'].items():
        f=d/name;assert f.stat().st_size==expected['bytes'] and sha(f)==expected['sha256'],'weights changed: '+name
    from transformers import AutoProcessor
    from peft import PeftModel
    proc=AutoProcessor.from_pretrained(d/'adapter',local_files_only=True,max_pixels=768*28*28)
    assert proc.tokenizer is not None
    if not args.cpu_only:
        import torch
        assert torch.cuda.is_available() and torch.cuda.device_count()==1,'expose exactly one allocated MODEL_GPU'
        with socket.socket() as s:s.bind(('127.0.0.1',args.port))
        print('GPU free/total bytes:',torch.cuda.mem_get_info(0),'GPU:',torch.cuda.get_device_name(0),flush=True)
    print('PASS pinned source, packages, weights and processor',flush=True)


if __name__=='__main__':main()
