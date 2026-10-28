"""Compare explicit ELF lookup contexts without importing evaluator packages."""
import hashlib
import json
import os
import re
import subprocess
import sys
import sysconfig
import time
from pathlib import Path

root = Path(os.environ['TASK_ROOT']).resolve(strict=True)
output = Path(sys.argv[1]).resolve(strict=True)
base = Path(sys.base_prefix).resolve(strict=True)
site = Path(sysconfig.get_path('purelib')).resolve(strict=True)
if not all(p.is_relative_to(root) for p in (output, base, site)):
    raise ValueError('Runtime/output root escapes task root')
deadline = time.monotonic() + 240
clean_env = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}
scoped_env = {**clean_env, 'LD_LIBRARY_PATH': str(base / 'lib')}
observations = {
    'scope': 'controlled_elf_loader_context_diagnostic', 'verdict': 'INCONCLUSIVE',
    'runtime_changed': False, 'package_imports_performed': False,
    'inherited_loader_variable_presence': {
        name: name in os.environ for name in ('LD_LIBRARY_PATH', 'LD_PRELOAD', 'LD_AUDIT')
    },
    'controls': {'clean': clean_env, 'base_lib': {**clean_env, 'LD_LIBRARY_PATH': '/opt/python/lib'}},
    'selected_elf': [], 'target_comparison': {}, 'full_scan': [],
    'full_scan_complete': False, 'error_type': None,
}


def logical(path):
    for alias, directory in (('/opt/python', base), ('/opt/site-packages', site)):
        if path.is_relative_to(directory):
            return alias + '/' + path.relative_to(directory).as_posix()
    raise ValueError('Path is outside registered roots')


def run(args, env, prefix):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('Diagnostic deadline reached')
    result = subprocess.run(args, env=env, capture_output=True,
                            timeout=min(10, remaining), check=False)
    (output / (prefix + '.stdout.private.txt')).write_bytes(result.stdout)
    (output / (prefix + '.stderr.private.txt')).write_bytes(result.stderr)
    return result


def ldd_record(path, env, prefix):
    result = run(['/usr/bin/ldd', str(path)], env, prefix)
    stdout = result.stdout.decode(errors='replace')
    return {
        'path': logical(path), 'exit_code': result.returncode,
        'contains_not_found': 'not found' in stdout,
        'unresolved': re.findall(r'^\s*(\S+)\s+=>\s+not found\s*$', stdout, re.MULTILINE),
        'stdout_sha256': hashlib.sha256(result.stdout).hexdigest(),
        'stderr_sha256': hashlib.sha256(result.stderr).hexdigest(),
        'artifact_prefix': prefix,
    }


status = 1
try:
    target = base / 'lib/python3.12/lib-dynload/_tkinter.cpython-312-x86_64-linux-gnu.so'
    selected = [Path(sys._base_executable), target, base / 'lib/libtcl9.0.so',
                base / 'lib/libtcl9tk9.0.so']
    for index, path in enumerate(selected):
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(base) or not resolved.is_file():
            raise ValueError('Selected ELF escapes base runtime or is not a file')
        raw = resolved.read_bytes()
        if raw[:4] != b'\x7fELF':
            raise ValueError('Selected file is not ELF')
        result = run(['/usr/bin/readelf', '-d', str(resolved)], clean_env, f'selected-{index}')
        if result.returncode != 0:
            raise ValueError('readelf failed')
        dynamic = result.stdout.decode(errors='replace')
        # Paths stay private; the public facts retain hashes and literal origin-relative tags.
        tags = re.findall(r'\((NEEDED|RPATH|RUNPATH)\).*?\[(.*?)\]', dynamic)
        sanitized_tags = [(name, value.replace(str(base), '/opt/python').replace(str(site), '/opt/site-packages'))
                          for name, value in tags]
        observations['selected_elf'].append({
            'path': logical(path), 'resolved_path': logical(resolved), 'bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest(), 'dynamic_tags': sanitized_tags,
            'readelf_stdout_sha256': hashlib.sha256(result.stdout).hexdigest(),
        })
    for label, env in (('clean', clean_env), ('base_lib', scoped_env)):
        observations['target_comparison'][label] = ldd_record(target, env, 'target-' + label)
    for directory in (base, site):
        for path in sorted(directory.rglob('*')):
            if time.monotonic() >= deadline:
                raise TimeoutError('Diagnostic deadline reached')
            if not path.is_file() or path.is_symlink():
                continue
            with path.open('rb') as stream:
                if stream.read(4) != b'\x7fELF':
                    continue
            index = len(observations['full_scan'])
            observations['full_scan'].append(ldd_record(path, scoped_env, f'scan-{index:04d}'))
    observations['full_scan_complete'] = True
    status = 0
except Exception as error:
    observations['error_type'] = type(error).__name__
    raise
finally:
    (output / 'observations.json').write_text(json.dumps(observations, indent=2) + '\n')
    (output / 'context.private.json').write_text(json.dumps({
        'base': str(base), 'site': str(site), 'scoped_environment': scoped_env,
    }, indent=2) + '\n')
sys.exit(status)
