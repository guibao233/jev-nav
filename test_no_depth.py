"""Depth ablation boundaries: preserve navigation inputs, remove perception payload."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from environment import ACTIONS
from jev import JevClient, make_request, prompt_version, PROMPT_VERSION, NO_DEPTH_PROMPT_VERSION
from run import load_config, main
from test_core import config


def sample_state():
    return {'task': {'step':1, 'stop_tolerance_m':.3},
            'reference':{'current_target':{'bearing_deg':25.,'distance_m':.75,'is_final':False},
                         'final_goal':{'distance_m':3.5},'ordered_preview':[{'forward_m':.5,'left_m':.2}]},
            'robot':{'camera_pitch_deg':15.,'previous_collided':True},
            'depth':{'source':'sensitive_depth_sentinel','sectors':[{'nearest_obstacle_m':.123}],
                     'move_checks':{'move_forward':{'status':'blocked'}},'valid_fraction':.9},
            'recent_actions':[{'action':'move_forward','collided':True,'actual_translation_m':0.}],
            'recent_motion':{'status':'low_net_motion'}}


class NoDepthTests(unittest.TestCase):
    def test_api_boundary_removes_only_depth_and_preserves_caller(self):
        state=sample_state();before=copy.deepcopy(state)
        cfg=dict(config(),depth_input='none')
        result=make_request(state,cfg)
        self.assertEqual(result['state'],{k:v for k,v in state.items() if k!='depth'})
        self.assertEqual(state,before)
        self.assertNotIn('sensitive_depth_sentinel',json.dumps(result))
        self.assertNotIn('sectors',json.dumps(result))
        self.assertNotIn('move_checks',json.dumps(result))
        self.assertNotIn('nearest_obstacle_m',json.dumps(result))

    def test_depth_contents_cannot_influence_ablated_request(self):
        state=sample_state();cfg=dict(config(),depth_input='none')
        before=make_request(state,cfg)
        state['depth']={'sectors':[{'nearest_obstacle_m':1000}], 'move_checks':{'move_forward':{'status':'clear'}}}
        self.assertEqual(make_request(state,cfg),before)
        del state['depth']
        self.assertEqual(make_request(state,cfg),before)

    def test_default_depth_and_actions_stop_and_recovery_rules_preserved(self):
        state=sample_state();cfg=config()
        default=make_request(state,cfg)
        explicit=make_request(state,dict(cfg,depth_input='mesh'))
        ablated=make_request(state,dict(cfg,depth_input='none'))
        self.assertEqual(default,explicit)
        self.assertIs(default['state'],state)
        self.assertEqual(default['questions']['action']['criteria'],ablated['questions']['action']['criteria'])
        self.assertEqual(set(ablated['questions']['action']['criteria']),set(ACTIONS))
        text=ablated['questions']['action']['instructions']
        self.assertEqual(text.split('Choose one next action')[0],default['questions']['action']['instructions'].split('Choose one next action')[0])
        self.assertIn('No depth or image observations are provided.',text)
        self.assertIn('recent_motion.status is turn_oscillation',text)
        self.assertIn('Temporary movement away from the target is allowed for recovery.',text)
        for forbidden in ['Use mesh-depth observations','Blocked indicates','Clear is only a sampled depth','inspect unseen nearby floor']:
            self.assertNotIn(forbidden,text)
        self.assertEqual(prompt_version(cfg),PROMPT_VERSION)
        self.assertEqual(prompt_version(dict(cfg,depth_input='none')),NO_DEPTH_PROMPT_VERSION)

    def test_wire_payload_contains_no_depth_or_images(self):
        cfg=dict(config(),depth_input='none')
        payload=make_request(sample_state(),cfg)
        response={'answers':{'action':{'choice':'stop','probabilities':{'stop':1.}}}}
        with patch.dict('os.environ',{'OPENROUTER_API_KEY':'test-placeholder'},clear=True),patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(response).encode())) as network:
            JevClient(cfg).decide(payload)
        body=json.loads(network.call_args.args[0].data)
        self.assertEqual(body,payload)
        self.assertNotIn('depth',body['state'])
        self.assertNotIn('images',body['state'])
        self.assertTrue(body['state']['robot']['previous_collided'])

    def test_config_validation_and_missing_option_default(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.json'
            for mode in ['mesh','none',False,None,'no-depth']:
                cfg=config();cfg['depth_input']=mode;path.write_text(json.dumps(cfg))
                if mode in ('mesh','none'):
                    self.assertEqual(load_config(path)['depth_input'],mode)
                else:
                    with self.assertRaisesRegex(ValueError,'depth_input'):load_config(path)
            cfg=config();cfg.pop('depth_input',None);path.write_text(json.dumps(cfg))
            self.assertEqual(load_config(path)['depth_input'],'mesh')

    def test_cli_switch_is_applied_to_run_and_smoke_without_changing_task(self):
        for command in ['run','smoke']:
            for flags,expected in [([], 'mesh'),(['--depth-input','none'], 'none')]:
                with self.subTest(command=command,flags=flags),patch('sys.argv',['run.py',command,'--tasks','same.json','--episode','turn-000','--out','unused',*flags]),patch('run.run_episode',return_value=0) as runner:
                    self.assertEqual(main(),0)
                    args,cfg=runner.call_args.args
                    self.assertEqual(cfg['depth_input'],expected)
                    self.assertEqual(args.tasks,'same.json')
                    self.assertEqual(args.episode,'turn-000')


if __name__ == '__main__':unittest.main()
