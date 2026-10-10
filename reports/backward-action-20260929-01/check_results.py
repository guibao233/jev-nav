"""Check seven-action smoke, unchanged route/prompt rules, and source records."""
from pathlib import Path
import ast
import hashlib
import importlib.util
import json
import re
import sys
import numpy as np

REPORT=Path(__file__).resolve().parent;ROOT=REPORT.parent.parent
sys.path.insert(0,str(ROOT))
from core import depth_facts
from jev import make_request,PROMPT_VERSION

def before_module(name):
    spec=importlib.util.spec_from_file_location(name+'_before',REPORT/'before'/f'{name}.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

run=ROOT/'runs/smoke-backward-20260929-01'
m=json.loads((run/'metadata.json').read_text());s=json.loads((run/'summary.json').read_text())
rows=[json.loads(x) for x in (run/'steps.jsonl').read_text().splitlines()]
actions={'move_forward','move_backward','turn_left','turn_right','look_up','look_down','stop'}
assert set(m['available_actions'])==actions and m['prompt_version']==PROMPT_VERSION=='seven_actions_backward_v3'
assert m['allow_sliding'] is True and m['config']['move_m']==.25
assert s['provider']=='scripted_smoke' and not s['is_jev_evaluation']
assert s['steps']==9 and s['invalid_actions']==2 and s['collisions']==0 and s['status']=='early_stop'
old_core=before_module('core');old_jev=before_module('jev');cfg=m['config']
for r in rows:
    if not r.get('request'):continue
    q=r['request']['questions']['action']
    assert set(q['criteria'])==actions
    assert set(r['request']['state']['depth']['move_checks'])=={'move_forward','move_backward'}
    assert r['request']['state']['depth']['move_checks']['move_backward']['status']=='unknown'
    assert '0.25 metres' in q['criteria']['move_backward']
    assert 'move_left' not in q['criteria'] and 'move_right' not in q['criteria']
    old=old_jev.make_request(r['request']['state'],cfg)['questions']['action']
    for name,text in old['criteria'].items():assert text==q['criteria'][name]
    assert old['instructions'].replace('The complete action set is move_forward, turn_left,','The complete action set is move_forward, move_backward, turn_left,')==q['instructions']
    depth_path=run/r['images']['depth'].replace('-depth.png','-depth.npz')
    with np.load(depth_path) as data:depth=data['depth_m']
    facts=depth_facts(depth,r['pose']['pitch_deg'],cfg)
    facts['move_checks'].pop('move_backward')
    assert facts==old_core.depth_facts(depth,r['pose']['pitch_deg'],cfg)
assert rows[1]['outcome']['action']=='move_backward' and rows[1]['outcome']['actual_forward_m']==-.25
assert rows[1]['outcome']['valid'] and rows[1]['outcome']['success']
assert np.linalg.norm(np.array(rows[1]['after_position'])-rows[0]['pose']['position'])<1e-5
for index in [6,7]:
    assert not rows[index]['outcome']['valid'] and rows[index]['outcome']['actual_translation_m']==0
# AST comparison isolates route-management code from the added depth candidate.
def route_ast(path):
    return ast.dump(next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.ClassDef) and n.name=='RoutePreview'))
assert route_ast(ROOT/'core.py')==route_ast(REPORT/'before/core.py')
html=(run/'index.html').read_text();payload=json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',html,re.S).group(1))
assert payload['records'][1]['outcome']['action']=='move_backward'
assert payload['records'][7]['previous_action_event']['kinds']==['invalid']
assert payload['records'][8]['previous_action_event']['kinds']==['invalid']
protected=json.loads((REPORT/'protected_hashes.json').read_text())
for path,digest in protected.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
native=json.loads((REPORT/'native-results.json').read_text());assert native['passed']
result={'passed':True,'protected_files_unchanged':len(protected),'native_checks':len(native['open_space_checks'])+1,
        'prompt_version':PROMPT_VERSION,'current_move_m':cfg['move_m'],'smoke_summary':s,
        'route_logic_unchanged':True,'existing_depth_facts_unchanged':True,'existing_action_criteria_and_stop_unchanged':True,
        'rear_unknown_in_smoke':True,'sideways_invalid':True,'called_jev':False}
(REPORT/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
