from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
OUT=Path(__file__).resolve().parent
j=json.loads((OUT/'audit.json').read_text())
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':180})
fig,axes=plt.subplots(3,3,figsize=(14,10),sharey='row',sharex='row')
for ri,route in enumerate(['simple','complex','extended']):
 for mi,mode in enumerate(['numeric','semantic','none']):
  ax=axes[ri,mi]
  for arm,color,label in [('text','#c14b43','Text only'),('rgb','#1469ad','RGB + marker + text')]:
   row=next(r for r in j['rows'] if r['arm']==arm and r['route']==route and r['input']==mode and r['batch']=='01')
   series=j['details'][row['run']]['distance_series_m']
   ax.plot(np.arange(len(series)),series,color=color,lw=1.5,label=label)
   ax.scatter([len(series)-1],[series[-1]],color=color,s=24,marker='o' if row['success'] else 'x',zorder=3)
  ax.axhline(.3,color='#666666',lw=.8,ls='--',label='Stop tolerance 0.30 m')
  ax.set_title(f'{route.title()} / {mode.title() if mode!="none" else "No depth"}')
  ax.set_xlim(0,dict(simple=100,complex=250,extended=500)[route])
  ax.set_ylim(bottom=-.2);ax.grid(alpha=.18)
  if mi==0:ax.set_ylabel('Geodesic distance to goal (m)')
  if ri==2:ax.set_xlabel('Executed actions')
handles,labels=axes[0,0].get_legend_handles_labels()
fig.legend(handles,labels,loc='lower center',ncol=3,bbox_to_anchor=(.5,.002))
fig.suptitle('OpenAI Decisions: goal distance with and without marked RGB',fontsize=16)
fig.text(.5,.045,'Both repeats have identical trajectories in each condition; one curve represents both. End markers: circle = success, x = failure.',ha='center',fontsize=9)
fig.tight_layout(rect=(0,.065,1,.96));fig.savefig(OUT/'goal-distance-comparison.png');plt.close(fig)
fig,axes=plt.subplots(1,3,figsize=(14,5.2),sharey=True)
categories=[('translate','#258878'),('turn','#db9d43'),('pitch','#8079ae'),('stop','#646b79')]
for ax,route in zip(axes,['simple','complex','extended']):
 for mi,mode in enumerate(['numeric','semantic','none']):
  for arm,offset in [('text',-.18),('rgb',.18)]:
   row=next(r for r in j['rows'] if r['arm']==arm and r['route']==route and r['input']==mode and r['batch']=='01')
   counts=j['details'][row['run']]['action_counts'];bottom=0
   values={'translate':sum(counts.get(k,0) for k in ['move_forward','move_backward']),'turn':sum(counts.get(k,0) for k in ['turn_left','turn_right']),'pitch':sum(counts.get(k,0) for k in ['look_down','look_up']),'stop':counts.get('stop',0)}
   for cat,color in categories:
    ax.bar(mi+offset,values[cat],bottom=bottom,width=.31,color=color,label=cat if mi==0 and arm=='text' else None,hatch='//' if arm=='text' else None)
    bottom+=values[cat]
   ax.text(mi+offset,bottom+5,str(row['steps']),ha='center',fontsize=9)
 ax.set_xticks([0,1,2],['Numeric','Semantic','No depth']);ax.set_title(route.title());ax.grid(axis='y',alpha=.18)
axes[0].set_ylabel('Actions per run');axes[0].set_ylim(0,465)
fig.legend(*axes[0].get_legend_handles_labels(),loc='lower center',ncol=4,bbox_to_anchor=(.5,.005))
fig.suptitle('Where the action budget goes',fontsize=16)
fig.text(.5,.09,'Left hatched bars: text only. Right solid bars: RGB + marker + text. Counts include invalid actions.',ha='center',fontsize=10)
fig.tight_layout(rect=(0,.15,1,.95));fig.savefig(OUT/'action-breakdown.png');plt.close(fig)
print('Rendered 2 figures from audited rows')
