"""Standalone offline HTML replay: no server, CDN, or model call required."""
import json
import copy
from html import escape
from pathlib import Path
import numpy as np
from PIL import Image
from map_view import draw_map, map_view
from replay_events import annotate_event, observation_event


def save_frame(root, index, depth, rgb):
    import matplotlib
    stem = f"frames/{index:05d}"
    np.savez_compressed(root / (stem+"-depth.npz"),depth_m=depth)
    valid = np.isfinite(depth) & (depth > 0) & (depth < 19.99)
    pixels = matplotlib.colormaps["viridis_r"](np.clip(depth/6,0,1))[...,:3]
    pixels[~valid] = .35
    Image.fromarray((pixels*255).astype(np.uint8)).save(root / (stem+"-depth.png"))
    if rgb is not None:
        Image.fromarray(rgb.astype(np.uint8)).save(root / (stem+"-rgb.png"))
    return {"depth": stem+"-depth.png", "rgb": stem+"-rgb.png" if rgb is not None else None}


def save_map(pf, height, root):
    resolution = .05
    nav = pf.get_topdown_view(resolution, float(height))
    image = np.full((*nav.shape,3),32,dtype=np.uint8)
    image[nav.astype(bool)] = [215,219,226]
    Image.fromarray(image).save(root/"navmap.png")
    low, high = pf.get_bounds()
    return {"origin_x": float(low[0]), "origin_z": float(low[2]), "resolution_m": resolution,
            "width": int(nav.shape[1]), "height": int(nav.shape[0])}


def write_replay(root, metadata, records, summary, *, filename="index.html", map_subdir="navmap-frames", media_prefix=None):
    # Render map panels once so HTML and video share the exact same transforms.
    # Display-only fields never mutate requests or steps.jsonl.
    records = copy.deepcopy(records)
    if records:
        with Image.open(root/"navmap.png") as image:
            navmap = image.convert("RGB")
        view = map_view(metadata,records)
        (root/map_subdir).mkdir(parents=True,exist_ok=True)
        for i,r in enumerate(records):
            name = f"{map_subdir}/{i:05d}.png"
            draw_map(navmap,metadata,records,i,view).save(root/name)
            r["map_image"] = name
            event = observation_event(records,i)
            r["previous_action_event"] = event
            r["rgb_display_image"] = r["images"].get("rgb")
            if event and r["images"].get("rgb"):
                folder = root/(map_subdir+"-events")
                folder.mkdir(parents=True,exist_ok=True)
                name = f"{map_subdir}-events/{i:05d}-rgb.png"
                with Image.open(root/r["images"]["rgb"]) as rgb:
                    annotate_event(rgb,event).save(root/name)
                r["rgb_display_image"] = name
    payload = json.dumps({"metadata":metadata,"records":records,"summary":summary},ensure_ascii=False,allow_nan=False).replace("<","\\u003c")
    label = metadata.get("model_label", "GPT-6 Luna Decisions" if metadata.get("provider") == "openai_decisions" else "Jev")
    html = '''<!doctype html><html lang="zh"><meta charset="utf-8"><title>__MODEL_LABEL__ 路径跟随实验回放</title>
<style>body{background:#131923;color:#e4e9ef;font:15px system-ui;margin:24px}h1{font-size:23px}button{padding:8px 16px}input{width:65%;vertical-align:middle} .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}img,canvas{max-width:100%;background:#202733;border-radius:6px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#202733;padding:14px;max-height:500px;overflow:auto}.tag{color:#ffd27c}.caption{color:#b8c5d6;margin:8px 0} @media(max-width:850px){.grid{grid-template-columns:1fr}}</style>
<h1>__MODEL_LABEL__ 路径跟随实验回放</h1><p id="kind" class="tag"></p><p id="summary"></p>__MEDIA_LINKS__
<noscript>当前预览没有执行 JavaScript。请使用工具的 --serve 浏览器入口，或查看导出的 GIF / MP4。</noscript>
<button id="prev">上一帧</button> <button id="play">播放</button> <button id="next">下一帧</button>
<label>展示间隔 <select id="speed"><option value="0.5">0.5 秒</option><option value="1">1 秒</option><option value="1.5" selected>1.5 秒</option><option value="3">3 秒</option></select></label>
<p><input id="slider" type="range" min="0" step="1"><span id="counter"></span></p>
<p class="caption">红色圈叉：碰撞；黄色方框叹号：无效动作。标识对应上一动作完成后的当前观察；地图保留已发生事件的机器人位置，不表示精确接触点。</p><p id="event" role="status"></p>
<div class="grid"><div><p class="caption" id="rgbTitle"></p><img id="rgb"><div id="modelRgbPanel" hidden><p class="caption">本帧模型输入 RGB：粉色圆环为当前航点投影，边缘箭头表示目标在画面外或身后；虚拟标记不代表可通行。终态不再请求模型。</p><img id="modelRgb"></div><p class="caption" id="depthTitle">Mesh 深度：黄色近、紫色远，显示范围 0–6 m；原始米制深度另存 NPZ。</p><img id="depth"></div>
<div><p class="caption">NavMesh 局部俯视图：蓝线为本轮参考路线，紫线为另存的原最短路径（如有），橙线为已执行轨迹；绿色 S 起点、红色 G 终点、白色机器人朝向。粉色 T 为当前目标，青色编号点为实际交给决策模型的前方路径点。</p><img id="map" width="640" height="480"><p class="caption">下方记录为本帧观察之后选择的动作及结果；画面标识为上一动作反馈。</p><pre id="decision"></pre></div></div>
<details open><summary>本帧模型输入状态（执行动作之前）</summary><pre id="state"></pre></details>
<details><summary>配置与结果</summary><pre id="all"></pre></details>
<script id="data" type="application/json">__PAYLOAD__</script><script>
const data=JSON.parse(document.querySelector('#data').textContent), rows=data.records, meta=data.metadata;
const slider=document.querySelector('#slider');
const modelLabel=meta.model_label||(meta.provider==='openai_decisions'?'GPT-6 Luna Decisions':'Jev');
const live=meta.is_model_evaluation??['jev','openai_decisions'].includes(meta.provider);
document.querySelector('#kind').textContent=live?`真实 ${modelLabel} 决策运行`:'脚本仿真验证：没有调用模型，不代表模型导航能力';
document.querySelector('#rgbTitle').textContent=meta.rgb_mode==='gs'?'Gaussian RGB（只用于回放，不送入模型）':meta.rgb_mode==='mesh'?'Mesh RGB（只用于回放）':'本次未渲染 RGB';
if(meta.rgb_provided_to_model){
 document.querySelector('#rgbTitle').textContent='原始 RGB（下方另示实际输入的标注图）';
 document.querySelector('#kind').textContent+=' · 当前 RGB + 虚拟航点标记';
}
if(meta.depth_input==='none'||meta.depth_provided_to_model===false){
 document.querySelector('#kind').textContent+=' · 无深度输入消融';
 document.querySelector('#depthTitle').textContent+=' 本组深度仅供回放，未提供给模型。';
}
if(meta.depth_format==='semantic'){
 document.querySelector('#kind').textContent+=' · 九方向语义深度';
 document.querySelector('#depthTitle').textContent+=' 决策模型接收文字摘要；精确数值仅保存在本地诊断日志。';
}
document.querySelector('#summary').textContent=JSON.stringify(data.summary);
document.querySelector('#all').textContent=JSON.stringify({metadata:meta,summary:data.summary},null,2);
slider.max=Math.max(0,rows.length-1);slider.value=0;
function draw(){let i=+slider.value,r=rows[i];if(!r)return;
 document.querySelector('#map').src=r.map_image;
 document.querySelector('#rgb').hidden=!r.images.rgb;if(r.images.rgb)document.querySelector('#rgb').src=r.rgb_display_image||r.images.rgb;
 document.querySelector('#modelRgbPanel').hidden=!r.images.model_rgb;if(r.images.model_rgb)document.querySelector('#modelRgb').src=r.images.model_rgb;
 const event=r.previous_action_event,eventLabel=document.querySelector('#event');
 eventLabel.textContent=event?event.label:'上一动作无碰撞或无效标识';eventLabel.style.color=event?event.color:'#b8c5d6';
 document.querySelector('#depth').src=r.images.depth;document.querySelector('#counter').textContent=` ${i+1} / ${rows.length}`;
 document.querySelector('#state').textContent=JSON.stringify(r.request?.state||{},null,2);
 document.querySelector('#decision').textContent=JSON.stringify({step:r.step,decision:r.decision,outcome:r.outcome,metrics:r.metrics,frame:r.frame_kind},null,2)}
let timer=null;const play=document.querySelector('#play'),speed=document.querySelector('#speed');
function stop(){if(timer!==null)clearInterval(timer);timer=null;play.textContent='播放'}
function selectFrame(i){stop();slider.value=Math.max(0,Math.min(rows.length-1,i));draw()}
function start(){if(!rows.length)return;if(+slider.value>=rows.length-1){slider.value=0;draw()}play.textContent='暂停';timer=setInterval(()=>{if(+slider.value>=rows.length-1){stop();return}slider.value=+slider.value+1;draw()},+speed.value*1000)}
slider.oninput=()=>{stop();draw()};play.onclick=()=>{timer===null?start():stop()};
document.querySelector('#prev').onclick=()=>selectFrame(+slider.value-1);
document.querySelector('#next').onclick=()=>selectFrame(+slider.value+1);
speed.onchange=()=>{if(timer!==null){stop();start()}};
document.addEventListener('keydown',e=>{if(e.target.tagName==='SELECT')return;if(e.key==='ArrowLeft'){e.preventDefault();selectFrame(+slider.value-1)}if(e.key==='ArrowRight'){e.preventDefault();selectFrame(+slider.value+1)}});
if(!rows.length){document.querySelector('#counter').textContent=' 没有保存观察帧';document.querySelectorAll('button,input,select').forEach(el=>el.disabled=true)}draw();
</script></html>'''
    html = html.replace("__MODEL_LABEL__",escape(label))
    media = ""
    if media_prefix:
        prefix = escape(media_prefix.rstrip("/"),quote=True)
        media = f'<p><a href="{prefix}/rgb-depth.mp4">MP4 视频</a> · <a href="{prefix}/rgb-depth.gif">GIF 动图</a> · <a href="{prefix}/contact-sheet.png">静态总览</a></p>'
    (root/filename).write_text(html.replace("__MEDIA_LINKS__",media).replace("__PAYLOAD__",payload),encoding="utf-8")
