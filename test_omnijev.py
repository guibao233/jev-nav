"""OmniJev multimodal contract and navigation integration, without model/GPU calls."""
import argparse
import base64
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import jev
import rgb_input
import run
from test_core import config
from test_semantic_depth import numeric_facts
from test_decision_models import FlatPathfinder
from test_rgb_input import RgbEnvironment

MODEL='tinnel123/OmniJev'
ROOT=Path(__file__).resolve().parent
ACTIONS=('move_forward','move_backward','turn_left','turn_right','look_up','look_down','stop')


def cfg(**kw):
    return dict(config(),model=MODEL,rgb_input='target_marked',omnijev_manifest=None,**kw)


def answer(choice='move_forward'):
    return {'choice':choice,'probabilities':{a:(.3 if a==choice else 0.) for a in ACTIONS},
            'abstain':.7,'valid':False,'confidence':.6571}


def result(choice='move_forward'):
    return {'model':MODEL,'answers':{'action':dict(answer(choice),type='choice')},
            'omnijev':{'images':1,'input_image_sha256':hashlib.sha256(b'jpeg').hexdigest()}}


def http(req,**kw):
    if req.full_url.endswith('/health'):d={'status':'ok','model':MODEL,'release':'v1.1'}
    elif req.full_url.endswith('/v1/models'):d={'models':[{'name':MODEL}]}
    else:d=result()
    return io.BytesIO(json.dumps(d).encode())


class ModelContractTests(unittest.TestCase):
    def test_model_is_selectable_and_cannot_be_sent_to_cloud(self):
        self.assertIn('omnijev',jev.DECISION_MODELS)
        ident=jev.evaluation_identity(cfg())
        self.assertEqual(ident['provider'],'omnijev_local');self.assertTrue(ident['is_omnijev_evaluation'])
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'unused'}),self.assertRaisesRegex(ValueError,'local'):
            jev.DecisionsClient(cfg())

    def test_protocol_retains_each_depth_condition_and_original_image(self):
        self.assertIn('omnijev',jev.DECISION_MODELS)
        for depth,fmt in [('mesh','numeric'),('mesh','semantic'),('none','numeric')]:
            c=cfg(depth_input=depth,depth_format=fmt)
            state={'depth':numeric_facts(),'reference':{'test':'relative target'},'recent_actions':[]}
            saved=copy.deepcopy(state);p=jev.make_request(state,c)
            w=json.loads(jev.encode_request(p,b'jpeg'))
            self.assertEqual(w['state'],p['state']);self.assertEqual(w['questions'],p['questions'])
            self.assertEqual(base64.b64decode(w['image_data_url'].split(',')[1]),b'jpeg')
            self.assertEqual(w['image_sha256'],hashlib.sha256(b'jpeg').hexdigest())
            self.assertEqual(state,saved)
            if depth=='none':self.assertNotIn('depth',w['state'])
            elif fmt=='semantic':self.assertEqual(w['state']['depth']['format'],'semantic')
            rgb_input.validate_rgb_input(c,'gs')

    def test_service_bridge_really_includes_complete_state_in_model_instructions(self):
        self.assertTrue((ROOT/'omnijev_server.py').is_file())
        from omnijev_server import infer_request
        seen={}
        class Engine:
            last_input_tokens=125
            def system_one(self,state,questions):
                seen['state']=state;seen['questions']=questions
                self.assert_bytes=Path(state['images'][0]).read_bytes()
                return {'action':answer()}
        engine=Engine(); p=jev.make_request({'depth':numeric_facts(),'reference':{'distance':.85},'recent_actions':[]},cfg())
        wire=json.loads(jev.encode_request(p,b'jpeg'));before=copy.deepcopy(wire)
        response=infer_request(engine,wire)
        instructions=seen['questions']['action']['instructions']
        self.assertIn(p['questions']['action']['instructions'],instructions)
        self.assertEqual(json.loads(instructions.split('\nNAVIGATION_STATE_JSON:\n')[1]),p['state'])
        self.assertEqual(seen['questions']['action']['criteria'],p['questions']['action']['criteria'])
        self.assertEqual(engine.assert_bytes,b'jpeg');self.assertEqual(wire,before)
        self.assertEqual(response['answers']['action']['choice'],'move_forward')
        self.assertEqual(response['answers']['action']['abstain'],.7)
        self.assertFalse(response['answers']['action']['valid'])
        self.assertFalse(Path(seen['state']['images'][0]).exists())

    def test_client_preserves_native_choice_even_when_abstain_is_largest(self):
        self.assertIn('omnijev',jev.DECISION_MODELS)
        with patch('omnijev.open_local',side_effect=http):client=jev.create_decision_client(cfg())
        with patch('omnijev.open_local',side_effect=http) as transport:
            d=client.decide(jev.make_request({},cfg()),b'jpeg')
        self.assertEqual(d['choice'],'move_forward');self.assertEqual(d['attempts'],1)
        self.assertEqual(d['response']['answers']['action']['abstain'],.7)
        self.assertFalse(d['response']['answers']['action']['valid'])
        self.assertEqual(transport.call_count,1)

    def test_wrong_probability_mass_or_image_receipt_fails_without_retry(self):
        self.assertIn('omnijev',jev.DECISION_MODELS)
        with patch('omnijev.open_local',side_effect=http):client=jev.create_decision_client(cfg())
        for bad in ['mass','image','model']:
            d=result()
            if bad=='mass':d['answers']['action']['abstain']=.2
            elif bad=='image':d['omnijev']['input_image_sha256']='wrong'
            else:d['model']='wrong'
            with patch('omnijev.open_local',return_value=io.BytesIO(json.dumps(d).encode())) as transport,self.assertRaises(jev.ServiceFailure):
                client.decide(jev.make_request({},cfg()),b'jpeg')
            self.assertEqual(transport.call_count,1)

    def test_real_runner_saves_multimodal_hashes_identity_and_events(self):
        self.assertIn('omnijev',jev.DECISION_MODELS)
        with tempfile.TemporaryDirectory() as tmp:
            task={'id':'test','start':[0,0,0],'goal':[0,0,-.25],'yaw_rad':0.,'geodesic_m':.25,'path':[[0,0,0],[0,0,-.25]]}
            tasks=Path(tmp)/'tasks.json';tasks.write_text(json.dumps({'tasks':[task]}));out=Path(tmp)/'run'
            args=argparse.Namespace(command='run',rgb='gs',tasks=str(tasks),episode='test',out=str(out))
            choices=iter(['move_forward','stop']);bodies=[]
            def transport(req,**kw):
                if req.data is None:return http(req,**kw)
                body=json.loads(req.data);bodies.append(req.data);d=result(next(choices))
                d['omnijev']['input_image_sha256']=body['image_sha256']
                return io.BytesIO(json.dumps(d).encode())
            with patch.dict(os.environ,{},clear=True),patch('omnijev.open_local',side_effect=transport),patch('run.asset_manifest',return_value={}),patch('run.load_pathfinder',return_value=FlatPathfinder()),patch('run.shortest',side_effect=lambda pf,a,b:(float(np.linalg.norm(np.asarray(a)-np.asarray(b))),[a,b])),patch('run.Environment',RgbEnvironment),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run.run_episode(args,cfg(depth_input='none',max_steps=2)),0)
            summary=json.loads((out/'summary.json').read_text());meta=json.loads((out/'metadata.json').read_text())
            self.assertTrue(summary['success']);self.assertTrue(summary['is_omnijev_evaluation'])
            self.assertEqual(meta['api_provider'],'local_mso1');self.assertIn('omnijev_service_health',meta)
            records=[json.loads(l) for l in (out/'steps.jsonl').read_text().splitlines()]
            for r,b in zip(records,bodies):
                w=json.loads(b);self.assertNotIn('depth',w['state'])
                self.assertEqual(r['wire_request_sha256'],hashlib.sha256(b).hexdigest())
                self.assertEqual(base64.b64decode(w['image_data_url'].split(',')[1]),(out/r['image_input']['path']).read_bytes())
                self.assertEqual(r['wire_state_encoding'],'object_plus_inline_image')
            self.assertIn('OmniJev-4B',(out/'index.html').read_text())

    def test_cli_switch_and_local_only_flags(self):
        with patch.dict(os.environ,{'CUDA_VISIBLE_DEVICES':'1'}),patch('run.run_episode',return_value=0) as runner,patch('sys.argv',['run.py','run','--tasks','x','--out','x','--decision-model','omnijev','--rgb-input','target_marked','--omnijev-url','http://127.0.0.1:9012','--omnijev-timeout-s','40']):
            self.assertEqual(run.main(),0)
        self.assertEqual(runner.call_args.args[1]['model'],MODEL)
        self.assertEqual(runner.call_args.args[1]['omnijev_timeout_s'],40)
        with patch('sys.argv',['run.py','run','--tasks','x','--out','x','--decision-model','openai','--omnijev-url','http://127.0.0.1:8012']),self.assertRaises(SystemExit):run.main()

    def test_server_rejects_corrupt_image_before_calling_model(self):
        self.assertTrue((ROOT/'omnijev_server.py').is_file())
        from omnijev_server import infer_request
        class Engine:
            def system_one(self,*a):raise AssertionError('must not infer')
        p={'model':MODEL,'state':{},'questions':{'action':{'type':'choice','instructions':'x','criteria':{a:'' for a in ACTIONS}}},'image_data_url':'data:image/jpeg;base64,eA==','image_sha256':'wrong'}
        with self.assertRaises(ValueError):infer_request(Engine(),p)

    def test_probe_reconstructs_archived_image_and_state_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'src';(src/'frames').mkdir(parents=True)
            img=src/'frames/current.jpg';img.write_bytes(b'jpeg')
            image={'path':'frames/current.jpg','sha256':hashlib.sha256(b'jpeg').hexdigest()}
            c=cfg(depth_input='none');request=jev.make_request({'depth':numeric_facts(),'reference':{'distance':1}},c)
            (src/'metadata.json').write_text(json.dumps({'config':c}))
            (src/'steps.jsonl').write_text(json.dumps({'step':0,'frame_kind':'before_action','request':request,'image_input':image})+'\n')
            out=Path(tmp)/'prepared.json'
            import sys
            r=subprocess.run([sys.executable,str(ROOT/'scripts/probe_omnijev.py'),'--run',str(src),'--out',str(out),'--prepare-only'],capture_output=True,text=True,timeout=20)
            self.assertEqual(r.returncode,0,r.stderr)
            prepared=json.loads(out.read_text());self.assertFalse(prepared['called_model'])
            self.assertNotIn('depth',prepared['request']['state'])
            self.assertEqual(prepared['wire_request_sha256'],hashlib.sha256(jev.encode_request(request,b'jpeg')).hexdigest())

    def test_service_help_and_missing_gpu_do_not_load_models(self):
        script=ROOT/'scripts/serve_omnijev.sh';env={k:v for k,v in os.environ.items() if k!='MODEL_GPU'}
        help_result=subprocess.run(['bash',str(script),'--help'],env=env,capture_output=True,text=True)
        self.assertEqual(help_result.returncode,0,help_result.stderr)
        missing=subprocess.run(['bash',str(script)],env=env,capture_output=True,text=True)
        self.assertNotEqual(missing.returncode,0);self.assertIn('MODEL_GPU',missing.stderr)


if __name__=='__main__':unittest.main()
