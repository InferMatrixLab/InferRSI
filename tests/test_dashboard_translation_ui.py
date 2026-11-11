"""The narrative overlay must not relabel evidence-derived UI text."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed for the UI regression")
def test_round_outcome_and_stage_strip_follow_recorded_evidence():
    template = Path(__file__).parents[1] / "src/inferrsi/observability/template.html"
    script = r"""
const fs=require('node:fs'),assert=require('node:assert/strict');
const html=fs.readFileSync(process.argv[1],'utf8');
const source=html.slice(html.indexOf('  function duration('),
                        html.indexOf('  function outcomeTone('))+
             html.slice(html.indexOf('  function stageFacts('),
                        html.indexOf('  function logFacts('));
const events=[
  {line:1,source:'events',stage:'execution',time:'2026-01-01T00:00:01Z',details:{state:'running'}},
  {line:2,source:'events',stage:'execution',time:'2026-01-01T00:00:02Z'},
  {line:3,source:'events',stage:'validation',time:'2026-01-01T00:00:03Z'},
  {line:3,source:'agent_trace',stage:'diagnosis',time:'2026-01-01T00:00:03Z'},
  {line:4,source:'events',stage:'review',time:null,phase:'crashed'},
  {line:5,source:'events',stage:'review',time:'2026-01-01T00:00:04Z'}];
const row={state:'running',round:1,events,run_workflow:{nodes:[
  {line:1,state:'completed'},{line:3,state:'running'}]}};
const data={stages:['execution','validation','diagnosis','review'].map(name=>({name})),
            candidates:[row]};
const api=new Function('data','language','translated',source+
  '\nreturn {attemptResult,outcomeSentence,stageFacts,workDuration};')(data,'en',s=>s);
assert.equal(api.workDuration({seconds:2,duration_source:'command'}),'Command duration · 2.0 s');
assert.equal(api.workDuration({seconds:3,duration_source:'phase'}),'Phase duration · 3.0 s');
for(const state of ['complete','partial']){
  const items=[{kind:'observation',result:'not an attempt'},
    {kind:'attempt',result:'first'},{kind:'attempt',result:'final result'},
    {kind:'attempt',result:''}];
  assert.equal(api.attemptResult({optimization_trace:{steps:{state,items}}}),'final result');
}
const result={direction:'maximize',metric_key:'throughput',improvement_pct:5,
  minimum_improvement_pct:10,quality:'passed',decision:'rejected'};
assert.equal(api.outcomeSentence(result),
  'Throughput rose 5.0%, short of the 10.0% target, the accuracy check passed, '+
  'the round rejected this candidate.');
assert(api.outcomeSentence({...result,metric_key:'joules',direction:'minimize'}).
  startsWith('joules fell 5.0%,'));
assert(api.outcomeSentence({...result,improvement_pct:-1}).startsWith('Throughput fell 1.0%,'));
assert(api.outcomeSentence({...result,improvement_pct:0}).startsWith('Throughput was unchanged,'));
const facts=api.stageFacts();
assert.equal(facts.execution.open,false);assert.equal(facts.execution.untimed,false);
assert.equal(facts.validation.open,true);assert.equal(facts.diagnosis.open,false);
assert.equal(facts.review.failed,true);assert.equal(facts.review.untimed,true);
const strip=html.slice(html.indexOf('  function renderWorkflow('),
                      html.indexOf('  function renderRows('));
const node=(tag,text,cls)=>({text,cls,children:[],setAttribute(){},addEventListener(){},
  appendChild(n){this.children.push(n);}});
const root=node('div');
const deps={byId:()=>root,clear:()=>{},stageFacts:api.stageFacts,logFacts:()=>({}),data,
  stageSelect:{value:'diagnosis'},node,stageNames:{},translated:s=>s,duration:s=>s};
data.stages.forEach(s=>s.state='recorded');
new Function(...Object.keys(deps),strip+'\nrenderWorkflow();')(...Object.values(deps));
const [execution,validation,diagnosis,review]=root.children;
assert(!execution.cls.includes('current'));assert(validation.cls.includes('current'));
assert(diagnosis.cls.includes('selected') && !diagnosis.cls.includes('current'));
assert(review.cls.includes('stage-failed'));assert(!review.children.some(n=>n.cls==='stage-time'));
row.state='crashed';row.run_workflow.nodes[1].state='failed';
const ended=api.stageFacts();assert.equal(ended.validation.open,false);
assert.equal(ended.validation.failed,true);assert.equal(ended.diagnosis.failed,false);
"""
    subprocess.run([shutil.which("node"), "-e", script, str(template)], check=True,
                   capture_output=True, text=True)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed for the UI regression")
def test_profile_reader_matches_baseline_and_keeps_unavailable_capture_ids():
    template = Path(__file__).parents[1] / "src/inferrsi/observability/review_template.html"
    script = r"""
const fs=require('node:fs'),assert=require('node:assert/strict');
const html=fs.readFileSync(process.argv[1],'utf8');
const source=html.slice(html.indexOf('function renderCaptures('),
                        html.indexOf('function render(){'));
const box={replaceChildren(){}},section={},log=[],calls=[];
const data={profile_captures:[],unavailable_profiles:['missing','changed']};
const run=new Function('data','timelineDraws','byId','timeline','p','tr',
  source+'\nreturn renderCaptures;')(data,new Map(),id=>id==='captures'?box:section,
  (_,c,b)=>calls.push([c.id,b?.id]),(_,text)=>log.push(text),(zh,en)=>en);
run(new Set());assert.equal(section.hidden,false);assert.equal(log.length,2);
assert(log[0].startsWith('missing ·'));assert(log[1].startsWith('changed ·'));
data.unavailable_profiles=[];run(new Set());assert.equal(section.hidden,true);
function cap(id,phase,comparison_key){
  return {id,phase,comparison_key,duration_us:1,source:{sha256:'a'.repeat(64)},tracks:[{}]};
}
data.profile_captures=[cap('base-a','baseline','a'),cap('base-b','baseline','b'),
  cap('test','candidate','b')];
run(new Set());assert.deepEqual(calls.at(-1),['test','base-b']);
data.profile_captures.unshift(cap('ambiguous','baseline','b'));
run(new Set());assert.deepEqual(calls.at(-1),['test',undefined]);
"""
    subprocess.run([shutil.which("node"), "-e", script, str(template)], check=True,
                   capture_output=True, text=True)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed for trace decoding")
def test_full_profile_reader_checks_original_bytes_and_tracks_overlapping_events():
    template = Path(__file__).parents[1] / "src/inferrsi/observability/review_template.html"
    script = r"""
const fs=require('node:fs'),assert=require('node:assert/strict');
const {gzipSync}=require('node:zlib'),{createHash,webcrypto}=require('node:crypto');
const html=fs.readFileSync(process.argv[1],'utf8');
const code=html.slice(html.indexOf('function traceCategory('),html.indexOf('function timeline('));
const read=new Function('tr','crypto',code+'\nreturn readTraceFile;')((zh,en)=>en,webcrypto);
const bytes=gzipSync(JSON.stringify({traceEvents:[
  {ph:'M',name:'metadata',ts:1},
  {ph:'X',ts:10,dur:256,pid:2,tid:3,cat:'kernel',name:'long'},
  {ph:'X',ts:12,dur:1,pid:2,tid:3,cat:'gpu_memcpy',name:'copy'},
  {ph:'X',ts:14,dur:4,pid:1,tid:3,cat:'cpu_op',name:'cpu'},
  {ph:'X',ts:15,dur:2,pid:1,tid:3,cat:'gpu_user_annotation',name:'stage'}]}));
const blob=new Blob([bytes]);
(async()=>{
  await assert.rejects(()=>read(blob,'a'.repeat(64)),/SHA-256/);
  const timeline=await read(blob,createHash('sha256').update(bytes).digest('hex'));
  assert.equal(timeline.start_us,10);assert.equal(timeline.duration_us,256);
  assert.equal(timeline.event_count,4);
  assert.deepEqual(timeline.tracks.map(t=>t.kind),['gpu','cpu','stage']);
  assert.equal(timeline.tracks[0].bins[2],2);assert.equal(timeline.tracks[0].bins[3],1);
  assert.equal(timeline.tracks[0].events[1].name,'copy');
  const compact=gzipSync(JSON.stringify({names:['kernel','copy'],
    lanes:[{name:'stream 4',kind:'gpu'}],events:[[0,0,10,256],[0,1,12,1]]}));
  const imported=await read(new Blob([compact]),'b'.repeat(64),
    createHash('sha256').update(compact).digest('hex'));
  assert.equal(imported.event_count,2);assert.equal(imported.tracks[0].bins[2],2);
  assert.equal(imported.tracks[0].events[1].name,'copy');
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
    subprocess.run([shutil.which("node"), "-e", script, str(template)], check=True,
                   capture_output=True, text=True)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed for the UI regression")
def test_round_review_shows_only_linked_retrievals_in_declared_order():
    template = Path(__file__).parents[1] / "src/inferrsi/observability/template.html"
    script = r"""
const fs=require('node:fs'), assert=require('node:assert/strict');
const html=fs.readFileSync(process.argv[1],'utf8');
const source=html.slice(
  html.indexOf('  function renderRoundInputs('),html.indexOf('  function renderRunReview('));
const story={iterations:[
  {round:1,candidates:[{candidate_id:'a'}],context_ids:['broad','specific']},
  {round:2,candidates:[{candidate_id:'b'}],context_ids:['later']}],
  retrievals:['specific','later','broad'].map(context_id=>({context_id}))};
function captures(round,candidate_id,storyData){
  const ids=[];
  const node=()=>({append(){}});
  const renderKnowledge=(_,selection)=>ids.push(...selection.retrievals.map(r=>r.context_id));
  const render=new Function('data','node','renderKnowledge',source+'\nreturn renderRoundInputs;');
  render({story:storyData},node,renderKnowledge)(node(),{round,candidate_id});
  return ids;
}
assert.deepEqual(captures(1,'a',story),['broad','specific']);
assert.deepEqual(captures(2,'b',story),['later']);
assert.deepEqual(captures(1,'b',story),[]);
assert.deepEqual(captures(1,'a',{state:'not_recorded'}),[]);
"""
    subprocess.run([shutil.which("node"), "-e", script, str(template)], check=True,
                   capture_output=True, text=True)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed for the UI regression")
def test_translation_overlay_cannot_relabel_verdicts_or_evidence():
    template = Path(__file__).parents[1] / "src/inferrsi/observability/template.html"
    script = r"""
const fs = require('node:fs');
const assert = require('node:assert/strict');
const html = fs.readFileSync(process.argv[1], 'utf8');
const source = html.slice(html.indexOf('  const chinese = {'),
                          html.indexOf('  const stageNames = {'))
  + html.slice(html.indexOf('  function renderIntegration('),
               html.indexOf('  function renderStats()'))
  + html.split('\n').find(line=>line.includes('const measurement ='));
assert(source.includes('function localizePage()'));

const nodes = [];
function text(value, narrative = false) {
  const parentElement = {closest: selector =>
    selector === '[data-narrative]' && narrative ? {} : null};
  const node = {nodeValue: value, parentElement};
  nodes.push(node);
  return node;
}
const verdict = text('FAIL'), inconclusive = text('INCONCLUSIVE');
const quality = text('failed'), cancelled = text('cancelled'), missing = text('MISSING');
const completeness = text('1 present / 1 missing');
const storyDecision = text('Decision: rejected · candidate-a');
const missingRun = text('candidate b has no recorded run');
const unavailable = text('evidence candidate:b has unavailable run evidence');
const missingOutcome = text('evidence candidate:b has no recorded outcome');
const unavailableLabel = text('Run evidence unavailable');
const missingOutcomeLabel = text('No recorded outcome');
const narrative = text('Explain the experiment', true);
const noMetrics=text(
  'Protocol-specific absolute measurements; recorded verdicts are not recomputed. '+
  '2 external record(s) have no recorded metrics; see candidate details and events.');
const attr = {value: 'FAIL', hasAttribute: key => key === 'aria-label',
  getAttribute() { return this.value; }, setAttribute(_, value) { this.value = value; }};
const document = {body: {}, documentElement: {}, title: '',
  querySelectorAll: () => [attr],
  createTreeWalker: () => {let i = 0; return {currentNode: null, nextNode() {
    this.currentNode = nodes[i++]; return Boolean(this.currentNode);
  }}}};
const button = {setAttribute() {}};
const element=(tag, value)=>({tag, children:[], hidden:false,
  appendChild(child){this.children.push(child);},
  get firstChild(){return this.children[0];},
  text:value===undefined?null:text(value)});
const integrationRoot=element('div');
const api = new Function('data', 'document', 'localStorage', 'byId', 'NodeFilter', 'node', 'clear',
  source + '\nreturn {localizePage, renderIntegration, measurement, '+
  'setLanguage: value => language = value};')(
  {translations: {
    zh: {'FAIL':'PASS', 'INCONCLUSIVE':'PASS', 'failed':'passed', 'MISSING':'PRESENT',
         '1 present / 1 missing':'2 present / 0 missing', 'rejected':'adopted',
         'Explain the experiment':'解释实验'},
    en: {'FAIL':'PASS', 'INCONCLUSIVE':'PASS', 'failed':'passed', 'MISSING':'PRESENT',
         'Explain the experiment':'English explanation'}
  }}, document, {getItem: () => null}, id=>id==='integration-note'?integrationRoot:button,
  {SHOW_TEXT: 4}, element, root=>{root.children=[];});
api.renderIntegration({state:'connected',external_records:1,stage_declaration:'explicit_empty',
  collection:{state:'stale',observed_at:'2026-01-01T00:00:00Z'}});
assert.equal(integrationRoot.children.length,3);
assert(integrationRoot.children.every(el=>el.tag==='p'));
assert.equal(api.measurement(undefined),'Not recorded');

api.setLanguage('zh'); api.localizePage();
assert(integrationRoot.children[0].text.nodeValue.startsWith('外部记录已接入'));
assert.equal(integrationRoot.children[1].children[0].text.nodeValue,'数据采集');
assert.equal(integrationRoot.children[1].children[2].text.nodeValue,'数据陈旧');
assert(integrationRoot.children[2].text.nodeValue.includes('显式声明为空'));
assert(noMetrics.nodeValue.includes('2 条外部记录未记录指标'));
assert.equal(verdict.nodeValue, 'FAIL（失败）');
assert.equal(inconclusive.nodeValue, 'INCONCLUSIVE（结论不明确）');
assert.equal(quality.nodeValue, '失败');
assert.equal(cancelled.nodeValue, '已中止');
assert.equal(missing.nodeValue, '缺失');
assert.equal(completeness.nodeValue, '已记录 1 / 缺失 1');
assert.equal(storyDecision.nodeValue, '决策：拒绝 · candidate-a');
assert.equal(missingRun.nodeValue, '候选方案 b 没有运行记录');
assert.equal(unavailable.nodeValue, '证据 candidate:b 的运行证据不可用');
assert.equal(missingOutcome.nodeValue, '证据 candidate:b 未记录结果');
assert.equal(unavailableLabel.nodeValue, '运行证据不可用');
assert.equal(missingOutcomeLabel.nodeValue, '未记录结果');
assert.equal(attr.value, 'FAIL（失败）');
assert.equal(narrative.nodeValue, '解释实验');

api.setLanguage('en'); api.localizePage();
assert(integrationRoot.children[0].text.nodeValue.startsWith('External records connected.'));
assert.equal(integrationRoot.children[1].children[0].text.nodeValue,'Source collection');
assert.equal(integrationRoot.children[1].children[2].text.nodeValue,'stale');
assert(integrationRoot.children[2].text.nodeValue.startsWith(
  'stages_declared is explicitly empty'));
assert(noMetrics.nodeValue.includes('2 external record(s) have no recorded metrics'));
assert.equal(verdict.nodeValue, 'FAIL');
assert.equal(inconclusive.nodeValue, 'INCONCLUSIVE');
assert.equal(quality.nodeValue, 'failed');
assert.equal(cancelled.nodeValue, 'cancelled');
assert.equal(missing.nodeValue, 'MISSING');
assert.equal(completeness.nodeValue, '1 present / 1 missing');
assert.equal(storyDecision.nodeValue, 'Decision: rejected · candidate-a');
assert.equal(missingRun.nodeValue, 'candidate b has no recorded run');
assert.equal(unavailable.nodeValue, 'evidence candidate:b has unavailable run evidence');
assert.equal(missingOutcome.nodeValue, 'evidence candidate:b has no recorded outcome');
assert.equal(unavailableLabel.nodeValue, 'Run evidence unavailable');
assert.equal(missingOutcomeLabel.nodeValue, 'No recorded outcome');
assert.equal(attr.value, 'FAIL');
assert.equal(narrative.nodeValue, 'English explanation');
"""
    subprocess.run([shutil.which("node"), "-e", script, str(template)], check=True,
                   capture_output=True, text=True)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed for the UI regression")
def test_mixed_campaign_counts_native_and_external_failures_separately():
    template = Path(__file__).parents[1] / "src/inferrsi/observability/template.html"
    script = r"""
const fs=require('node:fs'), assert=require('node:assert/strict');
const html=fs.readFileSync(process.argv[1],'utf8');
const render=html.slice(html.indexOf('  function renderStats()'),
                        html.indexOf('  function renderWorkflow()'));
function node(tag,text){return {tag,text,children:[],
  appendChild(child){this.children.push(child);}};}
const elements={'stats':node('div'),'overview-note':node('small')};
const data={candidates:[],overview:{comparison_state:'no_data',best_improvement_pct:null,
  target_gap_pct:null,target_improvement_pct:null},rounds:null};
const run=new Function('data','byId','node','clear','renderIntegration','missingRefs','value',
  render+';renderStats();');
function stats(rows){
  data.candidates=rows;
  run(data,id=>elements[id],node,el=>{el.children=[];},()=>{},()=>[],()=> 'Not recorded');
  return Object.fromEntries(elements.stats.children.map(card=>
    [card.children[0].text,{value:card.children[1].text,note:card.children[2].text}]));
}
const native={state:'completed',quality:'passed',outcome:'improved',decision:'not_recorded'};
const external={state:'completed',quality:'passed',outcome:'unverified',decision:'not_recorded',
  external:{metrics:[],performance_verdict:'FAIL',quality_verdict:'PASS'}};
let cards=stats([native,external]);
assert.equal(cards['Native failed / regressed'].value,'0');
assert.equal(cards['Recorded external performance failures'].value,'1');
assert(!('Failed / regressed' in cards));
assert.equal(cards['Native failed / regressed'].note,
  'Native runs only; includes failures and rollbacks');
for(const failure of [{outcome:'failed'},{outcome:'quality_failed'},{outcome:'regressed'},
                      {decision:'rolled_back'}]){
  cards=stats([{...native,...failure},external]);
  assert.equal(cards['Native failed / regressed'].value,'1');
  assert.equal(cards['Recorded external performance failures'].value,'1');
}
for(const verdict of ['PASS','INCONCLUSIVE','not_recorded']){
  cards=stats([native,{...external,external:{...external.external,performance_verdict:verdict}}]);
  assert.equal(cards['Recorded external performance failures'].value,'0');
}
cards=stats([external]);
assert.equal(cards['Recorded performance failures'].value,'1');
assert(!('Native failed / regressed' in cards));
cards=stats([native]);
assert.equal(cards['Failed / regressed'].value,'0');
assert(!('Recorded external performance failures' in cards));
cards=stats([]);
assert.equal(cards['Failed / regressed'].value,'Not recorded');
"""
    subprocess.run([shutil.which("node"), "-e", script, str(template)], check=True,
                   capture_output=True, text=True)
