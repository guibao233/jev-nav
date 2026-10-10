"""Independent inspection of actual mesh semantic requests, raw depths, and exports."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from core import depth_facts
from depth_language import semantic_depth
REPORT=Path(__file__).resolve().parent

def read(p):return json.loads(p.read_text())
def records(p):return [json.loads(s) for s in p.read_text().splitlines()]
def has_number(value):
    if isinstance(value,dict):return any(has_number(v) for v in value.values())
    if isinstance(value,list):return any(has_number(v) for v in value)
    return isinstance(value,(int,float)) and not isinstance(value,bool)

numeric=ROOT/'runs/smoke-semantic-simple-numeric-20261008-01'
simple=ROOT/'runs/smoke-semantic-simple-semantic-20261008-01'
complex_run=ROOT/'runs/smoke-semantic-complex-semantic-20261008-01'
checks={}
for folder in [simple,complex_run]:
    meta=read(folder/'metadata.json');summary=read(folder/'summary.json');rows=records(folder/'steps.jsonl')
    assert meta['depth_format']==summary['depth_format']=='semantic'
    assert meta['prompt_version']=='seven_actions_reassociate_motion_v5_semantic_depth_v1'
    assert summary['provider']=='scripted_smoke' and not summary['is_jev_evaluation']
    assert summary['steps']==4 and summary['status']=='early_stop' and summary['collisions']==0 and summary['invalid_actions']==0
    assert len(rows)==5
    for row in rows:
        if not row.get('request'):continue
        request=row['request'];depth=request['state']['depth']
        assert len(depth['sectors'])==9 and not has_number(depth)
        assert 'depth_numeric_debug' not in json.dumps(request)
        with np.load(folder/row['images']['depth'].replace('-depth.png','-depth.npz')) as saved:
            fresh=depth_facts(saved['depth_m'],row['pose']['pitch_deg'],meta['config'])
        assert fresh==row['depth_numeric_debug']
        assert semantic_depth(fresh)==depth
        assert depth['sectors'][0]['direction']=='right edge of forward view'
        assert depth['sectors'][4]['direction']=='straight ahead'
        assert depth['sectors'][-1]['direction']=='left edge of forward view'
        assert 'nearest_obstacle_m' not in json.dumps(depth)
    checks[folder.name]={'requests':4,'raw_depth_recomputed_equal':True,'numeric_depth_absent_from_request':True}

for a,b in zip(records(numeric/'steps.jsonl'),records(simple/'steps.jsonl')):
    for key in ['pose','outcome','after_position']:assert a.get(key)==b.get(key),key
    if a.get('request'):
        sa,sb=a['request']['state'],b['request']['state']
        assert {k:v for k,v in sa.items() if k!='depth'}=={k:v for k,v in sb.items() if k!='depth'}
        assert a['request']['questions']['action']['criteria']==b['request']['questions']['action']['criteria']

protected=read(REPORT/'protected-before.json')
for name,digest in protected.items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
viewer=REPORT/'viewer-complex';html=(viewer/'index.html').read_text()
embedded=json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',html,re.S).group(1))
for actual,shown in zip(records(complex_run/'steps.jsonl'),embedded['records']):assert actual['request']==shown['request']
script=re.search(r'</script><script>(.*?)</script>',html,re.S).group(1)
subprocess.run(['node','--check'],input=script,text=True,check=True)
export=read(viewer/'media/export.json');stream=export['ffprobe']['streams'][0]
assert stream['codec_name']=='h264' and int(stream['nb_read_frames'])==225
assert not export['called_jev'] and not export['reran_simulator']
print(json.dumps({'smoke':checks,'simple_paired_motion_and_other_state_equal':True,
                  'protected_files_unchanged':len(protected),'viewer_requests_equal':True,
                  'javascript_syntax_checked':True,'video_frames':225,'video_seconds':7.5,
                  'api_calls':0},indent=2))
