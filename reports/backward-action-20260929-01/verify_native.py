"""Verify native backward control uses the shared translation step; no API."""
from pathlib import Path
import json
import math
import sys
import numpy as np

REPORT=Path(__file__).resolve().parent
ROOT=REPORT.parent.parent
sys.path.insert(0,str(ROOT))
from environment import Environment, ACTIONS, load_pathfinder
from jev import make_request, PROMPT_VERSION
from run import load_config

cfg=load_config(ROOT/'config.json');pf=load_pathfinder(cfg);pf.seed(20260929)
island=max(range(pf.num_islands),key=pf.island_area)
start=None
for _ in range(10000):
    point=pf.get_random_navigable_point(island_index=island)
    if pf.distance_to_closest_obstacle(point,1.)>.65:
        start=np.asarray(point).tolist();break
assert start is not None,'No sufficiently open test point'
checks=[]
for length in [.25,.40]:
    config=dict(cfg,move_m=length)
    output=REPORT/f'native-{int(length*100):02d}cm';output.mkdir(exist_ok=False)
    env=Environment(config,output,rgb_mode='none')
    try:
        action_space=env.mesh.config.agents[0].action_space
        assert set(action_space)==set(ACTIONS)-{'stop'}
        amounts={name:action_space[name].actuation.amount for name in ['move_forward','move_backward']}
        assert all(abs(amount-length)<1e-6 for amount in amounts.values()),amounts
        criteria=make_request({},config)['questions']['action']['criteria']
        for name in ['move_forward','move_backward']:
            assert f'{length} metres' in criteria[name]
        for yaw_deg in [17.,107.]:
            env.reset({'start':start,'yaw_deg':yaw_deg,'pitch_deg':15})
            origin,_=env.pose();forward=env.act('move_forward');ahead,_=env.pose()
            backward=env.act('move_backward');returned,_=env.pose()
            assert forward['valid'] and backward['valid']
            assert not forward['collided'] and not backward['collided']
            assert abs(np.linalg.norm(ahead-origin)-length)<1e-5
            assert abs(np.linalg.norm(returned-ahead)-length)<1e-5
            assert np.linalg.norm(returned-origin)<1e-5
            assert abs(backward['actual_forward_m']+length)<.001
            assert abs(backward['actual_left_m'])<.001
            assert backward['actual_yaw_deg']==0. and backward['actual_pitch_deg']==0.
            checks.append({'move_m':length,'yaw_deg':yaw_deg,'actuation_amounts':amounts,
                'forward':forward,'backward':backward,'return_error_m':float(np.linalg.norm(returned-origin))})
        if length==.25:
            source=ROOT/'runs/jev-challenge-turn-000-sliding-01/steps.jsonl'
            row=json.loads(source.read_text().splitlines()[13])
            assert row['outcome']['collided']
            env.reset({'start':row['after_position'],'yaw_deg':math.degrees(row['pose']['yaw_rad']),'pitch_deg':row['pose']['pitch_deg']})
            before,yaw=env.pose();outcome=env.act('move_backward');after,_=env.pose()
            desired=before+length*np.array([math.sin(yaw),0,math.cos(yaw)])
            assert outcome['valid'] and not outcome['collided'],outcome
            assert np.linalg.norm(after-desired)<1e-5
            assert env.pf.is_navigable(after)
            recovery={'source_run':str(source.parent),'after_action_1based':14,
                      'outcome':outcome,'desired_error_m':float(np.linalg.norm(after-desired))}
    finally:env.close()
result={'passed':True,'prompt_version':PROMPT_VERSION,'actions':list(ACTIONS),
        'open_space_checks':checks,'recorded_collision_backward_check':recovery,
        'configuration_on_disk_unchanged':load_config(ROOT/'config.json')['move_m']==.25,
        'called_jev':False}
(REPORT/'native-results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
