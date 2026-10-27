"""Loopback HTTP bridge for the pinned native MSO1 runtime, single-image navigation."""
import argparse
import base64
import binascii
import copy
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

MODEL='tinnel123/OmniJev'
BRIDGE_VERSION='navigation_state_json_v1'
ACTIONS=('move_forward','move_backward','turn_left','turn_right','look_up','look_down','stop')


def prepare_native_request(payload):
    """Validate media and explicitly put complete state in the native question."""
    if payload.get('model')!=MODEL or not isinstance(payload.get('state'),dict):
        raise ValueError('invalid model/state')
    questions=payload.get('questions')
    if not isinstance(questions,dict) or set(questions)!={'action'}:raise ValueError('one action question required')
    question=questions['action']
    if (question.get('type')!='choice' or list(question.get('criteria',{}))!=list(ACTIONS)
            or not isinstance(question.get('instructions'),str)):
        raise ValueError('seven ordered navigation choices required')
    url=payload.get('image_data_url')
    if not isinstance(url,str) or not url.startswith('data:image/jpeg;base64,'):raise ValueError('one inline JPEG required')
    try:data=base64.b64decode(url.split(',',1)[1],validate=True)
    except binascii.Error as exc:raise ValueError('invalid base64') from exc
    digest=hashlib.sha256(data).hexdigest()
    if not data or digest!=payload.get('image_sha256'):raise ValueError('image SHA256 mismatch')
    adapted=copy.deepcopy(questions)
    adapted['action']['instructions']+='\nNAVIGATION_STATE_JSON:\n'+json.dumps(payload['state'],allow_nan=False)
    prompt_hash=hashlib.sha256(json.dumps(adapted,allow_nan=False).encode()).hexdigest()
    return data,digest,adapted,prompt_hash


def infer_request(engine,payload):
    """MSO1 ignores arbitrary state keys: use the validated complete native input."""
    data,digest,adapted,prompt_hash=prepare_native_request(payload)
    began=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='omnijev-frame-') as tmp:
        path=Path(tmp)/'current.jpg';path.write_bytes(data)
        answers=engine.system_one({'images':[str(path)]},adapted)
    native=answers['action']
    return {'model':MODEL,'answers':{'action':dict(native,type='choice')},
            'usage':{'input_tokens':getattr(engine,'last_input_tokens',None),'output_tokens':0},
            'omnijev':{'images':1,'input_image_sha256':digest,'bridge_version':BRIDGE_VERSION,
                       'adapted_questions_sha256':prompt_hash,'native_inference_s':time.perf_counter()-began}}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--deploy',type=Path,required=True)
    p.add_argument('--port',type=int,default=8012)
    args=p.parse_args()
    if not 1<=args.port<=65535:p.error('invalid port')
    deploy=args.deploy.resolve()
    # Only the separate model environment imports CUDA/Transformers/PEFT.
    import torch
    if not torch.cuda.is_available() or torch.cuda.device_count()!=1:
        p.error('make exactly one allocated CUDA GPU visible with MODEL_GPU')
    sys.path.insert(0,str(deploy/'source'))
    from mso.infer import MSO1
    before=time.perf_counter();torch.cuda.reset_peak_memory_stats()
    engine=MSO1(str(deploy/'adapter'),str(deploy/'base'),max_pixels=768*28*28)
    manifest=json.loads((deploy/'deployment.json').read_text())
    health={'status':'ok','model':MODEL,'release':'v1.1','bridge_version':BRIDGE_VERSION,
            'bridge_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'deployment_sha256':hashlib.sha256((deploy/'deployment.json').read_bytes()).hexdigest(),
            'upstream_commit':manifest['upstream_commit'],'model_revision':manifest['model_revision'],
            'base_revision':manifest['base_revision'],'dtype':str(engine.dtype),'head_dtype':'float32',
            'branch':engine.branch,'max_pixels':768*28*28,'temperatures':engine.temps,
            'settings':{name:os.environ.get(name) for name in ['MSO_ATTN','MSO_FLA','MSO_BRANCH','MSO_STATE_CACHE']},
            'gpu_name':torch.cuda.get_device_name(0),'physical_gpu':os.environ.get('CUDA_VISIBLE_DEVICES'),
            'load_seconds':time.perf_counter()-before,'load_peak_allocated_bytes':torch.cuda.max_memory_allocated()}
    lock=threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def reply(self,code,data):
            body=json.dumps(data,allow_nan=False).encode()
            self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_GET(self):
            if self.path=='/health':self.reply(200,health)
            elif self.path=='/v1/models':self.reply(200,{'models':[{'name':MODEL}]})
            else:self.reply(404,{'error':'unknown endpoint'})
        def do_POST(self):
            if self.path!='/v1/systemone':self.reply(404,{'error':'unknown endpoint'});return
            if not lock.acquire(blocking=False):self.reply(503,{'error':'one inference already running'});return
            try:
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=16*1024*1024:raise ValueError('request size exceeds limit')
                payload=json.loads(self.rfile.read(n))
                if not isinstance(payload,dict):raise ValueError('object request required')
                result=infer_request(engine,payload)
                result['omnijev']['peak_allocated_bytes']=torch.cuda.max_memory_allocated()
                self.reply(200,result)
            except (ValueError,TypeError,KeyError,AttributeError):self.reply(400,{'error':'invalid navigation request'})
            except Exception as exc:
                print('Inference failed:',type(exc).__name__,flush=True)
                self.reply(500,{'error':'inference_failure','type':type(exc).__name__})
            finally:lock.release()
        def log_message(self,format,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    receipt=deploy/'logs'/f'startup-{time.time_ns()}.json'
    receipt.write_text(json.dumps(health,indent=2)+'\n')
    print(json.dumps(health),flush=True);print(f'Listening http://127.0.0.1:{args.port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()
