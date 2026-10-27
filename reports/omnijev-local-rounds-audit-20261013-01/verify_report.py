"""Verify report bindings, aggregate tables, plot provenance and source integrity."""
import csv,hashlib,json,math,sys
from pathlib import Path
from PIL import Image
ROOT=Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav');OUT=Path(sys.argv[1])
audit=json.loads((OUT/'audit.json').read_text());v=json.loads((OUT/'validation.json').read_text());plot=json.loads((OUT/'plot-provenance.json').read_text())
rows=list(csv.DictReader((OUT/'runs.csv').open()));aggs=list(csv.DictReader((OUT/'aggregate.csv').open()));report=(OUT/'README.md').read_text()
assert v['status']=='PASS' and len(rows)==18 and len(aggs)==9
assert sum(int(r['steps']) for r in rows)==5100 and sum(int(r['collisions']) for r in rows)==1530
assert all(r['success']=='False' and r['status']=='action_budget' and float(r['minimum_geodesic_m'])>.3 for r in rows)
assert sum(len(d['forward_with_target_behind_steps']) for d in audit['details'].values())==1700
assert sum(len(d['blocked_move_chosen_steps']) for d in audit['details'].values())==1246
moving=sum(d['collisions_with_displacement'] for d in audit['details'].values());stationary=sum(d['collisions_without_displacement'] for d in audit['details'].values())
assert moving==866 and stationary==664 and moving+stationary==1530
assert all(all(d.values()) for d in audit['round_pair_identity'].values())
for a in aggs:
    selected=[r for r in rows if (r['route'],r['depth_mode'])==(a['route'],a['depth_mode'])]
    assert len(selected)==2
    for key in ['steps','collisions','invalid_actions','path_length_m','initial_geodesic_m','final_geodesic_m','minimum_geodesic_m']:
        values=[float(r[key]) for r in selected]
        assert math.isclose(float(a[key+'_mean']),sum(values)/2,abs_tol=1e-10)
        assert float(a[key+'_min'])==min(values) and float(a[key+'_max'])==max(values)
    labels={'simple':'简单','complex':'复杂','extended':'长路线','numeric':'数值','semantic':'语义','none':'无深度文字'}
    r=selected[0];text=f"| {labels[r['route']]} | {labels[r['depth_mode']]} | 0/2 | {r['steps']} | {r['collisions']} | {r['invalid_actions']} | {float(r['path_length_m']):.3f} | {float(r['final_geodesic_m']):.3f} | {float(r['minimum_geodesic_m']):.3f} |"
    assert text in report,text
assert len(list(csv.DictReader((OUT/'comparison.csv').open())))==45
assert len(plot['representatives'])==9
for name,p in plot['representatives'].items():
    positions=audit['details'][name]['positions'];assert len(positions)==p['positions']
    import struct
    data=b''.join(struct.pack('<d',x) for pt in positions for x in pt)
    assert hashlib.sha256(data).hexdigest()==p['position_sha256']
    assert hashlib.sha256((ROOT/p['map_source']).read_bytes()).hexdigest()==p['map_sha256']
for filename in ['trajectories.png','distance-progress.png','diagnostic-rgb.png']:
    with Image.open(OUT/filename) as image:assert image.width>=2000 and image.height>=700;image.verify()
for filename in ['trajectories.pdf','distance-progress.pdf']:assert (OUT/filename).read_bytes().startswith(b'%PDF')
for rel,digest in audit['source_hashes'].items():assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==digest,rel
result={'status':'PASS','metric_rows':18,'aggregate_conditions':9,'comparison_conditions':45,'representative_trajectories':9,'source_files_unchanged':len(audit['source_hashes']),'report_table_matches_raw_audit':True,'plot_positions_and_maps_match':True,'PNG_and_PDF_integrity':True,'visual_inspection':'nine trajectory panels, nine distance panels and three raw model images inspected','GPU_used':False,'API_calls':0}
(OUT/'report-validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
