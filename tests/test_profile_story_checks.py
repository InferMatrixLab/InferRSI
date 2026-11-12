"""Exercise the profile review page with narrative checks generated from real artifacts."""

import json
import shutil
import subprocess

import pytest
from test_optimization_story import campaign, log_document, write_log

from inferrsi.observability.dashboard import write_dashboard


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js runs the exported dashboard")
@pytest.mark.parametrize("conflicts", [True, False])
def test_profile_review_displays_narrative_evidence_conflicts(tmp_path, conflicts):
    document = log_document(campaign(tmp_path))
    manifest = tmp_path / "campaign.json"
    manifest.write_text(json.dumps({**json.loads(manifest.read_text()),
                                    "review_layout": "profile_first"}))
    if conflicts:
        document["knowledge"][0]["used_refs"].append("package:missing")
        document["iterations"][0]["decision"]["outcome"] = "rejected"
    write_log(tmp_path, document)
    html = write_dashboard(tmp_path)
    script = r"""
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const html=fs.readFileSync(process.argv[1],'utf8'), conflicts=process.argv[2]==='true';
class Element {
  constructor(){this.children=[];this.dataset={};this.hidden=false;this.textContent='';}
  append(...children){this.children.push(...children);}
  replaceChildren(){this.children=[];}
  addEventListener(event,listener){this[event]=listener;}
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
const source=html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
vm.runInNewContext(source,{document,window:{addEventListener(){}},
                          localStorage:{getItem(){return 'en';},setItem(){}}});
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
"""
    subprocess.run([shutil.which("node"), "-e", script, str(html), str(conflicts).lower()],
                   check=True)
