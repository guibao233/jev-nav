"""Read-only audit of comparable Jev input ablations across three fixed routes."""
from pathlib import Path
from collections import Counter
import csv,hashlib,json,math,sys
import numpy as np
ROOT=Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav');sys.path.insert(0,str(ROOT))
from environment import load_pathfinder,shortest
from depth_language import semantic_depth
OUT=Path('/tmp/jev-route-ablation-summary-20261008-01');OUT.mkdir(exist_ok=True)
MODES=['numeric','semantic','none'];ROUTES=['simple','complex','extended'];LABELS={'numeric':'数值深度','semantic':'语义深度','none':'无深度'};RLABELS={'simple':'简单路线','complex':'复杂路线','extended':'长路线'}
TASKS={'simple':ROOT/'tasks/debug-10.json','complex':ROOT/'tasks/challenge-clearance-aligned-20260930-01/tasks.json','extended':ROOT/'tasks/extended-clearance-aligned-20261008-01/tasks.json'}
IDS={'simple':'episode-000','complex':'turn-000','extended':'extended-000'};BUDGET={'simple':100,'complex':250,'extended':500}
BASE={k:next(t for t in json.loads(p.read_text())['tasks'] if t['id']==IDS[k]) for k,p in TASKS.items()}
rows=[];excluded=[];hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in TASKS.values()};baseline_cfg=None
for folder in sorted((ROOT/'runs').iterdir()):
 if not (folder/'metadata.json').is_file() or not (folder/'summary.json').is_file():continue
 m=json.loads((folder/'metadata.json').read_text());s=json.loads((folder/'summary.json').read_text())
 if not s.get('is_jev_evaluation'):continue
 task=m['task'];route=next((k for k,v in IDS.items() if task['id']==v),None)
 reason=None
 if route is None:reason='other task'
 elif not str(m.get('prompt_version','')).startswith('seven_actions_reassociate_motion_v5'):reason='different action/prompt/route policy generation'
 elif any(task[k]!=BASE[route][k] for k in ['start','goal','path','yaw_deg','pitch_deg']):reason='different initial pose or reference path'
 elif m['config']['max_steps']!=BUDGET[route]:reason='different action budget'
 elif s['status'] not in ['success','early_stop','action_budget']:reason='incomplete or service/runtime failure'
 if reason:
  excluded.append({'run':folder.name,'reason':reason});continue
 cfg=m['config'];mode='none' if m.get('depth_input',cfg.get('depth_input','mesh'))=='none' else m.get('depth_format','numeric')
 assert mode in MODES
 common={k:v for k,v in cfg.items() if k not in ['gpu_id','depth_input','depth_format','max_steps']}
 if baseline_cfg is None:baseline_cfg=common
 assert common==baseline_cfg,(folder.name,'common config mismatch')
 for name in ['metadata.json','summary.json','steps.jsonl']:
  path=folder/name;hashes[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
 records=[json.loads(l) for l in (folder/'steps.jsonl').read_text().splitlines()];a=[r for r in records if r.get('outcome')];pf=load_pathfinder(dict(cfg))
 assert len(a)==s['steps'] and len(records)==len(a)+1
 assert [r['step'] for r in records]==list(range(len(records)))
 assert all(math.dist(r['after_position'],records[i+1]['pose']['position'])<1e-6 for i,r in enumerate(a))
 ds=[];travel=0
 for r in a:
  assert r['decision']['choice']==r['outcome']['action']==r['decision']['response']['answers']['action']['choice']
  assert r['decision']['response']['model']=='typesafe/jev-1.13-20260917'
  d=shortest(pf,r['after_position'],task['goal']);assert d is not None;ds.append(d[0]);assert abs(ds[-1]-r['metrics']['distance_to_goal_geodesic_m'])<1e-6
  travel+=math.dist(r['pose']['position'],r['after_position']);assert abs(travel-r['metrics']['path_length_m'])<1e-4
  if mode=='none':assert 'depth' not in r['request']['state']
  elif mode=='semantic':assert semantic_depth(r['depth_numeric_debug'])==r['request']['state']['depth'] and 'depth_numeric_debug' not in json.dumps(r['request'])
 assert abs(travel-s['path_length_m'])<1e-4 and abs(ds[-1]-s['final_geodesic_m'])<1e-6
 assert sum(r['outcome']['collided'] for r in a)==s['collisions']
 assert sum(not r['outcome']['valid'] for r in a)==s['invalid_actions']
 assert s['success']==(a[-1]['outcome']['action']=='stop' and ds[-1]<=cfg['success_m'])
 assert s['ever_within_goal_tolerance']==(min(ds)<=cfg['success_m'])
 assert abs(s['spl']-(s['initial_geodesic_m']/max(s['initial_geodesic_m'],travel) if s['success'] else 0))<1e-6
 assert not m.get('rgb_provided_to_model',False)
 assert all(not any(key in json.dumps(r['request']) for key in ['image_url','image/jpeg','image/png','data:image/']) for r in a)
 batch=('H' if folder.name.startswith('jev-challenge-') else 'G'+folder.name[-1] if '-rgbgs-' in folder.name else 'M1')
 rows.append({'route':route,'input':mode,'batch':batch,'run':folder.name,'rgb_replay':m['rgb_mode'],'status':s['status'],'success':s['success'],'collision_free_success':s['collision_free_success'],'steps':s['steps'],'collisions':s['collisions'],'invalid_actions':s['invalid_actions'],'path_length_m':s['path_length_m'],'final_geodesic_m':s['final_geodesic_m'],'minimum_geodesic_m':min(ds),'spl':s['spl'],'initial_geodesic_m':s['initial_geodesic_m'],'reference_path_length_m':m['reference_path_length_m'],'max_steps':cfg['max_steps']})
 print('VERIFIED',folder.name,len(a),flush=True)
rows.sort(key=lambda r:(ROUTES.index(r['route']),MODES.index(r['input']),['H','M1','G1','G2'].index(r['batch'])))
assert len(rows)==19 and sum(r['steps'] for r in rows)==3852
aggregate=[]
for route in ROUTES:
 for mode in MODES:
  sub=[r for r in rows if r['route']==route and r['input']==mode];assert sub
  aggregate.append({'route':route,'input':mode,'runs':len(sub),'successes':sum(r['success'] for r in sub),'collision_free_successes':sum(r['collision_free_success'] for r in sub),'total_collisions':sum(r['collisions'] for r in sub),'total_invalid_actions':sum(r['invalid_actions'] for r in sub),**{'mean_'+k:sum(r[k] for r in sub)/len(sub) for k in ['steps','collisions','invalid_actions','path_length_m','final_geodesic_m','spl']}})
assert hashes=={k:hashlib.sha256((ROOT/k).read_bytes()).hexdigest() for k in hashes}
result={'scope':'three fixed routes under current seven-action v5 policy and supplied reference paths; all completed comparable runs, including historical failures','rows':rows,'aggregate':aggregate,'excluded_completed_real_runs':excluded,'common_config':baseline_cfg,'verification':{'runs':len(rows),'actions':sum(r['steps'] for r in rows),'all_post_action_geodesics_recomputed':True,'counts_and_path_lengths_recomputed':True,'source_hashes_unchanged':True,'hashes':hashes,'api_calls':0,'used_gpu':False}}
(OUT/'summary.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
for filename,values in [('runs.csv',rows),('aggregate.csv',aggregate)]:
 with (OUT/filename).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(values[0]));w.writeheader();w.writerows(values)
lines=['# 三类路线 × 三种输入：Jev 导航消融汇总','','范围：当前七动作 v5 路径跟随策略、同一路线的相同起终点/初始姿态/参考路径。纳入 19 轮真实模型实验，包括可比历史失败；不混入早期九动作、六动作、不同初始朝向或不同参考路径的实验。','','简单路线最短/参考均约 4.20 m，预算 100；复杂路线最短 9.80 m、参考 11.71 m，预算 250；长路线最短 16.32 m、参考 19.61 m，预算 500。成功阈值均为 NavMesh 距离 <=0.30 m 且模型输出停止。','','## 成功数 / 运行数','','| 路线 | 数值深度 | 语义深度 | 无深度 |','|---|---|---|---|']
for route in ROUTES:lines.append('| '+RLABELS[route]+' | '+' | '.join(f"{next(a for a in aggregate if a['route']==route and a['input']==mode)['successes']}/{next(a for a in aggregate if a['route']==route and a['input']==mode)['runs']}" for mode in MODES)+' |')
lines+=['','## 逐轮指标','','批次：H=此前同配置历史记录；M1=第一批 mesh RGB 回放；G1/G2=GS RGB 回放的第一/第二轮。同一输入的编号用于区分记录，并非所有输入都有同批次运行。RGB 不发送给模型，所有有深度条件仍使用 mesh 深度。完整运行目录见表中链接和 runs.csv。','','预算耗尽和提前停止均计失败；累计路程含往返。最终距离保留六位小数，避免将 0.303706 m 的失败误读为达到 0.30 m。']
status={'success':'成功','early_stop':'失败：提前停止','action_budget':'失败：预算耗尽'}
for route in ROUTES:
 lines+=['',f'### {RLABELS[route]}','','| 输入 | 批次 | 结果 | 动作数 | 碰撞 | 无效动作 | 累计路程 m | 最终距离 m | SPL |','|---|---|---|---:|---:|---:|---:|---:|---:|']
 for r in rows:
  if r['route']!=route:continue
  lines.append(f"| {LABELS[r['input']]} | [{r['batch']}](../../runs/{r['run']}/summary.json) | {status[r['status']]} | {r['steps']} | {r['collisions']} | {r['invalid_actions']} | {r['path_length_m']:.3f} | {r['final_geodesic_m']:.6f} | {r['spl']:.3f} |")
lines+=['','## 观察','','- 简单路线：三种输入均完成；数值深度 18 步且零碰撞，语义深度 23 步且零碰撞，无深度 18 步但每轮各 1 次碰撞。单纯参考路径可支撑直线路径跟随，但不等于可靠避障。','- 复杂路线：数值 1/3、语义 1/2、无深度 1/2。新增无深度成功样本为 77 步/6 次碰撞，历史无深度失败为 250 步/29 次碰撞。数值、语义的成功样本都零碰撞；两个近期失败是容差外提前停止。','- 长路线：只有数值一次成功（252 步、零碰撞、SPL 0.544）；语义两次均零碰撞但在终点附近绕行；无深度两次均失败且共 158 次碰撞。','- 总体：本批证据支持深度对减少碰撞有帮助；不能将零碰撞视为完成导航，也不能凭每格 2–3 次重复确定数值或语义的稳定优劣。','','## 可比性和限制','','- 每类只有一个固定起终点，因此是案例级消融，不是跨场景或多目标基准成功率。历史记录与近期记录不构成同一随机种子的配对试验；模型服务同请求可返回不同动作。','- 复杂数值组有 3 轮，其余各 2 轮；不可选择性剔除历史失败。aggregate.csv 保留各组样本数，不能直接合并不同难度来判断总体排名。','- 无深度仍保留参考路径、目标相对位置、本体状态和最近自身动作反馈；不是纯盲导航。相应提示词移除了深度和观察指令，语义版也有编码说明。','- 碰撞为 Habitat 的 NavMesh 移动过滤 collided，不是 Bullet 接触计数；成功与零碰撞成功分别记录。无效动作消耗预算。','- 累计路程不计原地转向与观察成本。失败路径受预算或提前停止截断，均值不是成功路径效率。','- M1 与 GS 记录的渲染耗时不可直接当作模型决策性能差异。','','## 输出与核查','','- [逐轮 CSV](runs.csv)：含所有所需指标、SPL、最小到达距离和原始目录。','- [按路线/输入聚合 CSV](aggregate.csv)：含成功数、零碰撞成功数、均值及总碰撞。','- [结构化结果与源文件哈希](summary.json)，[离线核查脚本](summarize.py)。','- 所有 3852 个实际动作重新计算到终点的 NavMesh 距离、累计路程、成功条件和 SPL；碰撞、无效动作由逐步日志重新计数。输入条件、共同配置、模型版本、日志步序和帧间位姿连续性均通过核对。此次没有重新渲染或逐帧重算原始深度。','- 检查原始日志和任务文件哈希未变化；未调用 API，未使用 GPU。','','## 排除的完成记录','','| 运行 | 原因 |','|---|---|']
for x in excluded:lines.append(f"| {x['run']} | {x['reason']} |")
(OUT/'README.md').write_text('\n'.join(lines)+'\n')
print('RESULT',json.dumps(aggregate,ensure_ascii=False),flush=True)
print('PASS',len(rows),'runs',sum(r['steps'] for r in rows),'actions',len(hashes),'protected sources')
