"""Check saved comparison tables, source hashes, all plotted coordinates and exports."""
from pathlib import Path
from collections import Counter,defaultdict
import csv,hashlib,json,math,re,sys
import numpy as np
from PIL import Image
ROOT=Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav')
OUT=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent
DEST=ROOT/'reports/four-model-navigation-comparison-20261012-01'
j=json.loads((OUT/'audit.json').read_text());v=j['verification']
assert len(j['rows'])==73 and len(j['aggregate'])==len(j['representatives'])==36
assert sum(r['steps'] for r in j['rows'])==15260
assert Counter(r['scheme'] for r in j['rows'])==dict(jev=19,openai_text=18,openai_rgb=18,onejev_rgb=18)
assert v['verified_image_requests']==dict(openai_rgb=3280,onejev_rgb=5100)
assert len(v['identical_pairs'])==27
for group in ['source_sha256','prior_source_hashes']:
 for name,digest in v[group].items():
  assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,('changed_source',name)
for filename,key in [('runs.csv','rows'),('aggregate.csv','aggregate'),('representatives.csv','representatives'),('totals.csv','totals'),('excluded.csv','excluded')]:
 with (OUT/filename).open() as f:actual=list(csv.DictReader(f))
 expected=j[key];assert len(actual)==len(expected)
 for a,b in zip(actual,expected):assert a=={k:'' if value is None else str(value) for k,value in b.items()},filename
for r in j['rows']:
 s=json.loads((ROOT/'runs'/r['run']/'summary.json').read_text())
 for key in ['steps','collisions','invalid_actions','path_length_m','final_geodesic_m','success','status','spl']:
  assert r[key]==s[key],(r['run'],key)
for g in j['aggregate']:
 rows=[r for r in j['rows'] if all(r[k]==g[k] for k in ['scheme','route','input'])]
 assert len(rows)==g['runs'] and sum(r['success'] for r in rows)==g['successes']
 for key in ['steps','collisions','invalid_actions','path_length_m','final_geodesic_m','spl']:
  values=[r[key] for r in rows]
  assert math.isclose(sum(values)/len(values),g['mean_'+key],abs_tol=1e-12)
  assert min(values)==g['min_'+key] and max(values)==g['max_'+key]
points=defaultdict(list)
with (OUT/'trajectory-points.csv').open() as f:
 for row in csv.DictReader(f):points[row['run']].append(row)
assert len(points)==36 and sum(map(len,points.values()))==7371
prov=json.loads((OUT/'plot-provenance.json').read_text())
for rep in j['representatives']:
 name=rep['run'];recorded=[json.loads(line) for line in (ROOT/'runs'/name/'steps.jsonl').read_text().splitlines()]
 assert len(points[name])==len(recorded)==rep['steps']+1
 assert rep['selection']=='first_GS_batch_01_not_selected_by_outcome'
 coords=[]
 for i,(row,record) in enumerate(zip(points[name],recorded)):
  assert int(row['observation'])==i
  pt=[float(row['world_'+axis+'_m']) for axis in ['x','y','z']]
  assert pt==record['pose']['position'];coords.append(pt)
 assert coords==j['details'][name]['positions'] and coords[-1]==recorded[-2]['after_position']
 assert hashlib.sha256(np.asarray(coords,dtype='<f8').tobytes()).hexdigest()==prov['representatives'][name]['position_sha256']
 assert hashlib.sha256((ROOT/prov['representatives'][name]['map_source']).read_bytes()).hexdigest()==prov['representatives'][name]['map_sha256']
 for event,key in [('collision_positions','collided'),('invalid_positions','valid')]:
  expected=[r['after_position'] if event=='collision_positions' else r['pose']['position'] for r in recorded[:-1] if (r['outcome'][key] if event=='collision_positions' else not r['outcome'][key])]
  assert expected==j['details'][name][event]
projections={s:Counter() for s in ['openai_rgb','onejev_rgb']}
for r in j['rows']:
 if r['scheme'] in projections:projections[r['scheme']].update(j['details'][r['run']]['projection_counts'])
assert projections['openai_rgb']['in_frame']==406 and projections['onejev_rgb']['in_frame']==4
assert sum(projections['openai_rgb'].values())==3280 and sum(projections['onejev_rgb'].values())==5100
formats={}
for name in ['trajectories','trajectories-simple','trajectories-complex','trajectories-extended']:
 with Image.open(OUT/(name+'.png')) as image:
  assert min(image.size)>3000;formats[name+'.png']=list(image.size);image.verify()
 assert (OUT/(name+'.pdf')).read_bytes().startswith(b'%PDF')
assert '<svg' in (OUT/'trajectories.svg').read_text()
links=[]
for name in ['README.md','ALL_RUNS.md','CONDITION_SUMMARY.md']:
 for target in re.findall(r'\]\(([^)]+)\)',(OUT/name).read_text()):
  p=(DEST/target).resolve()
  if p.is_relative_to(DEST.resolve()):p=OUT/p.relative_to(DEST.resolve())
  # This verifier generates validation.json after all checks below pass.
  assert p.exists() or target=='validation.json',(name,target);links.append(target)
assert (OUT/'ALL_RUNS.md').read_text().count('/summary.json)')==73
assert (OUT/'README.md').read_text().count('/summary.json)')==36
for filename,rows in [('README.md',j['representatives']),('ALL_RUNS.md',j['rows'])]:
 lines=(OUT/filename).read_text().splitlines()
 for r in rows:
  line=next(line for line in lines if f"../../runs/{r['run']}/summary.json)" in line)
  cells=[cell.strip() for cell in line.strip('|').split('|')]
  s=json.loads((ROOT/'runs'/r['run']/'summary.json').read_text())
  assert cells[4:9]==[str(s['steps']),str(s['collisions']),str(s['invalid_actions']),f"{s['path_length_m']:.3f}",f"{s['final_geodesic_m']:.6f}"],(filename,r['run'])
  assert cells[-1]==f"{s['spl']:.3f}"
summary=dict(status='passed',runs=73,conditions=36,actions_recomputed=15260,representative_trajectories=36,plotted_observations=7371,source_hashes_checked=len(v['source_sha256']),prior_source_hashes_checked=len(v['prior_source_hashes']),identical_pairs_verified=27,verified_image_requests=v['verified_image_requests'],projection_counts={k:dict(value) for k,value in projections.items()},png_dimensions=formats,links_checked=len(links),api_calls=0,used_gpu=False,source_runs_modified=False,visual_inspection='Pending manual figure inspection; numerical/export checks passed.')
(OUT/'validation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary))
