"""Draw recorded trajectories and geodesic progress; no interpolation or GPU."""
from pathlib import Path
from matplotlib.lines import Line2D
from matplotlib.patches import Circle
import csv,hashlib,json,sys
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav');OUT=Path(sys.argv[1])
audit=json.loads((OUT/'audit.json').read_text());rows=list(csv.DictReader((OUT/'runs.csv').open()))
ROUTES=['simple','complex','extended'];MODES=['numeric','semantic','none'];labels={'numeric':'Numeric depth','semantic':'Semantic depth','none':'No depth summary'}
names={(r['route'],r['depth_mode']):r for r in rows if r['round']=='01'}
plt.rcParams.update({'font.size':10,'savefig.dpi':170,'pdf.fonttype':42})
provenance={};bounds={}
for route in ROUTES:
    ds=[audit['details'][names[route,mode]['run']] for mode in MODES]
    p=np.concatenate([np.asarray(ds[0]['task']['path'])]+[np.asarray(d['positions']) for d in ds])[:,[0,2]]
    bounds[route]=(p.min(axis=0)-.7,p.max(axis=0)+.7)
fig,axes=plt.subplots(3,3,figsize=(17,18))
for ri,route in enumerate(ROUTES):
 for mi,mode in enumerate(MODES):
    ax=axes[ri,mi];row=names[route,mode];name=row['run'];d=audit['details'][name];t=d['task'];mp=d['map']
    mapfile=ROOT/'runs'/name/'navmap.png';img=np.asarray(Image.open(mapfile))
    extent=[mp['origin_x'],mp['origin_x']+img.shape[1]*mp['resolution_m'],mp['origin_z']+img.shape[0]*mp['resolution_m'],mp['origin_z']]
    ax.imshow(img,extent=extent,interpolation='nearest');ref=np.asarray(t['path']);pts=np.asarray(d['positions'])
    assert len(pts)==int(row['steps'])+1
    ax.plot(ref[:,0],ref[:,2],'--',color='#069bb5',lw=2,label='Reference route',zorder=2)
    ax.plot(pts[:,0],pts[:,2],color='#5242aa',lw=1.8,alpha=.92,label='Executed route',zorder=3)
    ax.scatter(t['start'][0],t['start'][2],marker='s',s=65,color='#16754b',edgecolors='white',zorder=8)
    ax.scatter(t['goal'][0],t['goal'][2],marker='*',s=160,color='#ce2942',edgecolors='white',zorder=8)
    ax.add_patch(Circle((t['goal'][0],t['goal'][2]),.3,fill=False,color='#ce2942',lw=1.3,zorder=6))
    ax.scatter(pts[-1,0],pts[-1,2],marker='X',s=70,color='#5242aa',edgecolors='black',zorder=9)
    c=np.asarray(d['collision_positions'])
    if len(c):ax.scatter(c[:,0],c[:,2],marker='x',s=22,color='#e2471d',lw=1,alpha=.6,zorder=7)
    lo,hi=bounds[route];ax.set_xlim(lo[0],hi[0]);ax.set_ylim(hi[1],lo[1]);ax.set_aspect('equal');ax.grid(alpha=.15)
    ax.set_xlabel('World X (m)');ax.set_ylabel('World Z (m)')
    ax.set_title(f"{route.title()} / {labels[mode]}\nFAIL; {row['steps']} actions, {row['collisions']} collisions, 0 invalid\ntravel {float(row['path_length_m']):.2f} m; final {float(row['final_geodesic_m']):.3f} m",fontsize=11)
    provenance[name]={'positions':len(pts),'position_sha256':hashlib.sha256(np.asarray(pts,dtype='<f8').tobytes()).hexdigest(),'map_source':str(mapfile.relative_to(ROOT)),'map_sha256':hashlib.sha256(mapfile.read_bytes()).hexdigest(),'reference_path':t['path']}
handles=[Line2D([0],[0],ls='--',color='#069bb5',lw=2,label='Reference route'),Line2D([0],[0],color='#5242aa',lw=2,label='Executed route'),Line2D([0],[0],ls='',marker='s',color='#16754b',label='Start'),Line2D([0],[0],ls='',marker='*',color='#ce2942',label='Goal (0.30 m circle)'),Line2D([0],[0],ls='',marker='X',color='#5242aa',label='Failure endpoint'),Line2D([0],[0],ls='',marker='x',color='#e2471d',label='Collision observation')]
fig.suptitle('OmniJev-4B: all nine navigation conditions failed',fontsize=19,y=.989)
fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.024),ncol=3,fontsize=11)
fig.text(.5,.008,'Representative: local-round-01. Round 02 has identical positions and actions. Rotations do not extend the trajectory line.',ha='center',fontsize=10)
fig.tight_layout(rect=(0,.068,1,.968),h_pad=3,w_pad=2)
for suffix in ['png','pdf']:fig.savefig(OUT/f'trajectories.{suffix}')
plt.close(fig)

fig,axes=plt.subplots(3,3,figsize=(16,12))
for ri,route in enumerate(ROUTES):
 for mi,mode in enumerate(MODES):
    ax=axes[ri,mi];row=names[route,mode];name=row['run'];records=[json.loads(s) for s in (ROOT/'runs'/name/'steps.jsonl').read_text().splitlines()]
    dist=[float(row['initial_geodesic_m'])]+[r['metrics']['distance_to_goal_geodesic_m'] for r in records[:-1]]
    ax.plot(range(len(dist)),dist,color='#5242aa',lw=1.7)
    collision_indices=[r['step']+1 for r in records[:-1] if r['outcome']['collided']]
    ax.scatter(collision_indices,[dist[i] for i in collision_indices],marker='x',color='#e2471d',s=16,alpha=.6)
    ax.axhline(.3,color='#ce2942',ls='--',lw=1,label='Success tolerance')
    best=int(np.argmin(dist));ax.scatter(best,dist[best],color='#16754b',s=35,zorder=4)
    ax.set_title(f'{route.title()} / {labels[mode]}',fontsize=12);ax.set_xlabel('Executed action count');ax.set_ylabel('Remaining geodesic distance (m)')
    ax.set_xlim(0,int(row['steps']));ax.set_ylim(0,max(float(r['initial_geodesic_m']) for r in rows if r['route']==route)*1.5);ax.grid(alpha=.18)
    ax.text(.98,.97,f"closest {float(row['minimum_geodesic_m']):.3f} m\nfinal {float(row['final_geodesic_m']):.3f} m",ha='right',va='top',transform=ax.transAxes,fontsize=10)
fig.suptitle('Remaining goal distance: progress reversals and stationary plateaus',fontsize=18,y=.99)
fig.text(.5,.012,'Purple: recorded distance after each action; orange x: collision; green dot: closest approach. Round 02 is identical.',ha='center',fontsize=10)
fig.tight_layout(rect=(0,.04,1,.962))
for suffix in ['png','pdf']:fig.savefig(OUT/f'distance-progress.{suffix}')
plt.close(fig)

samples=[('Simple numeric, action 14','simple','numeric',13),('Complex no-depth, action 249','complex','none',248),('Long no-depth, action 498','extended','none',497)]
fig,axes=plt.subplots(1,3,figsize=(18,5.4))
sample_sources=[]
for ax,(label,route,mode,index) in zip(axes,samples):
    name=names[route,mode]['run'];image_path=ROOT/'runs'/name/'frames'/f'{index:05d}-model-rgb.jpg'
    ax.imshow(Image.open(image_path));ax.axis('off');ax.set_title(label,fontsize=13)
    sample_sources.append({'run':name,'record_index':index,'image_path':str(image_path.relative_to(ROOT)),'image_sha256':hashlib.sha256(image_path.read_bytes()).hexdigest()})
fig.suptitle('Actual current-view images sent to the model',fontsize=17,y=.98)
fig.text(.5,.025,'Original saved marked JPEGs; captions are report-only. An in-frame marker does not prove a collision-free route.',ha='center',fontsize=11)
fig.tight_layout(rect=(0,.055,1,.91));fig.savefig(OUT/'diagnostic-rgb.png');plt.close(fig)
(OUT/'plot-provenance.json').write_text(json.dumps({'representatives':provenance,'bounds_by_route':{r:[p.tolist() for p in bounds[r]] for r in ROUTES},'sample_images':sample_sources,'representative_rule':'always local-round-01; all paired round-02 sequences identical','coordinate_frame':'recorded world X/Z; Z increases downward','interpolated':False,'smoothed':False,'GPU_used':False,'API_calls':0},indent=2)+'\n')
print('PASS 9 recorded trajectories, 9 progress panels and 3 actual input image examples')
