"""Local qev System One adapter. No torch/SDK imports or cloud fallback."""
import base64
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from jev import ServiceFailure, evaluation_identity
from rgb_input import rgb_input_mode

MODEL = 'OmniJev/OneJev-4B'
DEFAULT_URL = 'http://127.0.0.1:8011'
DEFAULT_MANIFEST = Path(__file__).resolve().parent/'local_models/onejev-4b/deployment.json'


def local_url(value):
    """Require a loopback HTTP origin without credentials, paths or queries."""
    if not isinstance(value,str):
        raise ValueError('onejev_url must be a loopback HTTP origin')
    parsed=urllib.parse.urlsplit(value)
    try:
        port=parsed.port
    except ValueError as exc:
        raise ValueError('invalid OneJev port') from exc
    if (parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost','::1')
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in ('','/') or parsed.query or parsed.fragment
            or port is not None and not 1<=port<=65535):
        raise ValueError('onejev_url must be a loopback HTTP origin with no credentials or path')
    return value.rstrip('/')


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url,code,'local service redirects are disabled',headers,fp)


def open_local(request,timeout):
    # Ignore HTTP proxies and reject redirects so local input never leaves host.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoRedirect()).open(request,timeout=timeout)


def encode_local_request(payload,image_bytes=None):
    if payload.get('model')!=MODEL:
        raise ValueError('local OneJev transport requires OmniJev/OneJev-4B')
    if image_bytes is None:
        return json.dumps(payload,allow_nan=False).encode()
    if not isinstance(image_bytes,bytes) or not image_bytes:
        raise ValueError('current RGB image bytes are required')
    if not isinstance(payload.get('state'),dict):
        raise ValueError('OneJev image state must be a dictionary')
    if re.search(r'<(?:image|video):\d+>',json.dumps(payload['state'])):
        raise ValueError('existing media placeholders are not accepted')
    wire=copy.deepcopy(payload)
    visual=wire['state'].setdefault('visual',{})
    if not isinstance(visual,dict):
        raise ValueError('visual state must be a dictionary')
    visual['image']='<image:1>'
    wire['media']=[{'type':'image','data':'data:image/jpeg;base64,'+base64.b64encode(image_bytes).decode('ascii')}]
    return json.dumps(wire,allow_nan=False).encode()


def _probability(value):
    return type(value) in (int,float) and math.isfinite(value) and 0<=value<=1


class OneJevClient:
    api_provider='local_qev'
    wire_state_encoding='object_plus_media_image_placeholder'

    def __init__(self,cfg):
        if cfg['model']!=MODEL:
            raise ValueError('OneJevClient requires the local OneJev model')
        self.cfg=cfg
        self.identity=evaluation_identity(cfg)
        self.base_url=local_url(cfg.get('onejev_url') or os.environ.get('ONEJEV_BASE_URL') or DEFAULT_URL)
        self.endpoint=self.base_url+'/v1/systemone'
        self.timeout_s=cfg.get('onejev_timeout_s',30)
        if type(self.timeout_s) not in (float,int) or not math.isfinite(self.timeout_s) or self.timeout_s<=0:
            raise ValueError('onejev_timeout_s must be positive and finite')
        self.health=self._get('/health')
        if not isinstance(self.health,dict) or self.health.get('status')!='ok' or self.health.get('model')!=MODEL:
            raise ServiceFailure('OneJev health or served model mismatch',1,0.)
        models=self._get('/v1/models')
        if not isinstance(models,dict) or not isinstance(models.get('models'),list) or not any(isinstance(x,dict) and x.get('name')==MODEL for x in models['models']):
            raise ServiceFailure('OneJev model is not listed by local service',1,0.)
        self.deployment=None
        path=cfg.get('onejev_manifest',DEFAULT_MANIFEST)
        if path is not None and Path(path).is_file():
            data=Path(path).read_bytes()
            self.deployment={'path':str(Path(path).resolve()),'sha256':hashlib.sha256(data).hexdigest(),
                             'manifest':json.loads(data)}

    def _get(self,path):
        start=time.perf_counter()
        try:
            req=urllib.request.Request(self.base_url+path,headers={'Accept':'application/json'})
            with open_local(req,timeout=self.timeout_s) as response:
                return json.load(response)
        except (urllib.error.URLError,TimeoutError,OSError,ValueError) as exc:
            # No raw URLs, response bodies, headers or environment values in errors.
            raise ServiceFailure('OneJev preflight failed: '+type(exc).__name__,1,time.perf_counter()-start) from None

    def decide(self,payload,image_bytes=None):
        if (rgb_input_mode(self.cfg)!='none')!=(image_bytes is not None):
            raise ValueError('RGB input setting and current image bytes must agree')
        body=encode_local_request(payload,image_bytes)
        start=time.perf_counter()
        try:
            req=urllib.request.Request(self.endpoint,data=body,headers={'Content-Type':'application/json'})
            with open_local(req,timeout=self.timeout_s) as response:
                result=json.load(response)
            if not isinstance(result,dict) or result.get('model')!=MODEL:
                raise ValueError('local response model mismatch')
            answer=result['answers']['action']
            if not isinstance(answer,dict) or answer.get('type')!='choice' or not isinstance(answer.get('choice'),str) or not answer['choice']:
                raise ValueError('invalid action choice')
            probabilities=answer['probabilities']
            candidates=payload['questions']['action']['criteria']
            if (not isinstance(probabilities,dict) or set(probabilities)!=set(candidates)
                    or not all(_probability(v) for v in probabilities.values())
                    or not math.isclose(sum(probabilities.values()),1.,abs_tol=1e-4)
                    or not _probability(answer.get('confidence'))):
                raise ValueError('invalid action probabilities/confidence')
            if image_bytes is not None:
                meta=result.get('qev')
                media=meta.get('media') if isinstance(meta,dict) else None
                if not isinstance(media,dict) or type(media.get('images')) is not int or media['images']!=1:
                    raise ValueError('local service did not report processing one image')
            return {'provider':'onejev_local','requested_model':MODEL,'api_provider':self.api_provider,
                    'response':result,'choice':answer['choice'],'latency_s':time.perf_counter()-start,
                    'attempts':1,'retry_errors':[],'request_body_sha256':hashlib.sha256(body).hexdigest()}
        except (urllib.error.URLError,TimeoutError,OSError,ValueError,KeyError,TypeError) as exc:
            detail=('HTTP '+str(exc.code)) if isinstance(exc,urllib.error.HTTPError) else type(exc).__name__
            raise ServiceFailure('OneJev local request failed: '+detail,1,time.perf_counter()-start) from None
