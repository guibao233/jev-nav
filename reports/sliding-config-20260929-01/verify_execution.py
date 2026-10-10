"""Reproduce saved boundary poses with actual Environment.act; no Jev calls."""
import json
import math
import sys
from pathlib import Path
import numpy as np

REPORT = Path(__file__).resolve().parent
ROOT = REPORT.parent.parent
sys.path.insert(0, str(ROOT))
from environment import Environment, shortest
from run import load_config


def desired_endpoint(pos, yaw, length):
    return np.asarray(pos, dtype=np.float32) + length * np.array(
        [-math.sin(yaw), 0, -math.cos(yaw)], dtype=np.float32)


def main():
    cases = []
    for suffix, index, offset in [('01', 246, 0), ('02', 149, 45), ('03', 173, 0)]:
        source = ROOT / ('runs/jev-challenge-turn-000-six-actions-' + suffix) / 'steps.jsonl'
        row = json.loads(source.read_text().splitlines()[index])
        cases.append({'source': str(source), 'step_1based': index + 1,
                      'position': row['pose']['position'],
                      'yaw_deg': math.degrees(row['pose']['yaw_rad']) + offset,
                      'relative_turn_deg': offset})
    records = []
    errors = []
    for sliding in [False, True]:
        cfg = load_config(ROOT/'config.json')
        cfg['allow_sliding'] = sliding
        output = REPORT / ('sliding-true' if sliding else 'sliding-false')
        output.mkdir(exist_ok=False)
        env = Environment(cfg, output, rgb_mode='none')
        try:
            actual_setting = bool(env.mesh.config.sim_cfg.allow_sliding)
            assert actual_setting == sliding
            (output/'config.json').write_text(json.dumps(cfg, indent=2)+'\n')
            for case in cases:
                pos = np.array(case['position'], dtype=np.float32)
                inward_yaw = math.radians(case['yaw_deg'])
                # Also test an outward step with a non-navigable desired endpoint.
                outward = None
                for offset in [180] + list(range(-180, 180, 15)):
                    yaw = inward_yaw + math.radians(offset)
                    if not env.pf.is_navigable(desired_endpoint(pos, yaw, cfg['move_m'])):
                        outward = yaw
                        break
                assert outward is not None, 'No outward direction for boundary case'
                for direction, yaw in [('inward', inward_yaw), ('outward', outward)]:
                    env.reset({'start': pos.tolist(), 'yaw_deg': math.degrees(yaw), 'pitch_deg': 0})
                    before, actual_yaw = env.pose()
                    desired = desired_endpoint(before, actual_yaw, cfg['move_m'])
                    path = shortest(env.pf, before, desired)
                    result = env.act('move_forward')
                    after, _ = env.pose()
                    rec = dict(case, allow_sliding=sliding, actual_simulator_allow_sliding=actual_setting,
                               probe=direction, probe_yaw_deg=math.degrees(actual_yaw),
                               desired_endpoint=desired.tolist(), actual_endpoint=after.tolist(),
                               desired_endpoint_navigable=bool(env.pf.is_navigable(desired)),
                               actual_endpoint_navigable=bool(env.pf.is_navigable(after)),
                               desired_geodesic_m=path[0] if path else None,
                               endpoint_error_m=float(np.linalg.norm(after-desired)),
                               actual_translation_unrounded_m=float(np.linalg.norm(after-before)),
                               outcome=result)
                    records.append(rec)
                    print(json.dumps(rec), flush=True)
                    if not rec['actual_endpoint_navigable']:
                        errors.append(f'{sliding}/{case["step_1based"]}/{direction}: endpoint outside NavMesh')
                    if direction == 'inward':
                        if not rec['desired_endpoint_navigable'] or path is None or abs(path[0]-cfg['move_m']) > .002:
                            errors.append('Invalid inward test setup')
                        if sliding and (rec['endpoint_error_m'] > .001 or result['collided']):
                            errors.append(f'{case["source"]}: sliding did not restore inward movement')
                        if not sliding and (rec['actual_translation_unrounded_m'] > .001 or not result['collided']):
                            errors.append(f'{case["source"]}: original false bug not reproduced')
                    elif rec['desired_endpoint_navigable'] or rec['endpoint_error_m'] < .001:
                        errors.append('Outward test not constrained')
        finally:
            env.close()
    payload = {'verification': 'actual Habitat mesh simulator Environment.act, no API calls',
               'records': records, 'errors': errors, 'passed': not errors}
    (REPORT/'execution-results.json').write_text(json.dumps(payload, indent=2)+'\n')
    print('PASS' if not errors else 'FAIL', errors, flush=True)
    if errors:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
