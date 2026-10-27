"""Document-only adaptation checks
no source implementation or native proof."""
import copy
import json
import re
import runpy
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
import yaml

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT / 'src/inferrsi/data/skill_library/repositories/husky'
FIXTURES = PROJECT / 'tests/fixtures/repo_to_skill/husky'


def card():
    return {'schema_version': 1, 'claim': 'A reported comparison needs qualification.',
            'evidence_class': 'author_report', 'source_url': 'https://husky.underdog.ai/',
            'identities': dict.fromkeys(('engine_revision', 'model_digest', 'workload_digest',
                                        'output_digest', 'backend')),
            'raw_artifacts_available': False}


def test_husky_document_links_and_unknowns_remain_explicit():
    header = yaml.safe_load((ROOT / 'SKILL.md').read_text().split('---', 2)[1])
    assert header['name'] == 'husky' and header['license'] == 'NO_LICENSE'
    assert header['disable-model-invocation'] is True
    assert len(list(ROOT.rglob('SKILL.md'))) == 1
    for path in ROOT.rglob('*.md'):
        text = path.read_text()
        assert '/workspace/' not in text and '/home/agent/' not in text
        for target in re.findall(r'\]\(([^)]+)\)', text):
            link = urlsplit(target)
            if link.scheme or link.netloc or not link.path:
                continue
            selected = (path.parent / unquote(link.path)).resolve()
            assert selected.is_relative_to(ROOT.resolve()) and selected.is_file()
    metadata = json.loads((ROOT / 'metadata.json').read_text())
    assert metadata['status'] == 'candidate' and metadata['empirical_validation'] == 'not_run'
    assert metadata['construction']['native_import'] == 'not-run'
    availability = json.loads((ROOT / 'references/source-availability.json').read_text())
    for key in ('canonical_repository', 'implementation_revision', 'raw_html_sha256'):
        assert availability[key] is None
    assert availability['source_license'] == 'UNKNOWN'
    assert not (ROOT / 'references/repo-routing-metadata.json').exists()


def test_husky_cases_reference_available_runtime_not_native_results():
    cases = list((FIXTURES / 'test-cases').rglob('assertions.json'))
    assert len(cases) == 5
    assert len(list((FIXTURES / 'test-cases/integration').glob('*/assertions.json'))) == 2
    for path in cases:
        value = json.loads(path.read_text())
        assert value['schema'] == 'disco.usability-case.v1'
        assert value['assertions'] and value['evidence_basis']
        assert (path.parent / 'user_request.txt').read_text().strip()
        for name in value['expected_skill_files']:
            assert (ROOT / name).is_file()


def test_husky_auditor_never_authenticates_even_a_complete_card(tmp_path):
    helper = ROOT / 'scripts/audit_evidence_card.py'
    audit = runpy.run_path(str(helper))['audit']
    unknown = audit(card())
    assert unknown['qualification'] == 'not_adjudicated' and len(unknown['missing_identity']) == 5
    complete = card()
    complete.update(evidence_class='runtime_run', raw_artifacts_available=True)
    complete['identities'] = dict.fromkeys(complete['identities'], 'self-reported')
    result = audit(complete)
    assert result['schema_valid'] and not result['missing_identity']
    assert result['qualification'] == 'not_adjudicated' and 'no artifact bytes' in result['scope']
    bad = []
    for key, value in [('schema_version', True), ('claim', ''), ('evidence_class', 'PASS'),
                       ('source_url', 'https://example.invalid'), ('identities', {}),
                       ('raw_artifacts_available', 'true')]:
        selected = copy.deepcopy(card())
        selected[key] = value
        bad.append(selected)
    selected = card()
    selected['unexpected'] = True
    bad.append(selected)
    selected = card()
    selected['identities']['backend'] = 1
    bad.append(selected)
    for selected in bad:
        with pytest.raises(ValueError):
            audit(selected)
    supplied = tmp_path / 'card.json'
    supplied.write_text(json.dumps(complete))
    cli = subprocess.run([sys.executable, str(helper), '--input', str(supplied)],
                         capture_output=True, text=True, check=True)
    assert json.loads(cli.stdout)['qualification'] == 'not_adjudicated'
    supplied.write_text('{}')
    invalid = subprocess.run([sys.executable, str(helper), '--input', str(supplied)],
                             capture_output=True, text=True)
    assert invalid.returncode == 2 and 'invalid research card' in invalid.stderr
    help_result = subprocess.run([sys.executable, str(helper), '--help'],
                                 capture_output=True)
    assert help_result.returncode == 0
