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
                          html.indexOf('  const stageNames = {'));
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
const quality = text('failed'), missing = text('MISSING');
const completeness = text('1 present / 1 missing');
const storyDecision = text('Decision: rejected · candidate-a');
const narrative = text('Explain the experiment', true);
const attr = {value: 'FAIL', hasAttribute: key => key === 'aria-label',
  getAttribute() { return this.value; }, setAttribute(_, value) { this.value = value; }};
const document = {body: {}, documentElement: {}, title: '',
  querySelectorAll: () => [attr],
  createTreeWalker: () => {let i = 0; return {currentNode: null, nextNode() {
    this.currentNode = nodes[i++]; return Boolean(this.currentNode);
  }}}};
const button = {setAttribute() {}};
const api = new Function('data', 'document', 'localStorage', 'byId', 'NodeFilter',
  source + '\nreturn {localizePage, setLanguage: value => language = value};')(
  {translations: {
    zh: {'FAIL':'PASS', 'INCONCLUSIVE':'PASS', 'failed':'passed', 'MISSING':'PRESENT',
         '1 present / 1 missing':'2 present / 0 missing', 'rejected':'adopted',
         'Explain the experiment':'解释实验'},
    en: {'FAIL':'PASS', 'INCONCLUSIVE':'PASS', 'failed':'passed', 'MISSING':'PRESENT',
         'Explain the experiment':'English explanation'}
  }}, document, {getItem: () => null}, () => button, {SHOW_TEXT: 4});

api.setLanguage('zh'); api.localizePage();
assert.equal(verdict.nodeValue, 'FAIL（失败）');
assert.equal(inconclusive.nodeValue, 'INCONCLUSIVE（结论不明确）');
assert.equal(quality.nodeValue, '失败');
assert.equal(missing.nodeValue, '缺失');
assert.equal(completeness.nodeValue, '已记录 1 / 缺失 1');
assert.equal(storyDecision.nodeValue, '决策：拒绝 · candidate-a');
assert.equal(attr.value, 'FAIL（失败）');
assert.equal(narrative.nodeValue, '解释实验');

api.setLanguage('en'); api.localizePage();
assert.equal(verdict.nodeValue, 'FAIL');
assert.equal(inconclusive.nodeValue, 'INCONCLUSIVE');
assert.equal(quality.nodeValue, 'failed');
assert.equal(missing.nodeValue, 'MISSING');
assert.equal(completeness.nodeValue, '1 present / 1 missing');
assert.equal(storyDecision.nodeValue, 'Decision: rejected · candidate-a');
assert.equal(attr.value, 'FAIL');
assert.equal(narrative.nodeValue, 'English explanation');
"""
    subprocess.run([shutil.which("node"), "-e", script, str(template)], check=True,
                   capture_output=True, text=True)
