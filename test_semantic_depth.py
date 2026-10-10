"""Semantic depth must preserve geometry facts while excluding metric sensor fields."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from core import depth_facts
from jev import make_request, prompt_version, JevClient
from run import load_config, main
from test_core import config


def numeric_facts():
    return {'source':'current_mesh_depth_only','valid_fraction':.8,
            'sectors':[{'bearing_interval_deg':[-45+i*10,-35+i*10],
                        'nearest_obstacle_m':d,'observation':'obstacle_seen',
                        'observed_surface_range_p90_m':5.,'near_floor_seen':False}
                       for i,d in enumerate([.2,.5,.51,1.,1.01,2.,2.01,4.,4.01])],
            'move_checks':{'move_forward':{'status':'blocked','swept_volume_observed_fraction':.12},
                           'move_backward':{'status':'unknown','swept_volume_observed_fraction':0.}}}


def semantic_request(facts):
    return make_request({'depth':facts,'reference':{'current_target':{'bearing_deg':20}},
                         'robot':{'previous_collided':True}},dict(config(),depth_format='semantic'))


class SemanticDepthTests(unittest.TestCase):
    def test_metric_distances_become_named_ordered_ranges_with_correct_boundaries(self):
        depth=semantic_request(numeric_facts())['state']['depth']
        self.assertEqual(depth.get('format'),'semantic')
        self.assertEqual([r['distance_band'] for r in depth['sectors']],
                         ['very close','very close','close','close','moderately near',
                          'moderately near','far','far','very far'])
        self.assertEqual(depth['sectors'][0]['direction'],'right edge of forward view')
        self.assertEqual(depth['sectors'][4]['direction'],'straight ahead')
        self.assertEqual(depth['sectors'][-1]['direction'],'left edge of forward view')

    def test_unknown_and_no_obstacle_seen_are_never_far_or_clear(self):
        facts=numeric_facts()
        facts['sectors'][0].update(nearest_obstacle_m=None,observation='unknown',observed_surface_range_p90_m=None)
        facts['sectors'][1].update(nearest_obstacle_m=None,observation='no_obstacle_seen',near_floor_seen=True)
        depth=semantic_request(facts)['state']['depth']
        self.assertEqual(depth['sectors'][0]['observation'],'unknown')
        self.assertEqual(depth['sectors'][1]['observation'],'no_obstacle_seen')
        self.assertEqual(depth['sectors'][0].get('distance_band'),'unknown')
        self.assertEqual(depth['sectors'][1].get('distance_band'),'unknown')
        self.assertNotEqual(depth['sectors'][0]['near_floor'],depth['sectors'][1]['near_floor'])
        self.assertEqual(depth['move_checks']['move_backward']['status'],'unknown')
        self.assertEqual(depth['move_checks']['move_forward']['status'],'blocked')

    def test_request_boundary_excludes_all_numeric_depth_but_preserves_navigation(self):
        state={'depth':numeric_facts(),'reference':{'distance_m':.75},'recent_actions':[]}
        before=copy.deepcopy(state);cfg=dict(config(),depth_format='semantic')
        request=make_request(state,cfg)
        self.assertEqual(state,before)
        self.assertEqual(request['state']['reference'],state['reference'])
        self.assertEqual(request['state']['recent_actions'],[])
        def numbers(value):
            if isinstance(value,dict):return any(numbers(v) for v in value.values())
            if isinstance(value,list):return any(numbers(v) for v in value)
            return isinstance(value,(int,float)) and not isinstance(value,bool)
        self.assertFalse(numbers(request['state']['depth']))
        for name in ['nearest_obstacle_m','bearing_interval_deg','valid_fraction','swept_volume_observed_fraction','observed_surface_range_p90_m']:
            self.assertNotIn(name,json.dumps(request))
        response={'answers':{'action':{'choice':'stop','probabilities':{'stop':1.}}}}
        with patch.dict('os.environ',{'OPENROUTER_API_KEY':'test-placeholder'},clear=True),patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(response).encode())) as transport:
            JevClient(cfg).decide(request)
        self.assertEqual(json.loads(transport.call_args.args[0].data),request)

    def test_numeric_default_actions_and_stop_rule_unchanged_none_takes_precedence(self):
        state={'depth':numeric_facts()};cfg=config()
        numeric=make_request(state,cfg)
        semantic=make_request(state,dict(cfg,depth_format='semantic'))
        self.assertEqual(numeric,make_request(state,dict(cfg,depth_format='numeric')))
        self.assertIs(numeric['state'],state)
        self.assertEqual(numeric['questions']['action']['criteria'],semantic['questions']['action']['criteria'])
        self.assertEqual(numeric['questions']['action']['instructions'].split('Choose one next action')[0],
                         semantic['questions']['action']['instructions'].split('Choose one next action')[0])
        self.assertNotEqual(prompt_version(cfg),prompt_version(dict(cfg,depth_format='semantic')))
        self.assertEqual(make_request(state,dict(cfg,depth_input='none')),
                         make_request(state,dict(cfg,depth_input='none',depth_format='semantic')))

    def test_config_and_cli_enable_semantic_without_changing_task(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'config.json';cfg=config();p.write_text(json.dumps(cfg))
            self.assertEqual(load_config(p).get('depth_format'),'numeric')
            cfg['depth_format']='semantic';p.write_text(json.dumps(cfg))
            self.assertEqual(load_config(p)['depth_format'],'semantic')
            for bad in [None,False,'text']:
                cfg['depth_format']=bad;p.write_text(json.dumps(cfg))
                with self.assertRaisesRegex(ValueError,'depth_format'):load_config(p)
        for command in ['smoke','run']:
            with patch('sys.argv',['run.py',command,'--tasks','same.json','--episode','turn-000','--out','unused','--depth-format','semantic']),patch('run.run_episode',return_value=0) as runner:
                self.assertEqual(main(),0)
                args,cfg=runner.call_args.args
                self.assertEqual(cfg['depth_format'],'semantic')
                self.assertEqual(args.tasks,'same.json')

    def test_real_missing_depth_and_wall_retain_unknown_and_blocked(self):
        cfg=config()
        missing=semantic_request(depth_facts(np.zeros((120,160)),0,cfg))['state']['depth']
        self.assertTrue(all(s.get('distance_band')=='unknown' for s in missing['sectors']))
        self.assertEqual(missing['move_checks']['move_forward']['status'],'unknown')
        wall=semantic_request(depth_facts(np.full((120,160),.2),0,cfg))['state']['depth']
        self.assertEqual(wall['sectors'][4]['distance_band'],'very close')
        self.assertEqual(wall['move_checks']['move_forward']['status'],'blocked')
        self.assertEqual(wall['move_checks']['move_backward']['status'],'unknown')

    def test_other_sector_counts_are_rejected_instead_of_mislabelled(self):
        facts=numeric_facts();facts['sectors'].pop()
        with self.assertRaisesRegex(ValueError,'nine'):
            semantic_request(facts)


if __name__=='__main__':unittest.main()
