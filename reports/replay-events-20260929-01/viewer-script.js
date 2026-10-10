
const data=JSON.parse(document.querySelector('#data').textContent), rows=data.records, meta=data.metadata;
const slider=document.querySelector('#slider');
document.querySelector('#kind').textContent=meta.provider==='jev'?'真实 Jev 决策运行':'脚本仿真验证：没有调用 Jev，不代表模型导航能力';
document.querySelector('#rgbTitle').textContent=meta.rgb_mode==='gs'?'Gaussian RGB（只用于回放，不送入 Jev）':meta.rgb_mode==='mesh'?'Mesh RGB（只用于回放）':'本次未渲染 RGB';
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
