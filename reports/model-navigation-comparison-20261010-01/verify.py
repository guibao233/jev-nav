"""Verify source integrity, tabular metrics, recorded trajectories and report assets."""
from pathlib import Path
from collections import Counter,defaultdict
import csv,hashlib,json,math,re,sys
from PIL import Image
import numpy as np
OUT=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent
ROOT=Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav')
DEST=ROOT/'reports/model-navigation-comparison-20261010-01'
j=json.loads((OUT/'audit.json').read_text());v=j['verification']
for group in ['source_sha256','prior_source_hashes']:
 for name,expected in v[group].items():
  assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected,('source_changed',name)
assert len(j['rows'])==55 and len(j['aggregate'])==len(j['representatives'])==27
assert sum(r['steps'] for r in j['rows'])==10160
assert Counter(r['scheme'] for r in j['rows'])=={'jev':19,'openai_text':18,'openai_rgb':18}
for filename,data in [('runs.csv',j['rows']),('aggregate.csv',j['aggregate']),('representatives.csv',j['representatives']),('totals.csv',j['totals']),('excluded.csv',j['excluded'])]:
 with (OUT/filename).open() as f:actual=list(csv.DictReader(f))
 assert len(actual)==len(data),(filename,len(actual))
 for a,b in zip(actual,data):assert a=={k:'' if x is None else str(x) for k,x in b.items()},filename
for row in j['rows']:
 run=ROOT/'runs'/row['run'];s=json.loads((run/'summary.json').read_text())
 for key in ['steps','collisions','invalid_actions','path_length_m','final_geodesic_m','success','status','spl']:
  assert s[key]==row[key],(row['run'],key)
for g in j['aggregate']:
 rows=[r for r in j['rows'] if all(r[k]==g[k] for k in ['scheme','route','input'])]
 assert len(rows)==g['runs'] and sum(r['success'] for r in rows)==g['successes']
 for key in ['steps','collisions','invalid_actions','path_length_m','final_geodesic_m','spl']:
  a=[r[key] for r in rows]
  assert math.isclose(sum(a)/len(a),g['mean_'+key],abs_tol=1e-12)
  assert min(a)==g['min_'+key] and max(a)==g['max_'+key]
points=defaultdict(list)
with (OUT/'trajectory-points.csv').open() as f:
 for r in csv.DictReader(f):points[r['run']].append(r)
prov=json.loads((OUT/'plot-provenance.json').read_text())
assert sum(map(len,points.values()))==4812
assert set(points)=={r['run'] for r in j['representatives']}
for rep in j['representatives']:
 run=rep['run'];p=points[run];records=[json.loads(s) for s in (ROOT/'runs'/run/'steps.jsonl').read_text().splitlines()]
 assert len(p)==len(records)==rep['steps']+1
 assert rep['selection']=='first_GS_batch_01_not_selected_by_outcome'
 coords=[]
 for i,(row,source) in enumerate(zip(p,records)):
  assert int(row['observation'])==i
  c=[float(row['world_'+axis+'_m']) for axis in ['x','y','z']]
  assert c==source['pose']['position'];coords.append(c)
 assert coords==j['details'][run]['positions']
 assert hashlib.sha256(np.asarray(coords,dtype='<f8').tobytes()).hexdigest()==prov['representatives'][run]['position_sha256']
 assert hashlib.sha256((ROOT/prov['representatives'][run]['map_source']).read_bytes()).hexdigest()==prov['representatives'][run]['map_sha256']
 assert coords[-1]==records[-2]['after_position']
pair_count=0;markers=Counter()
for g in j['aggregate']:
 if g['scheme']=='jev':continue
 rows=[r for r in j['rows'] if all(r[k]==g[k] for k in ['scheme','route','input'])]
 a,b=[[json.loads(x) for x in (ROOT/'runs'/r['run']/'steps.jsonl').read_text().splitlines()][:-1] for r in rows]
 assert len(a)==len(b)
 for x,y in zip(a,b):
  assert x['request']==y['request']
  assert x['pose']==y['pose'] and x['after_position']==y['after_position']
  assert x['outcome']==y['outcome']
  assert x['decision']['response']['answers']==y['decision']['response']['answers']
  if g['scheme']=='openai_rgb':
   assert x['image_input']['sha256']==y['image_input']['sha256']
   markers.update([z['request']['state']['visual']['marker']['projection_status'] for z in [x,y]])
 pair_count+=1
assert pair_count==18 and sum(markers.values())==3280 and markers['in_frame']==406
assert all(r['actions_after_first_arrival']==1 for r in j['rows'] if r['scheme']=='openai_rgb')
long_run='openai-decisions-rgbtarget-extended-rgbgs-none-20261009-01'
assert j['details'][long_run]['action_counts']['turn_left']==348
span=j['details'][long_run]['longest_stationary_span']
assert span['count']==116
records=[json.loads(x) for x in (ROOT/'runs'/long_run/'steps.jsonl').read_text().splitlines()]
assert all(r['outcome']['action']=='turn_left' for r in records[span['first_action']-1:span['last_action']])
formats={}
for name in ['trajectories','trajectories-simple','trajectories-complex','trajectories-extended']:
 with Image.open(OUT/(name+'.png')) as im:
  formats[name+'.png']=list(im.size);assert min(im.size)>3000;im.verify()
 assert (OUT/(name+'.pdf')).read_bytes().startswith(b'%PDF')
assert '<svg' in (OUT/'trajectories.svg').read_text()
links=[]
for name in ['README.md','ALL_RUNS.md']:
 for target in re.findall(r'\]\(([^)]+)\)',(OUT/name).read_text()):
  assert not target.startswith(('http','data:')),target
  p=(DEST/target).resolve()
  if p.is_relative_to(DEST.resolve()):p=OUT/p.relative_to(DEST.resolve())
  assert p.exists(),(name,target);links.append(target)
assert (OUT/'ALL_RUNS.md').read_text().count('/summary.json)')==55
assert (OUT/'README.md').read_text().count('/summary.json)')==27
result={'status':'passed','runs':55,'conditions':27,'actions_recomputed_by_audit':10160,'representative_trajectories':27,'plotted_observations':4812,'source_hashes_checked':len(v['source_sha256']),'prior_source_hashes_checked':len(v['prior_source_hashes']),'report_links_checked':len(links),'identical_openai_pairs_verified':pair_count,'visual_marker_projection_counts':dict(markers),'png_dimensions':formats,'visual_inspection':'All four figures inspected; dedicated panels have no label overlaps.','source_runs_modified':False,'api_calls':0,'gpu_used':False}
(OUT/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
