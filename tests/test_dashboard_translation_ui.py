"""The narrative overlay must not relabel evidence-derived UI text."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed for the UI regression")
def test_translation_overlay_cannot_relabel_verdicts_or_evidence():
    template = Path(__file__).parents[1] / "src/inferrsi/data/dashboard/template.html"
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
    template = Path(__file__).parents[1] / "src/inferrsi/data/dashboard/template.html"
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
