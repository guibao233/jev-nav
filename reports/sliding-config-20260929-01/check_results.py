"""Verify evidence from the scripted smoke and native execution checks."""
from pathlib import Path
import hashlib
import json

report = Path(__file__).resolve().parent
root = report.parent.parent
run = root/'runs/smoke-sliding-20260929-01'
metadata = json.loads((run/'metadata.json').read_text())
summary = json.loads((run/'summary.json').read_text())
execution = json.loads((report/'execution-results.json').read_text())
old = json.loads((root/'runs/jev-challenge-turn-000-six-actions-01/metadata.json').read_text())
protected = json.loads((report/'protected_hashes.json').read_text())
changed = [p for p, expected in protected.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest() != expected]
assert not changed, changed
assert execution['passed'] and len(execution['records']) == 12
assert metadata['allow_sliding'] is True and metadata['config']['allow_sliding'] is True
assert metadata['available_actions'] == ['move_forward', 'turn_left', 'turn_right', 'look_up', 'look_down', 'stop']
assert metadata['prompt_version'] == old['prompt_version'] == 'six_actions_stop_v2'
assert metadata['assets'] == old['assets']
assert summary['provider'] == 'scripted_smoke' and summary['is_jev_evaluation'] is False
assert summary['steps'] == 9 and summary['invalid_actions'] == 1 and summary['status'] == 'early_stop'
assert summary['collisions'] == 0 and summary['jev_request_latency'] is None
result = {'passed': True, 'protected_files_checked': len(protected), 'protected_files_changed': changed,
          'asset_manifest_matches_historical_run': True, 'allow_sliding_recorded_correctly': True,
          'prompt_and_action_set_unchanged': True, 'native_step_checks': len(execution['records']),
          'smoke_summary': summary, 'new_jev_evaluation_performed': False}
(report/'verification.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2))
