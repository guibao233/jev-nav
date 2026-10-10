"""Rebuild old text requests with installed code; never sends any requests."""
from pathlib import Path
import copy, hashlib, json
import sys

ROOT = Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav')
sys.path.insert(0, str(ROOT))
from jev import make_request, encode_request

OUT = Path(__file__).resolve().parent
names = []
for filename in ['reports/route-ablation-summary-20261008-01/summary.json', 'reports/openai-ablation-audit-20261009-01/audit.json']:
    names += [r['run'] for r in json.loads((ROOT/filename).read_text())['rows']]
count = 0
for name in names:
    folder = ROOT/'runs'/name
    cfg = json.loads((folder/'metadata.json').read_text())['config']
    for line in (folder/'steps.jsonl').read_text().splitlines():
        record = json.loads(line)
        if not record.get('request'): continue
        original = record['request']
        state = copy.deepcopy(original['state'])
        if record.get('depth_numeric_debug'):
            state['depth'] = record['depth_numeric_debug']
        rebuilt = make_request(state, cfg)
        assert rebuilt == original, (name, record['step'])
        assert encode_request(rebuilt) == json.dumps(original, allow_nan=False).encode()
        count += 1
hashes = json.loads((OUT/'historical-hashes.json').read_text())
assert all(hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == digest for path, digest in hashes.items())
result = {'runs': len(names), 'requests_identical': count, 'wire_bytes_identical': count,
          'protected_files_unchanged': len(hashes), 'api_calls': 0}
(OUT/'default-request-parity.json').write_text(json.dumps(result, indent=2)+'\n')
print('PASS', json.dumps(result))
