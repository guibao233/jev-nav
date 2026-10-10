"""Verify ablation isolation against saved real requests and paired mesh smoke."""
from pathlib import Path
import hashlib
import importlib.util
import json
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
REPORT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from jev import make_request, PROMPT_VERSION, NO_DEPTH_PROMPT_VERSION


def read(path):return json.loads(path.read_text())
def records(path):return [json.loads(line) for line in path.read_text().splitlines()]

spec=importlib.util.spec_from_file_location('jev_before_ablation',REPORT/'before/jev.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
baseline=ROOT/'runs/jev-challenge-turn-000-clearance-aligned-01'
cfg=read(baseline/'metadata.json')['config']
preserved=0
for r in records(baseline/'steps.jsonl'):
    if r.get('request'):
        expected=r['request']
        assert make_request(expected['state'],cfg)==old.make_request(expected['state'],cfg)==expected
        preserved+=1

mesh=ROOT/'runs/smoke-depth-ablation-mesh-20260930-01'
none=ROOT/'runs/smoke-depth-ablation-none-20260930-01'
a,b=records(mesh/'steps.jsonl'),records(none/'steps.jsonl')
ma,mb=read(mesh/'metadata.json'),read(none/'metadata.json')
assert ma['task']==mb['task']==read(baseline/'metadata.json')['task']
assert ma['prompt_version']==PROMPT_VERSION and mb['prompt_version']==NO_DEPTH_PROMPT_VERSION
assert ma['depth_input']=='mesh' and mb['depth_input']=='none'
assert ma['depth_provided_to_model'] and not mb['depth_provided_to_model']
assert ma['available_actions']==mb['available_actions']
assert {k:v for k,v in ma['config'].items() if k!='depth_input'}=={k:v for k,v in mb['config'].items() if k!='depth_input'}
assert len(a)==len(b)==7
paired=0
for left,right in zip(a,b):
    for key in ('pose','outcome','after_position'):
        assert left.get(key)==right.get(key),(paired,key)
    for image in right['images'].values():
        if image:assert (none/image).is_file()
    if not left.get('request'):
        assert right.get('request') is None
        continue
    sa,sb=left['request']['state'],right['request']['state']
    assert 'depth' in sa and 'depth' not in sb
    assert {k:v for k,v in sa.items() if k!='depth'}==sb
    assert left['request']['questions']['action']['criteria']==right['request']['questions']['action']['criteria']
    assert right['request']==make_request(sa,mb['config'])
    for forbidden in ('sectors','nearest_obstacle_m','move_checks','swept_volume_observed_fraction'):
        assert forbidden not in json.dumps(right['request'])
    assert 'images' not in sb
    paired+=1
for folder in (mesh,none):
    s=read(folder/'summary.json')
    assert s['provider']=='scripted_smoke' and not s['is_jev_evaluation']
    assert s['status']=='early_stop' and s['steps']==6 and s['collisions']==0 and s['invalid_actions']==0
    assert s['depth_input']==read(folder/'metadata.json')['depth_input']

viewer=REPORT/'viewer-none'
html=(viewer/'index.html').read_text()
payload=read(none/'metadata.json')
embedded=json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',html,re.S).group(1))
assert embedded['metadata']==payload
for original,viewed in zip(b,embedded['records']):assert original.get('request')==viewed.get('request')
assert '本组深度仅供回放，未提供给 Jev。' in html
script=re.search(r'</script><script>(.*?)</script>',html,re.S).group(1)
subprocess.run(['node','--check'],input=script,text=True,check=True)
export=read(viewer/'media/export.json')
assert export['source_observations']==7 and not export['called_jev'] and not export['reran_simulator']
stream=export['ffprobe']['streams'][0]
assert stream['codec_name']=='h264' and int(stream['nb_read_frames'])==315

protected=read(REPORT/'protected-before.json')
for name,digest in protected.items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
print(json.dumps({'historical_default_requests_exactly_preserved':preserved,
                  'paired_smoke_requests_with_only_depth_state_removed':paired,
                  'paired_poses_actions_outcomes_equal':True,
                  'actions':ma['available_actions'],
                  'no_depth_prompt_version':mb['prompt_version'],
                  'depth_images_retained_only_for_replay':True,
                  'viewer_requests_match_logs':True,
                  'viewer_javascript_syntax_valid':True,
                  'video_frames':315,'video_seconds':10.5,
                  'protected_files_unchanged':len(protected),'api_calls':0},indent=2))
