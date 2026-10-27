"""Export selected recorded X/Z trajectories; no simulator, API or interpolation."""
from pathlib import Path
from collections import Counter
import csv,hashlib,json,sys
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle
ROOT=Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav')
OUT=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent;j=json.loads((OUT/'audit.json').read_text())
ROUTES=['simple','complex','extended'];MODES=['numeric','semantic','none'];SCHEMES=['jev','openai_text','openai_rgb','onejev_rgb']
LABELS={'jev':'Jev','openai_text':'OpenAI text','openai_rgb':'OpenAI RGB + text','onejev_rgb':'OneJev-4B RGB + text'}
ML={'numeric':'Numeric depth','semantic':'Semantic depth','none':'No depth summary'}
C={'jev':'#17946b','openai_text':'#df732d','openai_rgb':'#7655c7','onejev_rgb':'#235b9c'}
STYLES={'jev':'--','openai_text':':','openai_rgb':'-','onejev_rgb':'-.'}
reps={(r['route'],r['input'],r['scheme']):r for r in j['representatives']}
plt.rcParams.update({'font.size':10,'savefig.dpi':190,'axes.spines.top':True,'axes.spines.right':True,'pdf.fonttype':42,'svg.fonttype':'none'})
backgrounds={};bounds={};provenance={};points_csv=[]
for route in ROUTES:
 r=reps[route,'numeric','jev'];d=j['details'][r['run']];mp=d['map'];p=ROOT/'runs'/r['run']/'navmap.png';img=np.asarray(Image.open(p))
 extent=[mp['origin_x'],mp['origin_x']+img.shape[1]*mp['resolution_m'],mp['origin_z']+img.shape[0]*mp['resolution_m'],mp['origin_z']]
 backgrounds[route]=(img,extent,d['task'])
 allpts=[np.asarray(d['task']['path'])]
 for mode in MODES:
  for scheme in SCHEMES:
   r=reps[route,mode,scheme];dd=j['details'][r['run']];assert dd['map']==mp
   pts=np.asarray(dd['positions']);allpts.append(pts)
   provenance[r['run']]={'position_sha256':hashlib.sha256(np.asarray(pts,dtype='<f8').tobytes()).hexdigest(),'positions':len(pts),'expected_steps_plus_terminal':r['steps']+1,'drawn_reference_path':dd['task']['path'],'map_source':str(p.relative_to(ROOT)),'map_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
   assert len(pts)==r['steps']+1
   for i,pt in enumerate(pts):points_csv.append({'scheme':scheme,'route':route,'input':mode,'run':r['run'],'observation':i,'world_x_m':pt[0],'world_y_m':pt[1],'world_z_m':pt[2]})
 xz=np.concatenate(allpts)[:,[0,2]];lo=xz.min(axis=0)-.7;hi=xz.max(axis=0)+.7
 # Identical crop per route across all input/model panels.
 bounds[route]=(lo,hi)
def base(ax,route):
 img,extent,t=backgrounds[route];ax.imshow(img,extent=extent,interpolation='nearest',zorder=0)
 path=np.asarray(t['path']);ax.plot(path[:,0],path[:,2],'--',color='#179bc0',lw=1.7,zorder=1)
 ax.scatter(t['start'][0],t['start'][2],marker='s',s=60,color='#1c4e31',edgecolor='white',linewidth=.8,zorder=7)
 ax.scatter(t['goal'][0],t['goal'][2],marker='*',s=130,color='#bd2536',edgecolor='white',linewidth=.5,zorder=7)
 ax.add_patch(Circle((t['goal'][0],t['goal'][2]),.3,fill=False,color='#bd2536',lw=1.3,zorder=6))
 lo,hi=bounds[route];ax.set_xlim(lo[0],hi[0]);ax.set_ylim(hi[1],lo[1]);ax.set_aspect('equal');ax.grid(alpha=.13)
 ax.set_xlabel('World X (m)');ax.set_ylabel('World Z (m)')
def draw(ax,r,events=True):
 d=j['details'][r['run']];p=np.asarray(d['positions']);color=C[r['scheme']]
 ax.plot(p[:,0],p[:,2],color=color,lw=1.8,ls=STYLES[r['scheme']],alpha=.86,zorder=3)
 ax.scatter(p[-1,0],p[-1,2],marker='o' if r['success'] else 'X',s=64,color=color,edgecolor='black',linewidth=.65,zorder=8)
 if events:
  for key,marker,color2,size in [('collision_positions','x','#ed2226',38),('invalid_positions','^','#f0bd38',45)]:
   q=np.asarray(d[key])
   if len(q):ax.scatter(q[:,0],q[:,2],marker=marker,color=color2,s=size,zorder=9,linewidths=1.2,edgecolors='black' if marker=='^' else None)
curve_handles=[Line2D([0],[0],color=C[k],lw=2,ls=STYLES[k],label=LABELS[k]) for k in SCHEMES]+[Line2D([0],[0],color='#179bc0',lw=1.8,ls='--',label='Reference route')]
event_handles=[Line2D([0],[0],color='#1c4e31',marker='s',ls='',label='Start'),Line2D([0],[0],color='#bd2536',marker='*',ls='',label='Goal / 0.30 m circle'),Line2D([0],[0],color='black',marker='o',ls='',label='Success endpoint'),Line2D([0],[0],color='black',marker='X',ls='',label='Failure endpoint'),Line2D([0],[0],color='#ed2226',marker='x',ls='',label='Collision observation'),Line2D([0],[0],color='#f0bd38',marker='^',ls='',label='Invalid-action observation')]
fig,axes=plt.subplots(3,3,figsize=(18,18))
for ri,route in enumerate(ROUTES):
 for mi,mode in enumerate(MODES):
  ax=axes[ri,mi];base(ax,route)
  # Vision first, dashed Jev last, making overlapping paths distinguishable.
  for scheme in ['openai_rgb','openai_text','jev','onejev_rgb']:draw(ax,reps[route,mode,scheme],events=False)
  stat=[]
  for scheme in SCHEMES:
   r=reps[route,mode,scheme];stat.append(f"{LABELS[scheme]}: {'OK' if r['success'] else 'FAIL'}, {r['steps']} acts, {r['collisions']} hits")
  ax.text(.02,.98,'\n'.join(stat),transform=ax.transAxes,va='top',fontsize=8.5,bbox=dict(facecolor='white',edgecolor='none',alpha=.86))
  ax.set_title(f'{route.title()} route / {ML[mode]}',fontsize=12)
fig.suptitle('Four navigation decision schemes: representative recorded trajectories',fontsize=17,y=.985)
fig.legend(handles=curve_handles,loc='lower center',bbox_to_anchor=(.5,.039),ncol=5,fontsize=10)
fig.legend(handles=event_handles[:4],loc='lower center',bbox_to_anchor=(.5,.012),ncol=4,fontsize=10)
fig.text(.5,.004,'First GS batch 01 per condition; OneJev local-round-01. All 73 runs, including failures, remain in the result tables.',ha='center',fontsize=10)
fig.tight_layout(rect=(0,.07,1,.967))
for suffix in ['png','pdf','svg']:fig.savefig(OUT/f'trajectories.{suffix}')
plt.close(fig)
for route in ROUTES:
 fig,axes=plt.subplots(4,3,figsize=(17,25))
 for si,scheme in enumerate(SCHEMES):
  for mi,mode in enumerate(MODES):
   r=reps[route,mode,scheme];ax=axes[si,mi];base(ax,route);draw(ax,r,events=True)
   ax.set_title(f"{LABELS[scheme]} / {ML[mode]}\n{r['status']}; {r['steps']} acts, {r['collisions']} hits, {r['invalid_actions']} invalid\ntravel {r['path_length_m']:.3f} m; final {r['final_geodesic_m']:.6f} m; turns {r['turn_actions']}",fontsize=10)
 fig.suptitle(f'{route.title()} route: models by depth input',fontsize=17,y=.987)
 fig.legend(handles=curve_handles[-1:]+event_handles,loc='lower center',bbox_to_anchor=(.5,.027),ncol=4,fontsize=9)
 fig.text(.5,.006,'Rows: Jev / OpenAI text / OpenAI RGB + text / OneJev-4B RGB + text. Columns: numeric / semantic / no depth.',ha='center',fontsize=9)
 fig.text(.5,.014,'Rotations and pitch actions do not move the trajectory line. Event markers are recorded robot positions.',ha='center',fontsize=9)
 fig.tight_layout(rect=(0,.065,1,.97), h_pad=5.0, w_pad=2.0)
 for suffix in ['png','pdf']:fig.savefig(OUT/f'trajectories-{route}.{suffix}')
 plt.close(fig)
with (OUT/'trajectory-points.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(points_csv[0]));w.writeheader();w.writerows(points_csv)
(OUT/'plot-provenance.json').write_text(json.dumps({'representatives':provenance,'bounds_by_route':{r:[x.tolist() for x in bounds[r]] for r in ROUTES},'coordinate_frame':'recorded world X/Z; Z increases downward as in the supplied reference figure','interpolation':False,'line_smoothing':False,'deduplicated_points':False,'collision_marker':'agent observation after movement filtering, not exact physical contact','success_circle':'illustrative horizontal radius; evaluation uses NavMesh geodesic distance','used_gpu':False,'api_calls':0},indent=2)+'\n')
print('PLOTS 9-cell overlay + 3 route figures, 36 representative trajectories,',len(points_csv),'recorded observations')
