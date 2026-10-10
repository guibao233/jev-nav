#!/usr/bin/env python3
"""Probe a verified archived decision without moving the robot or modifying runs."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from jev import create_decision_client,encode_request
from onejev import MODEL,DEFAULT_URL
from rgb_input import rgb_input_mode


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True,type=Path)
    p.add_argument('--step',type=int,default=0,help='zero-based saved before_action step')
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--url',default=DEFAULT_URL)
    p.add_argument('--timeout-s',type=float,default=30)
    p.add_argument('--prepare-only',action='store_true',help='validate and hash input; no model/network call')
    args=p.parse_args()
    if args.out.exists():p.error('output already exists; choose a new path')
    source=args.run.resolve()
    meta_path=source/'metadata.json';steps_path=source/'steps.jsonl'
    metadata=json.loads(meta_path.read_text());record=None
    for line in steps_path.read_text().splitlines():
        item=json.loads(line)
        if item.get('step')==args.step and item.get('frame_kind')=='before_action' and item.get('request'):
            record=item;break
    if record is None:p.error('requested before_action step has no request')
    cfg=dict(metadata['config'],model=MODEL,onejev_url=args.url,onejev_timeout_s=args.timeout_s)
    request=dict(record['request'],model=MODEL)
    data=None;image_manifest=record.get('image_input')
    if rgb_input_mode(cfg)!='none':
        if not image_manifest:p.error('marked RGB input is missing; select a saved RGB-input experiment')
        image=(source/image_manifest['path']).resolve()
        if source not in image.parents:p.error('image path is outside source run')
        data=image.read_bytes()
        if hashlib.sha256(data).hexdigest()!=image_manifest['sha256']:p.error('model image SHA256 mismatch')
    body=encode_request(request,data)
    output={'source_run':str(source),'source_step':args.step,'called_model':not args.prepare_only,
        'source_steps_sha256':hashlib.sha256(steps_path.read_bytes()).hexdigest(),
        'source_metadata_sha256':hashlib.sha256(meta_path.read_bytes()).hexdigest(),
        'request':request,'image_input':image_manifest,'wire_request_sha256':hashlib.sha256(body).hexdigest(),
        'wire_request_bytes':len(body),'decision':None}
    code=0
    if not args.prepare_only:
        from jev import ServiceFailure
        try:
            client=create_decision_client(cfg)
            output['service_health']=client.health
            output['decision']=client.decide(request,data)
        except ServiceFailure as exc:
            output['error']={'message':str(exc),'attempts':exc.attempts,'latency_s':exc.latency_s};code=2
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with args.out.open('x') as f:json.dump(output,f,indent=2,allow_nan=False);f.write('\n')
    print('PROBE',args.out,'PREPARED' if args.prepare_only else 'FAILED' if code else output['decision']['choice'])
    return code


if __name__=='__main__':raise SystemExit(main())
