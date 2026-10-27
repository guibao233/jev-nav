#!/usr/bin/env python3
"""Probe a saved real multimodal navigation request without moving the robot."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from jev import create_decision_client,encode_request,ServiceFailure
from omnijev import MODEL,DEFAULT_URL
from rgb_input import rgb_input_mode


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True,type=Path);p.add_argument('--step',type=int,default=0)
    p.add_argument('--out',required=True,type=Path);p.add_argument('--url',default=DEFAULT_URL)
    p.add_argument('--timeout-s',type=float,default=60);p.add_argument('--prepare-only',action='store_true')
    args=p.parse_args()
    if args.out.exists():p.error('output already exists; choose a new path')
    src=args.run.resolve();mp=src/'metadata.json';sp=src/'steps.jsonl';meta=json.loads(mp.read_text())
    rec=next((r for l in sp.read_text().splitlines() if (r:=json.loads(l)).get('step')==args.step and r.get('frame_kind')=='before_action' and r.get('request')),None)
    if rec is None:p.error('requested decision observation is unavailable')
    cfg=dict(meta['config'],model=MODEL,omnijev_url=args.url,omnijev_timeout_s=args.timeout_s)
    if rgb_input_mode(cfg)!='target_marked' or not rec.get('image_input'):p.error('choose a saved marked-RGB experiment')
    image=(src/rec['image_input']['path']).resolve()
    if src not in image.parents:p.error('source image is outside run')
    data=image.read_bytes()
    if hashlib.sha256(data).hexdigest()!=rec['image_input']['sha256']:p.error('saved image SHA256 mismatch')
    request=dict(rec['request'],model=MODEL);wire=encode_request(request,data)
    output={'source_run':str(src),'source_step':args.step,'called_model':not args.prepare_only,
            'source_steps_sha256':hashlib.sha256(sp.read_bytes()).hexdigest(),'source_metadata_sha256':hashlib.sha256(mp.read_bytes()).hexdigest(),
            'request':request,'image_input':rec['image_input'],'wire_request_sha256':hashlib.sha256(wire).hexdigest(),
            'wire_request_bytes':len(wire),'decision':None}
    code=0
    if not args.prepare_only:
        try:
            client=create_decision_client(cfg);output['service_health']=client.health
            output['decision']=client.decide(request,data)
        except ServiceFailure as exc:
            output['error']={'message':str(exc),'attempts':exc.attempts,'latency_s':exc.latency_s};code=2
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with args.out.open('x') as f:json.dump(output,f,indent=2,allow_nan=False)
    print('PROBE',args.out,'called_model',output['called_model']);return code


if __name__=='__main__':raise SystemExit(main())
