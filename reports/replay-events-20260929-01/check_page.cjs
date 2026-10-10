// Execute the generated page JavaScript with a minimal DOM; no browser install.
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const path = require('path');
const report = __dirname;
const page = path.join(report,'../../runs/collision-check-20260928-01/visualizations/events-20260929-01/index.html');
const html = fs.readFileSync(page,'utf8');
const payload = html.match(/<script id="data" type="application\/json">([\s\S]*?)<\/script>/)[1];
const data = JSON.parse(payload), elements = {};
for (const [,id] of html.matchAll(/id="([^"]+)"/g)) elements[id] = {textContent:'',style:{},value:0,tagName:'DIV'};
elements.data.textContent=payload;elements.speed.value='1.5';elements.speed.tagName='SELECT';
let tick = null, keydown = null;
const document = {querySelector:s=>elements[s.slice(1)],querySelectorAll:()=>Object.values(elements),addEventListener:(name,fn)=>{if(name==='keydown')keydown=fn;}};
vm.runInNewContext(fs.readFileSync(path.join(report,'viewer-script.js'),'utf8'), {document, setInterval:fn=>{tick=fn;return 1},clearInterval:()=>{tick=null}});
function select(i){elements.slider.value=i;elements.slider.oninput();}
assert(elements.rgb.src===data.records[0].images.rgb);
select(2);assert(elements.event.style.color==='#b8c5d6');
select(3);assert(elements.event.textContent.includes('第 3 步'));assert(elements.event.style.color==='#ff4b4b');
assert(elements.rgb.src===data.records[3].rgb_display_image);assert(elements.map.src===data.records[3].map_image);
select(6);assert(elements.event.textContent.includes('无效动作'));assert(elements.event.style.color==='#ffc247');
assert(elements.rgb.src===data.records[6].rgb_display_image);
elements.next.onclick();assert(+elements.slider.value===7);assert(elements.event.style.color==='#b8c5d6');
elements.prev.onclick();assert(+elements.slider.value===6);assert(elements.event.style.color==='#ffc247');
keydown({key:'ArrowLeft',target:{tagName:'BODY'},preventDefault(){}});assert(+elements.slider.value===5);
elements.play.onclick();assert(tick);tick();assert(+elements.slider.value===6);assert(elements.event.style.color==='#ffc247');
elements.play.onclick();assert(tick===null);
console.log('PASS: initial frame, no future collision, collision, invalid action, terminal, backward seek, keyboard and playback.');
