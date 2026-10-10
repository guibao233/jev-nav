const assert=require("assert");const elements={};const document={querySelector(s){return elements[s]??=(s==="#data"?{textContent:"{\"metadata\": {\"provider\": \"jev\", \"rgb_mode\": \"gs\", \"map\": {\"origin_x\": 0, \"origin_z\": 0, \"resolution_m\": 0.05, \"width\": 100, \"height\": 100}, \"task\": {\"start\": [1, 0, 3], \"goal\": [1, 0, 1], \"path\": [[1, 0, 3], [1, 0, 1]]}}, \"records\": [{\"step\": 0, \"frame_kind\": \"before_action\", \"pose\": {\"position\": [1, 0, 3], \"yaw_rad\": 0}, \"images\": {\"rgb\": \"observations/00000-rgb.png\", \"depth\": \"observations/00000-depth.png\"}, \"request\": {\"state\": {\"task\": {\"step\": 1}, \"reference\": {\"current_target\": {\"forward_m\": 0.75, \"left_m\": 0, \"distance_m\": 0.75}, \"ordered_preview\": [{\"forward_m\": 0.5, \"left_m\": 0}]}}}, \"decision\": null, \"outcome\": null, \"metrics\": {}, \"map_image\": \"navmap-frames/00000.png\", \"previous_action_event\": null, \"rgb_display_image\": \"observations/00000-rgb.png\"}], \"summary\": {\"status\": \"action_budget\"}}"}:{textContent:"",value:0,tagName:"DIV",style:{}});},querySelectorAll(){return[];},addEventListener(){}};

const data=JSON.parse(document.querySelector('#data').textContent), rows=data.records, meta=data.metadata;
const slider=document.querySelector('#slider');
const modelLabel=meta.model_label||(meta.provider==='openai_decisions'?'GPT-6 Luna Decisions':'Jev');
const live=meta.is_model_evaluation??['jev','openai_decisions'].includes(meta.provider);
document.querySelector('#kind').textContent=live?`真实 ${modelLabel} 决策运行`:'脚本仿真验证：没有调用模型，不代表模型导航能力';
document.querySelector('#rgbTitle').textContent=meta.rgb_mode==='gs'?'Gaussian RGB（只用于回放，不送入模型）':meta.rgb_mode==='mesh'?'Mesh RGB（只用于回放）':'本次未渲染 RGB';
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

assert(document.querySelector("#kind").textContent.startsWith("\u771f\u5b9e Jev \u51b3\u7b56\u8fd0\u884c"));console.log(document.querySelector("#kind").textContent);
