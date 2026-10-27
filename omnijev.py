"""Stdlib local OmniJev adapter; retains native choice, abstain and validity evidence."""
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

from jev import ServiceFailure, evaluation_identity
from onejev import local_url, open_local, _probability
from rgb_input import rgb_input_mode

MODEL='tinnel123/OmniJev'
DEFAULT_URL='http://127.0.0.1:8012'
DEFAULT_MANIFEST=Path(__file__).resolve().parent/'local_models/omnijev-4b/deployment.json'


def encode_local_request(payload,image_bytes=None):
    if payload.get('model')!=MODEL or not isinstance(payload.get('state'),dict):
        raise ValueError('OmniJev transport requires its model and an object state')
    if not isinstance(image_bytes,bytes) or not image_bytes:
        raise ValueError('OmniJev requires the current RGB JPEG bytes')
    wire=dict(payload,image_data_url='data:image/jpeg;base64,'+base64.b64encode(image_bytes).decode('ascii'),
              image_sha256=hashlib.sha256(image_bytes).hexdigest())
    return json.dumps(wire,allow_nan=False).encode()


class OmniJevClient:
    api_provider='local_mso1'
    wire_state_encoding='object_plus_inline_image'

    def __init__(self,cfg):
        if cfg['model']!=MODEL or rgb_input_mode(cfg)!='target_marked':
            raise ValueError('OmniJev requires its local model and target_marked RGB input')
        self.cfg=cfg;self.identity=evaluation_identity(cfg)
        self.base_url=local_url(cfg.get('omnijev_url') or os.environ.get('OMNIJEV_BASE_URL') or DEFAULT_URL)
        self.endpoint=self.base_url+'/v1/systemone'
        self.timeout_s=cfg.get('omnijev_timeout_s',60)
        if type(self.timeout_s) not in (float,int) or not math.isfinite(self.timeout_s) or self.timeout_s<=0:
            raise ValueError('omnijev_timeout_s must be positive and finite')
        self.health=self._get('/health');models=self._get('/v1/models')
        if not isinstance(self.health,dict) or self.health.get('status')!='ok' or self.health.get('model')!=MODEL or self.health.get('release')!='v1.1':
            raise ServiceFailure('OmniJev health/release/model mismatch',1,0.)
        if not isinstance(models,dict) or not isinstance(models.get('models'),list) or not any(isinstance(x,dict) and x.get('name')==MODEL for x in models['models']):
            raise ServiceFailure('OmniJev model not listed by local service',1,0.)
        self.deployment=None
        path=cfg.get('omnijev_manifest',DEFAULT_MANIFEST)
        if path is not None and Path(path).is_file():
            data=Path(path).read_bytes()
            self.deployment={'path':str(Path(path).resolve()),'sha256':hashlib.sha256(data).hexdigest(),'manifest':json.loads(data)}

    def _get(self,path):
        started=time.perf_counter()
        try:
            with open_local(urllib.request.Request(self.base_url+path,headers={'Accept':'application/json'}),timeout=self.timeout_s) as response:
                return json.load(response)
        except (urllib.error.URLError,TimeoutError,OSError,ValueError) as exc:
            raise ServiceFailure('OmniJev preflight failed: '+type(exc).__name__,1,time.perf_counter()-started) from None

    def decide(self,payload,image_bytes=None):
        body=encode_local_request(payload,image_bytes);started=time.perf_counter()
        try:
            req=urllib.request.Request(self.endpoint,data=body,headers={'Content-Type':'application/json'})
            with open_local(req,timeout=self.timeout_s) as response:result=json.load(response)
            if not isinstance(result,dict) or result.get('model')!=MODEL:raise ValueError('response model mismatch')
            a=result['answers']['action'];p=a['probabilities'];criteria=payload['questions']['action']['criteria']
            if (a.get('type')!='choice' or not isinstance(a.get('choice'),str) or not a['choice']
                    or not isinstance(p,dict) or set(p)!=set(criteria) or not all(_probability(x) for x in p.values())
                    or not _probability(a.get('abstain')) or not _probability(a.get('confidence'))
                    or not isinstance(a.get('valid'),bool)
                    or not math.isclose(sum(p.values())+a['abstain'],1.,abs_tol=.001)):
                raise ValueError('invalid native OmniJev probability distribution')
            receipt=result.get('omnijev',{})
            if type(receipt.get('images')) is not int or receipt['images']!=1 or receipt.get('input_image_sha256')!=hashlib.sha256(image_bytes).hexdigest():
                raise ValueError('image processing receipt mismatch')
            # Upstream picks the highest-probability action, even when abstain is larger.
            # Its valid flag describes probability normalization, not action validity.
            return {'provider':'omnijev_local','requested_model':MODEL,'api_provider':self.api_provider,
                    'response':result,'choice':a['choice'],'latency_s':time.perf_counter()-started,
                    'attempts':1,'retry_errors':[],'request_body_sha256':hashlib.sha256(body).hexdigest()}
        except (urllib.error.URLError,TimeoutError,OSError,ValueError,KeyError,TypeError,AttributeError) as exc:
            detail='HTTP '+str(exc.code) if isinstance(exc,urllib.error.HTTPError) else type(exc).__name__
            raise ServiceFailure('OmniJev local request failed: '+detail,1,time.perf_counter()-started) from None
