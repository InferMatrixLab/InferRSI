const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const html=fs.readFileSync(process.argv[2],'utf8'), mode=process.argv[3], conflicts=mode==='conflicts';
class Element {
  constructor(){this.children=[];this.dataset={};this.hidden=false;this.textContent='';}
  append(...children){this.children.push(...children);}
  replaceChildren(){this.children=[];}
  addEventListener(event,listener){this[event]=listener;}
  child(){const item=new Element();this.append(item);return item;}
  createTHead(){return this.child();} createTBody(){return this.child();}
  insertRow(){return this.child();} insertCell(){return this.child();}
  *walk(){yield this;for(const c of this.children)if(c instanceof Element)yield* c.walk();}
  text(){return [...this.walk()].map(c=>c.textContent).join(' ');}
}
const nodes=new Map();
for(const match of html.matchAll(/<[a-z][^>]*\bid="([^"]+)"[^>]*>/g)){
  const el=new Element();el.hidden=/\shidden\b/.test(match[0]);nodes.set(match[1],el);
}
const id=k=>nodes.get(k), make=()=>new Element();
const payload=html.match(/<script id="dashboard-data"[^>]*>([\s\S]*?)<\/script>/);
id('dashboard-data').textContent=payload[1];
const document={documentElement:make(),createElement:make,createTextNode:String,
                getElementById:id,querySelectorAll:()=>[]};
const source=[...html.matchAll(/<script>\s*([\s\S]*?)<\/script>/g)].at(-1)[1];
vm.runInNewContext(source,{document,window:{addEventListener(){},
  InferRSIExperiments:{create:()=>({render(){}})}},
                          localStorage:{getItem(){return 'en';},setItem(){}}});
if(mode==='timing'){
  function expand(root,key){
    const item=[...root.walk()].find(el=>el.dataset.key===key);
    assert.ok(item,key);item.open=true;item.toggle();return item;
  }
  const timing=id('baseline'), table=timing.text();
  assert.match(table,/Caller-recorded stage measurements/);
  assert.match(table,/Different clock/);
  assert.match(table,/Verified baseline · sampled scope duration/);
  assert.match(table,/Original worker/);
  assert.match(table,/Supplemental timing evidence is unavailable/);
  assert.match(expand(timing,'experiment-calls').text(),/Unmeasured/);
  const card=expand(id('captures'),'profile:other');
  const kb=expand(card,'profile:other-kb');
  assert.match(kb.text(),/r1 · Search predates the caller-recorded capture start/);
  assert.match(kb.text(),/late · Search did not precede capture/);
  assert.match(kb.text(),/unknown · Order unknown/);
  assert.match(kb.text(),/bad · Search unavailable or unverified/);
  assert.match(kb.text(),/Query · decode launch/);
  assert.match(kb.text(),/Included · Reported used/);
  assert.match(expand(kb,'profile:other-kb-r1-text').text(),/Capture repeated decode launches/);
  assert.doesNotMatch(kb.text(),/PRIVATE SENTINEL/);
  assert.equal([...kb.walk()].filter(e=>e.dataset.key?.endsWith('-text')).length,1);
}
const items=()=>id('checks-list').children.map(node=>node.textContent);
assert.equal(id('story-checks').hidden,!conflicts);
assert.equal(id('checks-title').textContent,'Narrative vs evidence');
if(conflicts) assert.deepEqual(items(),[
  'Warning · knowledge r1 · the log says package:missing was used, '
    +'but it was not retrieved by this capture',
  'Conflict · round 1 · the log says rejected, rounds.jsonl records adopted',
]); else assert.deepEqual(items(),[]);
id('language').click();
assert.equal(id('story-checks').hidden,!conflicts);
assert.equal(id('checks-title').textContent,'叙述与证据核对');
if(conflicts) assert.deepEqual(items(),[
  '警告 · 检索 r1 · 日志称采用了 package:missing，本次检索没有返回该条目',
  '冲突 · 第 1 轮 · 日志记为未采纳，rounds.jsonl 记为已采纳',
]); else assert.deepEqual(items(),[]);
