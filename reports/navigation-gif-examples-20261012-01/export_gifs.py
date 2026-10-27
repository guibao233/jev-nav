"""Export selected recorded navigation sequences; no simulator/model/GPU calls."""
from pathlib import Path
from collections import Counter
import csv,hashlib,html,json,sys
from PIL import Image,ImageDraw,ImageFont,ImageSequence
ROOT=Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav')
sys.path.insert(0,str(ROOT))
from map_view import draw_map,map_view,recorded_targets
from replay_events import observation_event,annotate_event,EVENT_TIMING,ACTIONS
OUT=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent
OUT.mkdir(parents=True,exist_ok=True)
for folder in ['gifs','posters']:(OUT/folder).mkdir(exist_ok=True)
FONT='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
FONTS={size:ImageFont.truetype(FONT,size) for size in [16,17,18,22]}
specs=[
 dict(id='01-jev-simple-success',run='jev-simple-rgbgs-numeric-20261008-01',title='Jev 文字｜简单路线｜数值深度',note='完整过程：快速跟随并主动停止。',start=0,end=None,poster=10),
 dict(id='02-openai-text-complex-success',run='openai-decisions-complex-rgbgs-numeric-20261009-01',title='OpenAI 纯文字｜复杂路线｜数值深度',note='完整过程：经过转角，零碰撞到达并停止。',start=0,end=None,poster=62),
 dict(id='03-openai-rgb-complex-success',run='openai-decisions-rgbtarget-complex-rgbgs-semantic-20261009-01',title='OpenAI 图文｜复杂路线｜语义深度',note='完整过程：转向、低头观察、路径跟随与停止；含一次无效俯仰。',start=0,end=None,poster=70),
 dict(id='04-openai-rgb-marker-and-stop',run='openai-decisions-rgbtarget-extended-rgbgs-semantic-20261009-01',title='OpenAI 图文｜长路线｜语义深度',note='局部片段：最后接近与停止，包含第307次决策前的粉色圆环示例。',start=269,end=None,poster=306),
 dict(id='05-openai-text-collision',run='openai-decisions-complex-rgbgs-none-20261009-01',title='OpenAI 纯文字｜复杂路线｜无深度文字',note='局部片段：35次动作窗口中碰撞最多的连续片段，展示受阻后的重复尝试。',selection='densest_collision_35_actions',poster=None),
 dict(id='06-onejev-forward-backward',run='onejev-local-rgbtarget-simple-rgbgs-numeric-local-round-01',title='OneJev-4B 图文｜简单路线｜数值深度',note='完整过程：接近终点后反复前进/后退，伴随碰撞，预算耗尽。',start=0,end=None,poster=46),
 dict(id='07-onejev-stationary-turns',run='onejev-local-rgbtarget-complex-rgbgs-none-local-round-01',title='OneJev-4B 图文｜复杂路线｜无深度文字',note='局部片段：连续48次原地左转，位置保持不变；整轮最终失败。',start=9,end=57,poster=21),
 dict(id='08-jev-long-route-failure',run='jev-extended-rgbgs-semantic-20261008-01',title='Jev 文字｜长路线｜语义深度',note='局部片段：最后60次动作，终点附近绕行与无效俯仰，预算耗尽。',start=440,end=None,poster=478),
]
input_hashes={}
def protect(path):
 digest=hashlib.sha256(path.read_bytes()).hexdigest()
 input_hashes[str(path.relative_to(ROOT))]=digest
 return digest
def text(draw,xy,value,size=18,color='#e4e9ef'):
 assert draw.textlength(value,font=FONTS[size])<=940,('caption too wide',value)
 draw.text(xy,value,font=FONTS[size],fill=color)
results=[];frames_manifest={};posters=[]
for spec in specs:
 run=ROOT/'runs'/spec['run']
 for f in ['metadata.json','steps.jsonl','summary.json','navmap.png']:protect(run/f)
 m=json.loads((run/'metadata.json').read_text());s=json.loads((run/'summary.json').read_text())
 records=[json.loads(line) for line in (run/'steps.jsonl').read_text().splitlines()]
 assert len(records)==s['steps']+1 and records[-1]['frame_kind']=='after_final_action'
 with Image.open(run/'navmap.png') as im:navmap=im.convert('RGB')
 view=map_view(m,records)
 if spec.get('selection')=='densest_collision_35_actions':
  spec['start']=max(range(len(records)-35),key=lambda i:sum(r['outcome']['collided'] for r in records[i:i+35]))
  spec['end']=spec['start']+35
  spec['poster']=next(i for i in range(spec['start']+1,spec['end']+1) if observation_event(records,i))
 start=spec['start'];end=spec['end'] if spec['end'] is not None else len(records)-1
 assert 0<=start<=end<len(records)
 spec['end']=end
 frames=[];manifest=[]
 for index in range(start,end+1):
  r=records[index];state=(r.get('request') or {}).get('state');event=observation_event(records,index)
  model_image=bool(state and m.get('rgb_provided_to_model'))
  name=r['images'].get('model_rgb') if model_image else r['images']['rgb']
  assert name
  image_path=run/name;digest=protect(image_path)
  if model_image:assert digest==r['image_input']['sha256']
  with Image.open(image_path) as im:rgb=im.convert('RGB')
  rgb=annotate_event(rgb,event,top=44)
  mp=draw_map(navmap,m,records,index,view)
  # Neutralize the historical map helper's provider-specific terminal label.
  if not state:
   md=ImageDraw.Draw(mp);md.rounded_rectangle((18,14,400,40),radius=4,fill='#131923')
   md.text((24,16),'终态：没有新的模型请求或目标',font=FONTS[16],fill='#e4e9ef')
  canvas=Image.new('RGB',(960,558),'#131923');draw=ImageDraw.Draw(canvas)
  text(draw,(12,5),spec['title'],22)
  text(draw,(12,34),spec['note'],17,'#b8c5d6')
  channel='实际模型标注图＋回放事件' if model_image else '终态 RGB：未再次请求模型' if not state else 'GS RGB：仅供回放，未提供给模型'
  text(draw,(12,63),channel,16);text(draw,(492,63),'NavMesh：参考路线／轨迹／当前目标',16)
  canvas.paste(rgb.resize((480,360),Image.Resampling.LANCZOS),(0,86))
  canvas.paste(mp.resize((480,360),Image.Resampling.LANCZOS),(480,86))
  distance=s['initial_geodesic_m'] if index==0 else records[index-1]['metrics']['distance_to_goal_geodesic_m']
  previous=records[index-1]['outcome'] if index else None
  prev_caption='初始观察' if previous is None else f"上一动作：{ACTIONS[previous['action']]}／"+('碰撞' if previous['collided'] else '无效' if not previous['valid'] else '正常执行')
  next_caption=f"下一动作：{ACTIONS[r['decision']['choice']]}" if state else '终态：'+('成功' if s['success'] else s['status'])
  text(draw,(12,453),f"观察 {index}/{s['steps']}｜{prev_caption}｜{next_caption}",18,'#ffd27c')
  completed=records[:index]
  collisions=sum(x['outcome']['collided'] for x in completed);invalid=sum(not x['outcome']['valid'] for x in completed)
  text(draw,(12,479),f"当前到终点的 NavMesh 距离：{distance:.3f} m｜累计碰撞 {collisions}｜累计无效 {invalid}",18)
  if state:
   t=state['reference']['current_target'];target_caption=f"局部目标：{t['distance_m']:.3f} m / {t['bearing_deg']:+.2f}°（左正）｜下俯角 {r['pose']['pitch_deg']:g}°"
  else:target_caption=f"整轮：{s['steps']}次动作，{s['collisions']}次碰撞，最终距离 {s['final_geodesic_m']:.3f} m"
  text(draw,(12,505),target_caption,17)
  text(draw,(12,532),f"原观察范围 {start}–{end}｜固定5帧/秒，末帧停留0.8秒；展示时间非实际耗时",16,'#b8c5d6')
  frames.append(canvas)
  manifest.append(dict(observation_index=index,source_rgb=name,source_rgb_sha256=digest,current_geodesic_m=distance,previous_completed_action=previous,previous_event=event,current_pending_action=r['decision']['choice'] if state else None,pose=r['pose'],targets=recorded_targets(r)))
 assert len(frames)==end-start+1
 # One shared palette per clip avoids per-frame adaptive-palette flicker.
 samples=[frames[k] for k in sorted({0,len(frames)//4,len(frames)//2,3*len(frames)//4,len(frames)-1})]
 montage=Image.new('RGB',(480,279*len(samples)))
 for i,f in enumerate(samples):montage.paste(f.resize((480,279)),(0,279*i))
 palette=montage.quantize(colors=240,method=Image.Quantize.MEDIANCUT)
 fixed=['#131923','#e4e9ef','#b8c5d6','#ffd27c','#ff4b4b','#ffc247','#ff00cc','#d81b97','#2974ee','#ef9024','#0eaa50','#ed394e','#00acb8','#ffffff','#000000','#ab6ae0']
 tail=[]
 for color in fixed:tail.extend(bytes.fromhex(color[1:]))
 palette.putpalette(palette.getpalette()[:720]+tail)
 indexed=[f.quantize(palette=palette,dither=Image.Dither.NONE) for f in frames]
 durations=[200]*len(indexed);durations[-1]=800
 gif_path=OUT/'gifs'/(spec['id']+'.gif')
 indexed[0].save(gif_path,save_all=True,append_images=indexed[1:],duration=durations,loop=0,disposal=2,optimize=False)
 with Image.open(gif_path) as gif:
  assert gif.size==(960,558) and gif.n_frames==len(frames)
  assert sum(f.info['duration'] for f in ImageSequence.Iterator(gif))==sum(durations)
  assert gif.info['loop']==0
 poster_index=spec['poster']-start;assert 0<=poster_index<len(frames)
 poster_path=OUT/'posters'/(spec['id']+'.png');frames[poster_index].save(poster_path);posters.append(frames[poster_index])
 counts=Counter(r['outcome']['action'] for r in records[start:end])
 row=dict(id=spec['id'],title=spec['title'],description=spec['note'],source_run=spec['run'],start_observation=start,end_observation=end,observations=len(frames),actions_shown=end-start,full_episode=start==0 and end==s['steps'],whole_episode_success=s['success'],whole_episode_status=s['status'],whole_episode_steps=s['steps'],whole_episode_collisions=s['collisions'],whole_episode_invalid_actions=s['invalid_actions'],whole_episode_path_m=s['path_length_m'],whole_episode_final_geodesic_m=s['final_geodesic_m'],clip_collisions=sum(r['outcome']['collided'] for r in records[start:end]),clip_invalid_actions=sum(not r['outcome']['valid'] for r in records[start:end]),clip_action_counts=dict(counts),gif=str(gif_path.relative_to(OUT)),poster=str(poster_path.relative_to(OUT)),poster_observation=spec['poster'],duration_s=sum(durations)/1000,gif_bytes=gif_path.stat().st_size,gif_sha256=hashlib.sha256(gif_path.read_bytes()).hexdigest(),map_view=view)
 results.append(row);frames_manifest[spec['id']]=manifest
 print(json.dumps({k:row[k] for k in ['id','observations','duration_s','gif_bytes','clip_collisions','clip_invalid_actions']},ensure_ascii=False),flush=True)
 del frames,indexed
sheet=Image.new('RGB',(960,279*4),'#131923')
for i,im in enumerate(posters):sheet.paste(im.resize((480,279),Image.Resampling.LANCZOS),((i%2)*480,(i//2)*279))
sheet.save(OUT/'contact-sheet.png')
readme='''# 代表性导航序列 GIF

选取固定四模型对比中的 8 个成功或失败行为案例，用已有 GS RGB 与 NavMesh 记录离线生成。不是新的模型实验；片段按展示行为选择，不用于重新计算成功率或代表全部条件。所有选择的来源、范围和指标见下表及 export.json。

左侧为 RGB，右侧为 NavMesh。图文组优先显示该步实际发送的标注 JPEG；文字组 RGB 只供回放。红框/红圈叉表示上一动作后的碰撞，黄框/感叹号表示无效动作；事件叠加只用于展示，没有发送给模型。NavMesh 中蓝线为参考路线，橙线为累计执行轨迹，粉色 T 为当步局部目标，白箭头为身体朝向，绿色 S / 红色 G 为起终点。

每个原观察保留一帧，固定 5 帧/秒，末帧停留 0.8 秒；播放时间不是模型调用或实际实验耗时。没有插值、平滑、删除转向或无效动作帧。GIF 循环回到开头仅是播放设置，不是机器人自动重启。

## 展示序列

| 序列 | 范围（原观察索引，从0开始） | 整轮结果 | 片段动作 / 碰撞 / 无效 | GIF时长 | 文件 |
|---|---|---|---|---:|---|
'''
cards=[]
for r in results:
 kind='全程' if r['full_episode'] else '局部片段'
 state='成功' if r['whole_episode_success'] else '失败：'+r['whole_episode_status']
 readme+=f"| {r['title']} | {kind} {r['start_observation']}–{r['end_observation']} | {state} | {r['actions_shown']} / {r['clip_collisions']} / {r['clip_invalid_actions']} | {r['duration_s']:.1f}s | [GIF]({r['gif']}) / [静态预览]({r['poster']}) |\n"
 readme+=f"\n<!-- {r['id']}: {r['description']} -->\n" if False else ''
 cards.append(f"<article><h2>{html.escape(r['title'])}</h2><p>{html.escape(r['description'])}</p><p>{kind}：观察 {r['start_observation']}–{r['end_observation']}；整轮{state}；片段碰撞 {r['clip_collisions']}，无效 {r['clip_invalid_actions']}。</p><img loading='lazy' src='{r['gif']}' alt='{html.escape(r['title'])}' width='960' height='558'><p><a href='{r['gif']}'>打开／下载 GIF</a> · <a href='{r['poster']}'>静态预览</a> · <a href='../../runs/{r['source_run']}/summary.json'>原始结果</a></p></article>")
readme+='\n## 案例说明\n\n'
for r in results:readme+=f"- **{r['title']}**：{r['description']} 来源 [{r['source_run']}](../../runs/{r['source_run']}/summary.json)。\n"
readme+='''
无深度图文组仍有 RGB；GIF 中的导航地图仅供解释，没有作为图片发送给模型。最终状态/成功率依据整轮 summary.json，而非片段结束位置。片段中的当前距离是上一动作完成后、与当前 RGB 位姿一致的 NavMesh 距离；下一动作尚未发生，避免将其碰撞结果提前叠在当前观察。

[浏览所有 GIF](index.html) · [静态总览](contact-sheet.png) · [片段与源哈希](export.json) · [逐帧来源/事件/目标](frame-manifest.json) · [复现脚本](export_gifs.py)

PNG/GIF 可直接用图片查看器或 VS Code 打开。index.html 不需要 JavaScript、服务器或模型服务。复现只需现有 habitat-gs 环境，传入新的目录：

```bash
conda activate habitat-gs
python reports/navigation-gif-examples-20261012-01/export_gifs.py /tmp/navigation-gif-recheck
```
'''
(OUT/'README.md').write_text(readme)
(OUT/'index.html').write_text("<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>导航代表序列 GIF</title><style>body{background:#131923;color:#e4e9ef;font:17px system-ui,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px}article{margin:30px 0;padding:16px;border:1px solid #516072;border-radius:8px}img{width:100%;height:auto}a{color:#8ad1ff}h2{font-size:22px}p{line-height:1.6}</style><h1>8 个代表性导航序列</h1><p>固定 5 帧/秒，保留连续观察；末帧停留 0.8 秒。GIF 循环播放，不代表实验实际耗时。文字组 RGB 仅供回放，图文组为实际输入标注图加展示事件。</p><p><a href='README.md'>选择说明与指标</a> · <a href='contact-sheet.png'>静态总览</a></p>"+''.join(cards)+"</html>")
for path,digest in input_hashes.items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,path
(OUT/'export.json').write_text(json.dumps(dict(clips=results,source_sha256=input_hashes,seconds_per_observation=.2,last_observation_hold_s=.8,event_timing=EVENT_TIMING,interpolation=False,frame_skipping=False,api_calls=0,used_gpu=False,reran_simulator=False,source_runs_modified=False),ensure_ascii=False,indent=2)+'\n')
(OUT/'frame-manifest.json').write_text(json.dumps(frames_manifest,ensure_ascii=False,indent=2)+'\n')
print('PASS',len(results),'GIFs;',sum(r['observations'] for r in results),'frames;',sum(r['gif_bytes'] for r in results),'bytes',flush=True)
