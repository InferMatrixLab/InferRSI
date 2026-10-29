"""Check the exact embedded reference validator with observed and mutated receipts."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).parent
wrapper = (root / 'run-synthetic.sbatch').read_text()
code = wrapper.split("<<'PYBENIGN'\n", 1)[1].split('\nPYBENIGN', 1)[0]
reference = root / 'reference.private'
original_execution = json.loads((reference / 'probe/execution.json').read_bytes())
original_stdout = json.loads((reference / 'probe/stdout.json').read_bytes())
rootfs = json.loads((reference / 'rootfs-before/rootfs.json').read_bytes())
bwrap = rootfs['executor']['binary_sha256']
cases = ['observed_success', 'exit_bool', 'exit_nonzero', 'timeout', 'wrong_phase',
         'wrong_output_digest', 'wrong_rootfs', 'wrong_executor', 'empty_checks',
         'missing_check', 'integer_check', 'integer_passed', 'duplicate_key']
with tempfile.TemporaryDirectory(dir=root) as temporary:
    fixture = Path(temporary)
    (fixture / 'probe').mkdir()
    (fixture / 'rootfs-before').mkdir()
    reference_rootfs = (reference / 'rootfs-before/rootfs.json').read_bytes()
    (fixture / 'rootfs-before/rootfs.json').write_bytes(reference_rootfs)
    for name in cases:
        execution, stdout = copy.deepcopy(original_execution), copy.deepcopy(original_stdout)
        if name == 'exit_bool':
            execution['exit_code'] = False
        elif name == 'exit_nonzero':
            execution['exit_code'] = 1
        elif name == 'timeout':
            execution['timed_out'] = True
        elif name == 'wrong_phase':
            execution['phase'] = 'unrelated'
        elif name == 'wrong_rootfs':
            execution['rootfs_digest'] = 'sha256:' + '0' * 64
        elif name == 'wrong_executor':
            execution['executor']['binary_sha256'] = '0' * 64
        elif name == 'empty_checks':
            stdout['checks'] = {}
        elif name == 'missing_check':
            del stdout['checks']['new_namespaces']
        elif name == 'integer_check':
            stdout['checks']['new_namespaces'] = 1
        elif name == 'integer_passed':
            stdout['passed'] = 1
        encoded = json.dumps(stdout).encode()
        execution['stdout_sha256'] = hashlib.sha256(encoded).hexdigest()
        if name == 'wrong_output_digest':
            execution['stdout_sha256'] = '0' * 64
        encoded_execution = json.dumps(execution)
        if name == 'duplicate_key':
            encoded_execution = '{"exit_code":1,' + encoded_execution[1:]
        (fixture / 'probe/execution.json').write_text(encoded_execution)
        (fixture / 'probe/stdout.json').write_bytes(encoded)
        result = subprocess.run([sys.executable, '-IBO', '-c', code, str(fixture), bwrap],
                                capture_output=True, check=False, timeout=5)
        if (result.returncode == 0) != (name == 'observed_success'):
            raise RuntimeError('Unexpected reference-validation outcome: ' + name)
report = {'benign_reference_cases': len(cases), 'cases': cases, 'optimized_python': True,
          'evaluator_or_sandbox_executed': False, 'passed': True}
(root / 'benign-reference-controls.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
