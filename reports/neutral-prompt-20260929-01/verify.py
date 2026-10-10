"""Offline verification only; makes no API or simulator calls."""
from pathlib import Path
import ast
import hashlib
import json
import sys

report = Path(__file__).resolve().parent
root = report.parent.parent
sys.path.insert(0, str(root))
from jev import make_request, PROMPT_VERSION
from environment import ACTIONS

before_source = (report/'before/jev.py').read_text()
before_ns = {}
exec(compile(before_source, 'before/jev.py', 'exec'), before_ns)
source = (root/'jev.py').read_text()
cfg = json.loads((root/'config.json').read_text())
old_first = json.loads(next((root/'runs/jev-challenge-turn-000-02/steps.jsonl').open()))
old_question = old_first['request']['questions']['action']
marker = 'Choose one next action'
assert PROMPT_VERSION == 'seven_actions_neutral_v4'
assert cfg['move_m'] == 0.25 and cfg['allow_sliding'] is True
assert tuple(ACTIONS) == ('move_forward', 'move_backward', 'turn_left', 'turn_right', 'look_up', 'look_down', 'stop')
checked = 0
for line in (root/'runs/jev-challenge-turn-000-backward-01/steps.jsonl').open():
    row = json.loads(line)
    if not row.get('request'):
        continue
    state = row['request']['state']
    before = before_ns['make_request'](state, cfg)
    after = make_request(state, cfg)
    bq, aq = before['questions']['action'], after['questions']['action']
    prefix = bq['instructions'].split(marker, 1)[0]
    assert aq['instructions'] == prefix + old_question['instructions']
    assert aq['criteria']['stop'] == bq['criteria']['stop']
    assert tuple(aq['criteria']) == tuple(ACTIONS)
    assert all(aq['criteria'][key] == old_question['criteria'][key] for key in ACTIONS if key != 'stop')
    assert after['state'] is state and after['model'] == before['model']
    # Outside the instruction body and backward criterion the request is unchanged.
    comparable = json.loads(json.dumps(after))
    comparable['questions']['action']['instructions'] = bq['instructions']
    comparable['questions']['action']['criteria']['move_backward'] = bq['criteria']['move_backward']
    assert comparable == before
    if checked == 0:
        (report/'request-example.json').write_text(json.dumps(after, indent=2, ensure_ascii=False)+'\n')
    checked += 1
assert checked > 0
# All code outside make_request and the prompt version remains identical.
def unchanged_ast(text):
    tree = ast.parse(text)
    tree.body = [node for node in tree.body if not (
        isinstance(node, ast.FunctionDef) and node.name == 'make_request'
        or isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'PROMPT_VERSION' for t in node.targets))]
    return ast.dump(tree)
assert unchanged_ast(before_source) == unchanged_ast(source)
protected = json.loads((report/'protected-before.json').read_text())
assert all(hashlib.sha256((root/path).read_bytes()).hexdigest() == digest for path, digest in protected.items())
assert not (root/'runs/jev-challenge-turn-000-neutral-01').exists()
result = {
    'prompt_version': PROMPT_VERSION,
    'saved_states_checked': checked,
    'historical_general_instructions_exact_match': True,
    'historical_non_stop_criteria_exact_match': True,
    'current_stop_prefix_and_criterion_unchanged': True,
    'state_and_other_request_fields_unchanged': True,
    'available_actions': list(ACTIONS),
    'move_m': cfg['move_m'], 'allow_sliding': cfg['allow_sliding'],
    'api_code_unchanged': True,
    'protected_files_unchanged': len(protected),
    'api_calls': 0, 'simulator_runs': 0,
    'performance_recovery_verified': False,
    'before_jev_sha256': hashlib.sha256(before_source.encode()).hexdigest(),
    'after_jev_sha256': hashlib.sha256(source.encode()).hexdigest(),
}
(report/'verification.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2))
