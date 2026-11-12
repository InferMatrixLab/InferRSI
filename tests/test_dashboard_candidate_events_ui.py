"""A bound agent event can be inspected without a caller-authored optimization trace."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed for this UI regression")
def test_candidate_event_disclosure_and_live_elapsed():
    template = Path(__file__).parents[1] / "src/inferrsi/observability/template.html"
    script = r"""
const fs=require('node:fs'),assert=require('node:assert/strict');
const html=fs.readFileSync(process.argv[1],'utf8');
const section=(a,b)=>html.slice(html.indexOf('  function '+a+'('),
                                html.indexOf('  function '+b+'('));
const source=section('jumpToEvent','renderRoundInputs')+
             section('refreshElapsed','eventLabel')+section('eventLabel','stageFacts')+
             section('renderCandidateEvents','renderCandidate');
const bound=[
  {source:'events',line:1,phase:'complete',details:{state:'completed'},refs:[]},
  {source:'agent_trace',line:1,type:'agent.tool',stage:'search',tool:'submit_candidate',
   details:{count:3},refs:[{sha256:'a'.repeat(64)}]}];
const row={candidate_id:'first',round:1,run_id:'run',events:bound,optimization_trace:null,
  unlinked_agent_events:[{source:'agent_trace',line:2,details:{name:'UNBOUND_PAYLOAD'}}],
  agent_trace_links:{unlinked:[2],mismatched:[3]},corrupt_event_sources:{events:[],agent_trace:[4]}};
const node=(tag,text='')=>({tag,textContent:text,children:[],dataset:{},listeners:{},open:false,
  get childElementCount(){return this.children.length},
  append(...nodes){this.children.push(...nodes)},setAttribute(){},
  addEventListener(name,fn){this.listeners[name]=fn},showModal(){this.open=true}});
const all=n=>[n,...n.children.flatMap(all)];
const panels=Object.fromEntries(
  ['event-body','event-heading','event-record'].map(id=>[id,node(id)]));
const clockCell=node('td');clockCell.dataset.started='2026-01-01T00:00:00Z';
const env={data:{candidates:[row]},selected:0,identity:()=>row.candidate_id,byId:id=>panels[id],
  clear:n=>n.children=[],node,translated:s=>s,workNames:{},stageNames:{search:'Candidate search'},
  refText:ref=>ref.sha256,liveMode:true,serverTime:Date.parse('2026-01-01T00:00:07Z'),
  document:{querySelectorAll:()=>[clockCell]},duration:s=>s+' s'};
const api=new Function(...Object.keys(env),source+
  '\nreturn {renderCandidateEvents,refreshElapsed,jumpToEvent};')(...Object.values(env));
const root=node('div');
api.renderCandidateEvents(root,row);
const fold=root.children[0];
assert.equal(fold.tag,'details');assert.equal(fold.open,false);
assert.equal(all(fold).filter(n=>n.tag==='button').length,0);
fold.open=true;fold.listeners.toggle();
fold.listeners.toggle();
const buttons=all(fold).filter(n=>n.tag==='button');
assert.equal(buttons.length,2);
const button=buttons.find(b=>b.textContent.includes('submit_candidate'));
assert(button.textContent.includes('agent_trace:1'));button.listeners.click();
assert(panels['event-record'].open);assert.equal(panels['event-heading'].textContent,'Tool call');
const content=all(panels['event-body']).map(n=>n.textContent).join('\n');
assert(content.includes('agent_trace:1') && content.includes('submit_candidate'));
assert(content.includes('"count": 3') && content.includes('a'.repeat(64)));
const labels=all(fold).map(n=>n.textContent).join('\n');
for(const ref of ['agent_trace:2','agent_trace:3','agent_trace:4'])assert(labels.includes(ref));
assert(!labels.includes('UNBOUND_PAYLOAD'));
panels['event-record'].open=false;api.jumpToEvent('agent_trace',2);
assert.equal(panels['event-record'].open,false);
api.refreshElapsed();assert.equal(clockCell.textContent,'Elapsed since start · 7 s');
"""
    subprocess.run([shutil.which("node"), "-e", script, str(template)], check=True,
                   capture_output=True, text=True)
