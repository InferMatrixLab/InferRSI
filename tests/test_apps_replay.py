"""Apps envelopes for real RunStore contention and request conflicts.

These tests use a fixed terminal payload, not the production execution engine.
A live lock is held by another process; an exited owner is a distinct case.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from inferrsi.apps.api import execute
from inferrsi.apps.archive import read_result
from inferrsi.harness.run_store import Claim, RunStore, request_digest
from tests.test_apps_output import _bind, _request, _submit_to_run_store

_ROOT = Path(__file__).resolve().parents[1]
_HOLDER = """
import json, sys
from pathlib import Path
from inferrsi.harness.run_store import Claim, RunStore
root = Path(sys.argv[1])
params = json.loads((root / 'claim.json').read_text())
store = RunStore(root / 'run-store', 'apps-test')
claim = store.claim(params['attempt'], params['digest'])
assert isinstance(claim, Claim)
with claim:
    (root / 'owner-ready').write_text('locked')
    assert sys.stdin.readline() == 'release\\n'
"""


def _assert_error(output, workspace, request, code, exit_code):
    assert output.result['reason_code'] == code
    assert output.result['error']['code'] == code
    assert output.result['error']['attempt_id'] == request['attempt']['attempt_id']
    assert output.result['exit_code'] == exit_code
    assert output.result['record_ref'] is None
    assert output.result['execution'] is None
    assert read_result(workspace, output.output_id) == output


def test_apps_reentry_with_live_owner_then_owner_gone(tmp_path):
    request = _request()
    digest = request_digest(_bind(request))
    (tmp_path / 'claim.json').write_text(json.dumps({
        'attempt': request['attempt'], 'digest': digest,
    }))
    child = subprocess.Popen(
        [sys.executable, '-c', _HOLDER, str(tmp_path)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env={**os.environ, 'PYTHONPATH': str(_ROOT / 'src')},
    )
    try:
        deadline = time.monotonic() + 30
        while not (tmp_path / 'owner-ready').exists():
            assert child.poll() is None, child.communicate(timeout=5)
            assert time.monotonic() < deadline, 'owner did not acquire its lock'
            time.sleep(0.01)
        assert child.poll() is None
        # This calls the real claim path through Apps, not a mocked PublicError.
        output = execute(
            request, workspace=tmp_path, output_id='held', bind_execution=_bind,
            execute_harness=lambda spec: _submit_to_run_store(tmp_path, spec),
        )
        _assert_error(output, tmp_path, request, 'AttemptInProgress', 4)
        assert child.poll() is None  # The holder remained live throughout re-entry.
        stdout, stderr = child.communicate('release\n', timeout=15)
        assert child.returncode == 0, (stdout, stderr)
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=10)

    # Released without committing is owner gone, NOT an unconfirmable held lock.
    output = execute(
        request, workspace=tmp_path, output_id='gone', bind_execution=_bind,
        execute_harness=lambda spec: _submit_to_run_store(tmp_path, spec),
    )
    _assert_error(output, tmp_path, request, 'RecoveryRequired', 5)
    assert 'owner is gone' in output.result['error']['message']


def test_apps_same_attempt_changed_digest_preserves_committed_record(tmp_path):
    request = _request()
    original = _submit_to_run_store(tmp_path, _bind(request))
    store = RunStore(tmp_path / 'run-store', 'apps-test')
    before = store.committed(request['attempt']['attempt_id'])
    changed = {**request, 'output_root': 'attempts/alternate-output'}
    assert request_digest(_bind(changed)) != original['request_digest']

    def submit(spec):
        # A valid changed runtime location retains the same attempt identity.
        claimed = store.claim(changed['attempt'], request_digest(spec))
        if isinstance(claimed, Claim):
            claimed.release()
        raise AssertionError('RunStore accepted a conflicting request')

    output = execute(
        changed, workspace=tmp_path, output_id='conflict',
        bind_execution=_bind, execute_harness=submit,
    )
    _assert_error(output, tmp_path, changed, 'RequestConflict', 2)
    after = store.committed(changed['attempt']['attempt_id'])
    assert after.record_ref == before.record_ref
    assert after.payload_bytes == before.payload_bytes
    assert store.open(before.record_ref['artifact']).read() == before.payload_bytes
