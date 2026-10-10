"""Read-only verification of generated tasks and actual scripted mesh smoke."""
from pathlib import Path
import hashlib
import json
import math
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from prepare_initial_heading import build_dataset, initial_target
from run import load_config

report = Path(__file__).resolve().parent
source_path = ROOT/'tasks/challenge-clearance-20260929-01/tasks.json'
output_path = ROOT/'tasks/challenge-clearance-aligned-20260930-01/tasks.json'
source = json.loads(source_path.read_text())
output = json.loads(output_path.read_text())
cfg = load_config(ROOT/'config.single-gpu.json')
expected = build_dataset(source,cfg,['turn-000'])
for key,value in expected.items():
    assert output[key] == value,key
original,aligned = source['tasks'][0], output['tasks'][0]
assert set(aligned)-set(original) == {'initial_heading'}
changed = [key for key in original if original[key] != aligned[key]]
assert changed == ['yaw_deg'],changed
# Test the old 12-task dataset as well, without generating another persistent variant.
old_tasks = json.loads((ROOT/'tasks/challenge-v1-20260928/tasks.json').read_text())
all_aligned = build_dataset(old_tasks,cfg)
assert len(all_aligned['tasks']) == len(old_tasks['tasks']) == 12
for task in all_aligned['tasks']:
    first = initial_target(task,task['yaw_deg'],cfg)
    assert abs(first['bearing_deg']) <= .01 and first['forward_m'] > 0
for filename,digest in output['initial_heading_generator_sha256'].items():
    assert hashlib.sha256((ROOT/filename).read_bytes()).hexdigest() == digest
assert hashlib.sha256(source_path.read_bytes()).hexdigest() == output['initial_heading_source_tasks']['sha256']
manifest = json.loads((report/'protected-before.json').read_text())
for filename,digest in manifest.items():
    assert hashlib.sha256((ROOT/filename).read_bytes()).hexdigest() == digest, filename

smoke = ROOT/'runs/smoke-initial-heading-20260930-01'
metadata = json.loads((smoke/'metadata.json').read_text())
summary = json.loads((smoke/'summary.json').read_text())
records = [json.loads(line) for line in (smoke/'steps.jsonl').read_text().splitlines()]
first = records[0]
target = first['request']['state']['reference']['current_target']
assert abs(target['bearing_deg']) <= .01 and target['forward_m'] > 0
loaded_yaw = math.degrees(first['pose']['yaw_rad'])
assert abs((loaded_yaw-aligned['yaw_deg']+180)%360-180) < 1e-3
assert first['decision']['choice'] == 'move_forward'
assert first['outcome']['valid'] and not first['outcome']['collided']
assert abs(first['outcome']['actual_forward_m']-.25) < .001
assert abs(first['outcome']['actual_left_m']) < .001
assert metadata['task'] == aligned
assert metadata['prompt_version'] == 'seven_actions_reassociate_motion_v5'
assert metadata['provider'] == 'scripted_smoke'
assert summary['status'] == 'early_stop' and summary['steps'] == 2
assert not summary['is_jev_evaluation'] and summary['collisions'] == 0
assert summary['initial_geodesic_m'] == original['geodesic_m']
print(json.dumps({
    'original_task_fields_changed':changed,
    'source_yaw_deg':original['yaw_deg'], 'aligned_yaw_deg':aligned['yaw_deg'],
    'initial_target_before':aligned['initial_heading']['target_before'],
    'initial_target_after':target,
    'mesh_loaded_yaw_deg':loaded_yaw,
    'scripted_first_action_outcome':first['outcome'],
    'smoke_status':summary['status'],
    'original_shortest_m':summary['initial_geodesic_m'],
    'reference_length_m':metadata['reference_path_length_m'],
    'all_original_challenge_tasks_align':len(all_aligned['tasks']),
    'protected_files_unchanged':len(manifest),
    'source_and_generator_hashes_match':True,
    'deterministic_regeneration_identical':True,
    'api_calls':0
},indent=2))
