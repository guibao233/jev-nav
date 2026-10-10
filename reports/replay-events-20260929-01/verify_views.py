"""Check saved real-run overlays, source preservation, and post-action alignment."""
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import threading
from urllib.request import urlopen

from PIL import Image, ImageColor

REPORT = Path(__file__).resolve().parent
ROOT = REPORT.parent.parent
sys.path.insert(0,str(ROOT))
from replay_events import observation_event, completed_events
from visualize import make_server

checks = []
for name in ['collision-check-20260928-01','jev-challenge-turn-000-02']:
    run = ROOT/'runs'/name
    out = run/'visualizations/events-20260929-01'
    original = [json.loads(line) for line in (run/'steps.jsonl').read_text().splitlines()]
    html = (out/'index.html').read_text()
    payload = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',html,re.S).group(1))
    rows = payload['records']
    assert len(rows) == len(original)
    collisions = invalid = 0
    for i,(source,display) in enumerate(zip(original,rows)):
        for key in source:
            if key != 'images':
                assert display[key] == source[key], (name,i,key)
        prior = original[i-1].get('outcome') or {} if i else {}
        expected = []
        if prior.get('collided') is True: expected.append('collision')
        if prior.get('valid') is False: expected.append('invalid')
        event = display['previous_action_event']
        assert (event['kinds'] if event else []) == expected
        if event:
            assert event['step_1based'] == original[i-1]['step']+1
            assert event['position'] == original[i-1]['after_position']
        collisions += 'collision' in expected
        invalid += 'invalid' in expected
        for channel,path in source['images'].items():
            if path:
                assert hashlib.sha256((run/path).read_bytes()).digest() == hashlib.sha256((out/display['images'][channel]).read_bytes()).digest()
        if source['images'].get('rgb'):
            with Image.open(out/display['rgb_display_image']) as rgb:
                if event: assert rgb.getpixel((2,2)) == ImageColor.getrgb(event['color'])
                else:
                    with Image.open(run/source['images']['rgb']) as raw: assert rgb.tobytes() == raw.convert('RGB').tobytes()
        with Image.open(out/display['map_image']) as map_image:
            if event: assert map_image.getpixel((2,2)) == ImageColor.getrgb(event['color'])
            if name.startswith('collision-check'):
                with Image.open(out/'media/maps'/f'{i:05d}.png') as media_map: assert map_image.tobytes() == media_map.tobytes()
                with Image.open(out/'media/frames'/f'{i:05d}.png') as media_frame:
                    with Image.open(out/display['rgb_display_image']) as rgb: assert media_frame.crop((0,112,640,592)).tobytes() == rgb.tobytes()
        for prior_event in completed_events(original,i):
            assert prior_event['step_1based'] <= i
    summary = json.loads((run/'summary.json').read_text())
    assert collisions == summary['collisions'] and invalid == summary['invalid_actions']
    manifest = json.loads((out/'visualization.json').read_text())
    for path,digest in manifest['source_sha256'].items():
        assert hashlib.sha256((run/path).read_bytes()).hexdigest() == digest
    assert not manifest['called_jev'] and not manifest['reran_simulator']
    checks.append({'run':name,'frames':len(rows),'collision_frames':collisions,'invalid_frames':invalid,'original_fields_and_sources_preserved':True})

    if name.startswith('collision-check'):
        # Real frames: action 3 collides; it must not tint observation 3.
        assert rows[2]['previous_action_event'] is None
        assert rows[3]['previous_action_event']['step_1based'] == 3
        assert rows[6]['previous_action_event']['kinds'] == ['invalid']
        # Reuse actual post-action observations as terminal fixtures without
        # fabricating actions or modifying the saved run.
        for event_index in [2,5]:
            terminal = copy.deepcopy(original[event_index+1])
            terminal.update(frame_kind='after_final_action',request=None,decision=None,outcome=None)
            clip = original[:event_index+1]+[terminal]
            assert observation_event(clip,len(clip)-1)['step_1based'] == event_index+1
        # No outcome is not an invalid action and must not inherit stale events.
        missing = dict(original[2],outcome=None)
        assert observation_event([missing,original[3]],1) is None
        (REPORT/'viewer-script.js').write_text(re.findall(r'<script>(.*?)</script>',html,re.S)[0])
        with make_server(out,0) as server:
            worker = threading.Thread(target=server.serve_forever,daemon=True)
            worker.start()
            try:
                for path in ['index.html',rows[3]['rgb_display_image'],rows[6]['rgb_display_image'],rows[3]['map_image'],'media/rgb-depth.mp4']:
                    with urlopen(f'http://127.0.0.1:{server.server_address[1]}/{path}',timeout=10) as response:
                        assert response.status == 200
                        response.read()
            finally:
                server.shutdown();worker.join()

protected = json.loads((REPORT/'protected_hashes.json').read_text())
for path,digest in protected.items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest,path
result = {'passed':True,'runs':checks,'terminal_event_alignment':True,'no_future_events':True,
          'html_video_panels_match':True,'http_assets_checked':5,'protected_files':len(protected),
          'original_browser_manual_test':False}
(REPORT/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
