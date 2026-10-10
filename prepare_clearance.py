#!/usr/bin/env python3
"""Create independent clearance-weighted tasks and previews; CPU only, no API."""
import argparse
import copy
import hashlib
from html import escape
import json
from pathlib import Path

import numpy as np
from clearance import ClearancePlanner, VERSION, path_statistics
from environment import load_pathfinder, shortest
from run import ROOT, load_config


def route_preview(pf, task, destination):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    nav = pf.get_topdown_view(.05, float(task['start'][1]))
    low,_ = pf.get_bounds()
    fig,ax = plt.subplots(figsize=(9,8), constrained_layout=True)
    ax.imshow(nav, cmap=ListedColormap(['#343b45','#e5e8ed']), vmin=0, vmax=1,
              extent=[low[0],low[0]+nav.shape[1]*.05,low[2]+nav.shape[0]*.05,low[2]])
    old,new = np.asarray(task['shortest_path']),np.asarray(task['path'])
    ax.plot(old[:,0],old[:,2],color='#ab6ae0',lw=2,ls='--',label='Original shortest path')
    ax.plot(new[:,0],new[:,2],color='#2875ed',lw=2.5,marker='.',ms=5,label='Clearance-weighted reference')
    for name,color,label in [('start','#16a154','S'),('goal','#d32a34','G')]:
        p=task[name];ax.scatter(p[0],p[2],s=70,color=color,zorder=5);ax.annotate(label,(p[0],p[2]),xytext=(8,6),textcoords='offset points')
    all_points=np.concatenate([old,new])
    ax.set_xlim(all_points[:,0].min()-.8,all_points[:,0].max()+.8)
    ax.set_ylim(all_points[:,2].max()+.8,all_points[:,2].min()-.8)
    ax.set_aspect('equal');ax.set_xlabel('World X (m)');ax.set_ylabel('World Z (m)')
    ax.set_title(f"{task['id']}: shortest {task['geodesic_m']:.2f} m / reference {task['reference_path_length_m']:.2f} m")
    ax.legend(loc='upper right',fontsize=8);ax.grid(alpha=.15)
    fig.savefig(destination,dpi=140);plt.close(fig)


def build_dataset(dataset, pf, selected, grid_m=.1, clearance_m=.2, weight=4., padding_m=2.):
    result=copy.deepcopy(dataset)
    result['tasks']=[]
    for original in dataset['tasks']:
        if original['id'] not in selected:continue
        task=copy.deepcopy(original)
        seed=task.get('shortest_path',task['path'])
        path=shortest(pf,task['start'],task['goal'])
        if path is None or abs(path[0]-task['geodesic_m'])>.02:
            raise ValueError('task shortest-distance baseline does not match current NavMesh')
        print(f"[plan] {task['id']}: clearance-weighted grid search",flush=True)
        planner=ClearancePlanner(pf,seed,grid_m,clearance_m,weight,padding_m)
        reference,stats=planner.plan()
        task['shortest_path']=copy.deepcopy(seed)
        task['path']=reference
        task['reference_path_kind']='clearance_weighted'
        task['reference_planner']=dict(planner.parameters,search=stats)
        task['reference_statistics']={'original_shortest':path_statistics(pf,seed),
                                      'clearance_weighted':path_statistics(pf,reference)}
        task['reference_path_length_m']=task['reference_statistics']['clearance_weighted']['length_m']
        result['tasks'].append(task)
        print('[verified]',task['id'],json.dumps(task['reference_statistics']),flush=True)
    if len(result['tasks'])!=len(selected):
        raise ValueError('unknown or duplicate task selection')
    result['reference_path_kind']='clearance_weighted'
    result['reference_planner_version']=VERSION
    result['evaluation_baseline']='geodesic_m and shortest_path remain the original NavMesh shortest path; path is the supplied reference'
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default=str(ROOT/'config.json'))
    parser.add_argument('--tasks',required=True)
    parser.add_argument('--episode',action='append',help='repeat to select several; omit for all tasks')
    parser.add_argument('--out',required=True)
    parser.add_argument('--grid-m',type=float,default=.1)
    parser.add_argument('--clearance-m',type=float,default=.2,help='soft cost decay scale, not a guaranteed minimum')
    parser.add_argument('--weight',type=float,default=4.)
    parser.add_argument('--padding-m',type=float,default=2.)
    args=parser.parse_args()
    out=Path(args.out)
    if out.exists():raise FileExistsError(out)
    source=Path(args.tasks);dataset=json.loads(source.read_text())
    cfg=load_config(args.config);pf=load_pathfinder(cfg)
    nav=Path(cfg['scene_dir'])/'shuyuan.navmesh'
    digest=hashlib.sha256(nav.read_bytes()).hexdigest()
    expected=dataset.get('assets',{}).get(nav.name,{}).get('sha256')
    if expected and expected!=digest:raise ValueError('NavMesh differs from source tasks')
    ids={t['id'] for t in dataset['tasks']}
    selected=set(args.episode) if args.episode else ids
    if not selected<=ids:raise ValueError(f'unknown task IDs: {sorted(selected-ids)}')
    result=build_dataset(dataset,pf,selected,args.grid_m,args.clearance_m,args.weight,args.padding_m)
    result['source_tasks']={'path':str(source.resolve()),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
    result['reference_generator_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ('prepare_clearance.py','clearance.py')}
    out.mkdir(parents=True,exist_ok=False)
    (out/'maps').mkdir()
    (out/'tasks.json').write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    cards=[];table=['| 任务 | 原最短长度 m | 新参考长度 m | 原/新最小额外余量 m |','|---|---:|---:|---:|']
    for task in result['tasks']:
        route_preview(pf,task,out/'maps'/f"{task['id']}.png")
        old,new=task['reference_statistics']['original_shortest'],task['reference_statistics']['clearance_weighted']
        table.append(f"| {task['id']} | {task['geodesic_m']:.3f} | {task['reference_path_length_m']:.3f} | {old['extra_navmesh_clearance_min_m']:.3f} / {new['extra_navmesh_clearance_min_m']:.3f} |")
        cards.append(f'<h2>{escape(task["id"])}</h2><img src="maps/{escape(task["id"])}.png" style="max-width:100%;width:900px">')
    (out/'index.html').write_text('<!doctype html><html lang="zh"><meta charset="utf-8"><title>居中参考路线</title><body style="font:16px system-ui;margin:24px"><h1>居中参考路线计划预览</h1><p>蓝线：新参考路线；紫虚线：原最短路径。尚未运行 Jev，不能视为导航成功。余量指原 NavMesh 边界外的额外留白，原 NavMesh 已计入机器人半径。</p>'+''.join(cards)+'</body></html>')
    (out/'README.md').write_text('# 居中参考路线任务变体\n\n相同起终点、初始朝向与最短距离基准，仅替换任务的 path 参考路线。原路线另存 shortest_path，SPL 仍使用原 geodesic_m。geometry 字段仍描述原最短路径。\n\n'+ '\n'.join(table)+'\n\n[计划对照图](index.html)。这是 CPU 规划与 NavMesh 几何验证结果，没有调用模型。\n\n代价为距离乘以 1 + weight × exp(-额外 NavMesh 余量 / clearance_scale_m)，默认网格 0.10 m、衰减尺度 0.20 m、权重 4。尺度为软偏好，不是所有地方都保证 0.20 m 留白。网格边和简化后直连都经过原 NavMesh 验证；简化限制代价增加不超过 1%，最低余量下降不超过 0.005 m。仅支持近似平面路径，失败会明确报错，不偷偷回退到旧路线。\n')
    print('OUTPUT',out,flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
