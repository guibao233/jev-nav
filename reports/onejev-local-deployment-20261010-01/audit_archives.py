"""CPU-only audit of the 18 fixed OpenAI RGB archives for local OneJev transport."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav').resolve()
REPORT = ROOT/'reports/onejev-local-deployment-20261010-01'
sys.path.insert(0, str(ROOT))
from onejev import MODEL, encode_local_request
from qev import media
from qev.prompt import build_messages, render_question, PROMPT_VERSION
from qev.schema import SystemOneRequest
from transformers import AutoProcessor
import torch

processor = AutoProcessor.from_pretrained(ROOT/'local_models/onejev-4b/weights', local_files_only=True, trust_remote_code=False)
selected = {}
longest = {}
scanned = 0
runs = []
for source in sorted((ROOT/'runs').glob('openai-decisions-rgbtarget-*')):
    if not source.is_dir() or not (source/'summary.json').is_file():
        continue
    cfg = json.loads((source/'metadata.json').read_text())['config']
    if cfg.get('rgb_input') != 'target_marked':
        continue
    mode = 'none' if cfg.get('depth_input') == 'none' else cfg.get('depth_format', 'numeric')
    runs.append(source.name)
    for line in (source/'steps.jsonl').read_text().splitlines():
        item = json.loads(line)
        if item.get('frame_kind') != 'before_action' or not item.get('request') or not item.get('image_input'):
            continue
        request = copy.deepcopy(item['request'])
        request['model'] = MODEL
        request['state']['visual']['image'] = '<image:1>'
        request['media'] = [{'type': 'image', 'data': ''}]
        req = SystemOneRequest.model_validate(request)
        rendered = render_question('action', req.questions['action'])
        prompt = media.render_prompt(processor, {'enable_thinking': False}, build_messages(req.state, rendered.suffix), req.media)
        count = len(processor.tokenizer.encode(prompt, add_special_tokens=False))
        case = {'source': source, 'step': item['step'], 'unexpanded_tokens': count, 'record': item}
        if mode not in longest or count > longest[mode]['unexpanded_tokens']:
            longest[mode] = case
        state = request['state']
        target = state['reference']['current_target']
        if item['step'] == 0:
            selected.setdefault((mode, 'ordinary'), case)
        if state.get('robot', {}).get('previous_collided') or abs(target['bearing_deg']) >= 45:
            selected.setdefault((mode, 'turn_or_blocked'), case)
        if target.get('is_final') and state['reference']['final_goal']['distance_m'] <= state['task']['stop_tolerance_m']:
            selected.setdefault((mode, 'arrival'), case)
        scanned += 1
for mode, case in longest.items():
    selected[(mode, 'longest')] = case

cases = []
for (mode, category), case in sorted(selected.items()):
    source = case['source']; item = case['record']
    out = REPORT/f'archive-{mode}-{category}-prepare.json'
    subprocess.run([str(ROOT/'local_models/onejev-4b/env/bin/python'), str(ROOT/'scripts/probe_onejev.py'),
                    '--run', str(source), '--step', str(case['step']), '--out', str(out), '--prepare-only'], check=True)
    prepared = json.loads(out.read_text())
    image = (source/item['image_input']['path']).resolve()
    wire = json.loads(encode_local_request(prepared['request'], image.read_bytes()))
    req = SystemOneRequest.model_validate(wire)
    rendered = render_question('action', req.questions['action'])
    prompt = media.render_prompt(processor, {'enable_thinking': False}, build_messages(req.state, rendered.suffix), req.media)
    images, videos, metas = media.load(req.media)
    tensors = processor(text=[prompt], return_tensors='pt', **media.processor_kwargs(images, videos, metas))
    tokens = tensors['input_ids'].shape[-1]
    assert len(images) == 1 and not videos
    assert tokens <= 8192
    assert len(req.questions['action'].criteria) == 7
    cases.append({'mode': mode, 'category': category, 'source_run': source.name, 'step': case['step'],
                  'unexpanded_tokens': case['unexpanded_tokens'], 'expanded_tokens': tokens,
                  'image_grid_thw': tensors['image_grid_thw'].tolist(),
                  'image_dimensions': [list(im.size) for im in images],
                  'wire_sha256': prepared['wire_request_sha256'], 'image_sha256': item['image_input']['sha256'],
                  'request_archive': out.name})
    print(mode, category, source.name, case['step'], tokens, flush=True)
assert not torch.cuda.is_initialized()
coverage = [{'mode': mode, 'category': category, 'status': 'passed' if (mode, category) in selected else 'no_archived_case'}
            for mode in ('numeric', 'semantic', 'none') for category in ('ordinary', 'turn_or_blocked', 'arrival', 'longest')]
result = {'status': 'passed', 'gpu_initialized': False, 'model_called': False, 'scanned_requests': scanned,
          'source_runs': runs, 'prompt_version': PROMPT_VERSION, 'cases': cases, 'coverage': coverage,
          'note': 'Exact processor checks for selected cases. Longest ranks unexpanded tokens; all selected grids must match before treating this as a fixed-size archive maximum. No decisions or robot motion.'}
assert len({json.dumps(x['image_grid_thw']) for x in cases}) == 1
(REPORT/'cpu-archive-validation.json').write_text(json.dumps(result, indent=2)+'\n')
print('CPU_ARCHIVE_AUDIT', scanned, 'requests', len(cases), 'cases', max(x['expanded_tokens'] for x in cases), 'max tokens', flush=True)
