"""Local OneJev protocol and navigation integration; fake HTTP only."""
import argparse
import base64
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import numpy as np
import jev
import onejev
import rgb_input
import run
from test_core import config
from test_semantic_depth import numeric_facts
from test_decision_models import FlatPathfinder
from test_rgb_input import RgbEnvironment

MODEL = 'OmniJev/OneJev-4B'
ACTIONS = ('move_forward','move_backward','turn_left','turn_right','look_up','look_down','stop')


def result(choice='move_forward'):
    return {'model':MODEL,'answers':{'action':{'type':'choice','choice':choice,
        'probabilities':{a:float(a == choice) for a in ACTIONS},'confidence':1.0}},
        'usage':{'input_tokens':120,'output_tokens':1},'qev':{'media':{'images':1}}}


def cfg(**kwargs):
    return dict(config(),model=MODEL,onejev_manifest=None,**kwargs)


def fake_http(request, **kwargs):
    url = request.full_url
    if url.endswith('/health'): data={'status':'ok','model':MODEL}
    elif url.endswith('/v1/models'): data={'models':[{'name':MODEL}]}
    else: data=result()
    return io.BytesIO(json.dumps(data).encode())


class EncodingTests(unittest.TestCase):
    def test_all_depth_conditions_preserve_questions_and_jpeg_bytes(self):
        for mode,fmt in [('mesh','numeric'),('mesh','semantic'),('none','numeric')]:
            c=cfg(rgb_input='target_marked',depth_input=mode,depth_format=fmt)
            state={'depth':numeric_facts(),'visual':{'marker':{'kind':'test'}},'recent_actions':[]}
            saved=copy.deepcopy(state);p=jev.make_request(state,c);before=copy.deepcopy(p)
            wire=json.loads(jev.encode_request(p,b'jpeg-fixture'))
            self.assertEqual(wire['questions'],p['questions'])
            self.assertEqual(wire['state']['visual']['image'],'<image:1>')
            self.assertEqual(base64.b64decode(wire['media'][0]['data'].split(',')[1]),b'jpeg-fixture')
            self.assertEqual(p,before);self.assertEqual(state,saved)
            if mode=='none':self.assertNotIn('depth',wire['state'])
            elif fmt=='semantic':self.assertEqual(wire['state']['depth']['format'],'semantic')
            else:self.assertEqual(wire['state']['depth'],numeric_facts())

    def test_text_only_has_no_media_or_reference(self):
        p=jev.make_request({'recent_actions':[]},cfg())
        self.assertEqual(json.loads(jev.encode_request(p)),p)

    def test_wrong_model_missing_bytes_or_existing_placeholder_are_rejected(self):
        p=jev.make_request({'visual':{}},cfg())
        for bad in [b'', 'text']:
            with self.assertRaises(ValueError):onejev.encode_local_request(p,bad)
        with self.assertRaises(ValueError):onejev.encode_local_request(dict(p,model='other'),b'jpeg')
        with self.assertRaises(ValueError):onejev.encode_local_request(dict(p,state={'x':'<image:1>'}),b'jpeg')

    def test_openai_and_onejev_have_identical_semantic_prompts(self):
        p=jev.make_request({'recent_actions':[]},cfg(rgb_input='target_marked'))
        alternate=jev.make_request({'recent_actions':[]},dict(cfg(rgb_input='target_marked'),model=jev.DECISION_MODELS['openai']))
        self.assertEqual(p['questions'],alternate['questions'])
        self.assertEqual(p['state'],alternate['state'])


class ClientTests(unittest.TestCase):
    def test_local_url_only_and_finite_positive_timeout(self):
        for url in ['https://openrouter.ai','http://example.com','http://user:password@127.0.0.1:8011','http://127.0.0.1:8011/path','http://127.0.0.1:8011/?x=1']:
            with self.subTest(url=url),self.assertRaises(ValueError):onejev.OneJevClient(cfg(onejev_url=url))
        for t in [0,-1,float('nan'),True]:
            with self.assertRaises(ValueError):onejev.OneJevClient(cfg(onejev_timeout_s=t))

    def test_no_key_preflight_and_successful_local_choice(self):
        with patch.dict(os.environ,{},clear=True),patch('onejev.open_local',side_effect=fake_http) as transport:
            client=jev.create_decision_client(cfg())
            p=jev.make_request({'recent_actions':[]},cfg())
            d=client.decide(p)
        self.assertEqual(d['provider'],'onejev_local');self.assertEqual(d['api_provider'],'local_qev')
        self.assertEqual(d['attempts'],1);self.assertEqual(d['choice'],'move_forward')
        self.assertEqual(transport.call_count,3)
        sent=transport.call_args.args[0]
        self.assertEqual(sent.full_url,'http://127.0.0.1:8011/v1/systemone')
        self.assertNotIn('Authorization',sent.headers)
        self.assertEqual(d['request_body_sha256'],hashlib.sha256(sent.data).hexdigest())

    def test_health_mismatch_or_unreachable_fails_before_renderer(self):
        for fixture in [{'status':'ok','model':'wrong'}, {'status':'bad','model':MODEL}]:
            with patch('onejev.open_local',return_value=io.BytesIO(json.dumps(fixture).encode())),self.assertRaises(jev.ServiceFailure):
                onejev.OneJevClient(cfg())
        with patch('onejev.open_local',side_effect=urllib.error.URLError('offline')),self.assertRaises(jev.ServiceFailure):
            onejev.OneJevClient(cfg())

    def test_no_retry_on_bad_json_http_or_timeout(self):
        for error in [TimeoutError(),urllib.error.HTTPError('local',500,'error',{},None),ValueError()]:
            with patch('onejev.open_local',side_effect=fake_http):client=onejev.OneJevClient(cfg())
            with patch('onejev.open_local',side_effect=error) as transport,self.assertRaises(jev.ServiceFailure):
                client.decide(jev.make_request({},cfg()))
            self.assertEqual(transport.call_count,1)

    def test_model_probability_shape_and_confidence_are_checked(self):
        bad=[]
        for mutate in [lambda x:x.update(model='wrong'),
                       lambda x:x['answers']['action']['probabilities'].update(stop=float('nan')),
                       lambda x:x['answers']['action']['probabilities'].pop('stop'),
                       lambda x:x['answers']['action']['probabilities'].update(stop=.5),
                       lambda x:x['answers']['action'].update(confidence=2),
                       lambda x:x['answers']['action']['probabilities'].update(stop=True)]:
            x=result();mutate(x);bad.append(x)
        for x in bad:
            with patch('onejev.open_local',side_effect=fake_http):client=onejev.OneJevClient(cfg())
            with patch('onejev.open_local',return_value=io.BytesIO(json.dumps(x).encode())),self.assertRaises(jev.ServiceFailure):
                client.decide(jev.make_request({},cfg()))

    def test_unknown_choice_is_preserved_for_invalid_action_accounting(self):
        x=result();x['answers']['action']['choice']='unknown'
        with patch('onejev.open_local',side_effect=fake_http):client=onejev.OneJevClient(cfg())
        with patch('onejev.open_local',return_value=io.BytesIO(json.dumps(x).encode())):
            self.assertEqual(client.decide(jev.make_request({},cfg()))['choice'],'unknown')

    def test_rgb_setting_must_match_actual_image_presence(self):
        for mode,image in [('target_marked',None),('none',b'jpeg')]:
            with patch('onejev.open_local',side_effect=fake_http):client=onejev.OneJevClient(cfg(rgb_input=mode))
            with self.assertRaises(ValueError):client.decide(jev.make_request({},cfg()),image)

    def test_malformed_image_metadata_is_a_service_failure(self):
        for metadata in [None, {'media':None}, {'media':[]}, {'media':{'images':True}}, {}]:
            with patch('onejev.open_local',side_effect=fake_http):client=onejev.OneJevClient(cfg(rgb_input='target_marked'))
            x=result();x['qev']=metadata
            with patch('onejev.open_local',return_value=io.BytesIO(json.dumps(x).encode())),self.assertRaises(jev.ServiceFailure):
                client.decide(jev.make_request({},cfg(rgb_input='target_marked')),b'jpeg')

    def test_legacy_client_cannot_send_onejev_to_cloud_even_with_key(self):
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test-placeholder'},clear=True),patch('urllib.request.urlopen') as transport:
            with self.assertRaises(ValueError):jev.DecisionsClient(cfg())
        transport.assert_not_called()


class IntegrationTests(unittest.TestCase):
    def test_identity_rgb_and_cli(self):
        ident=jev.evaluation_identity(cfg())
        self.assertEqual(ident['provider'],'onejev_local');self.assertTrue(ident['is_onejev_evaluation'])
        self.assertFalse(ident['is_jev_evaluation']);self.assertFalse(ident['is_openai_decisions_evaluation'])
        rgb_input.validate_rgb_input(cfg(rgb_input='target_marked'),'gs')
        argv=['run.py','run','--tasks','unused','--out','unused','--decision-model','onejev','--onejev-url','http://127.0.0.1:9011','--onejev-timeout-s','40']
        with patch.dict(os.environ,{'CUDA_VISIBLE_DEVICES':'7'}),patch('sys.argv',argv),patch('run.run_episode',return_value=0) as runner:
            self.assertEqual(run.main(),0)
        self.assertEqual(runner.call_args.args[1]['onejev_timeout_s'],40)
        self.assertEqual(runner.call_args.args[1]['model'],MODEL)
        with patch('sys.argv',['run.py','run','--tasks','x','--out','x','--decision-model','jev','--onejev-url','http://127.0.0.1:8011']),self.assertRaises(SystemExit):
            run.main()

    def test_live_cli_requires_explicit_render_gpu_before_any_client_or_renderer(self):
        argv=['run.py','run','--tasks','x','--out','x','--decision-model','onejev']
        with patch.dict(os.environ,{},clear=True),patch('sys.argv',argv),patch('run.run_episode') as runner,self.assertRaises(SystemExit):
            run.main()
        runner.assert_not_called()

    def test_runner_records_local_wire_images_and_model_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);tasks=root/'tasks.json';out=root/'run'
            tasks.write_text(json.dumps({'tasks':[{'id':'test','start':[1,0,2],'goal':[1,0,1.75],
                'path':[[1,0,2],[1,0,1.75]],'geodesic_m':.25,'yaw_deg':0,'pitch_deg':0}]}))
            args=argparse.Namespace(command='run',tasks=str(tasks),episode='test',out=str(out),rgb='gs')
            c=cfg(rgb_input='target_marked',depth_input='none',max_steps=2)
            decisions=iter(['move_forward','stop']);wire=[]
            def http(req,**kwargs):
                if req.data is None:return fake_http(req,**kwargs)
                wire.append(req.data);return io.BytesIO(json.dumps(result(next(decisions))).encode())
            with patch.dict(os.environ,{},clear=True),patch('onejev.open_local',side_effect=http),patch('run.asset_manifest',return_value={}),patch('run.load_pathfinder',return_value=FlatPathfinder()),patch('run.shortest',side_effect=lambda pf,a,b:(float(np.linalg.norm(np.asarray(a)-np.asarray(b))),[a,b])),patch('run.Environment',RgbEnvironment),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run.run_episode(args,c),0)
            meta=json.loads((out/'metadata.json').read_text());summary=json.loads((out/'summary.json').read_text())
            self.assertEqual(meta['api_provider'],'local_qev');self.assertTrue(summary['is_onejev_evaluation'])
            self.assertTrue(summary['success']);self.assertEqual(summary['response_models'],[MODEL])
            records=[json.loads(x) for x in (out/'steps.jsonl').read_text().splitlines()]
            for record,body in zip(records,wire):
                data=json.loads(body);self.assertNotIn('depth',data['state'])
                self.assertEqual(base64.b64decode(data['media'][0]['data'].split(',')[1]),(out/record['image_input']['path']).read_bytes())
                self.assertEqual(record['wire_request_sha256'],hashlib.sha256(body).hexdigest())
                self.assertEqual(record['wire_state_encoding'],'object_plus_media_image_placeholder')
            self.assertNotIn('base64,',(out/'steps.jsonl').read_text())
            self.assertIn('OneJev-4B',(out/'index.html').read_text())

    def test_service_failure_never_executes_a_robot_action(self):
        with patch('onejev.open_local',side_effect=urllib.error.URLError('offline')),patch('run.Environment') as env:
            args=argparse.Namespace(command='run',rgb='gs')
            with self.assertRaises(jev.ServiceFailure):run.run_episode(args,cfg())
        env.assert_not_called()


class ToolTests(unittest.TestCase):
    def test_service_script_requires_gpu_and_has_nonexecuting_help(self):
        import subprocess
        root=Path(__file__).resolve().parent
        script=root/'scripts/serve_onejev.sh'
        self.assertTrue(script.is_file())
        env={k:v for k,v in os.environ.items() if k!='MODEL_GPU'}
        help_result=subprocess.run(['bash',str(script),'--help'],env=env,text=True,capture_output=True)
        self.assertEqual(help_result.returncode,0,help_result.stderr)
        no_gpu=subprocess.run(['bash',str(script)],env=env,text=True,capture_output=True)
        self.assertNotEqual(no_gpu.returncode,0)
        self.assertIn('MODEL_GPU',no_gpu.stderr)

    def test_probe_prepares_verified_archive_without_network(self):
        import subprocess
        from PIL import Image
        root=Path(__file__).resolve().parent
        script=root/'scripts/probe_onejev.py'
        self.assertTrue(script.is_file())
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source';source.mkdir();image=source/'image.jpg'
            Image.new('RGB',(2,2)).save(image)
            record={'step':0,'frame_kind':'before_action','request':jev.make_request({'visual':{'marker':{}}},cfg(rgb_input='target_marked')),
                'image_input':{'path':'image.jpg','sha256':hashlib.sha256(image.read_bytes()).hexdigest()}}
            (source/'metadata.json').write_text(json.dumps({'config':cfg(rgb_input='target_marked')}))
            (source/'steps.jsonl').write_text(json.dumps(record)+'\n')
            out=Path(tmp)/'probe.json'
            import sys
            command=[sys.executable,str(script),'--run',str(source),'--step','0','--out',str(out),'--prepare-only']
            completed=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(completed.returncode,0,completed.stderr)
            data=json.loads(out.read_text());self.assertFalse(data['called_model'])
            self.assertEqual(data['request']['model'],MODEL)
            self.assertNotIn('base64,',out.read_text())
            image.write_bytes(b'tampered')
            completed=subprocess.run([*command[:-1], '--prepare-only'],capture_output=True,text=True)
            self.assertNotEqual(completed.returncode,0)


if __name__=='__main__':unittest.main()
