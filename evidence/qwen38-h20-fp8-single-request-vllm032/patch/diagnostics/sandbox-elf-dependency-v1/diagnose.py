"""Read-only reproduction of the first unresolved ELF in frozen inventory order."""
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

root = Path(os.environ['TASK_ROOT']).resolve(strict=True)
output = Path(sys.argv[1]).resolve(strict=True)
if not output.is_relative_to(root):
    raise ValueError('Output escapes task root')
base = Path(sys.base_prefix).resolve(strict=True)
site = Path(sysconfig.get_path('purelib')).resolve(strict=True)
if not all(p.is_relative_to(root) for p in (base, site)):
    raise ValueError('Interpreter roots escape task root')
ldd = shutil.which('ldd')
if ldd is None:
    raise ValueError('ldd unavailable')
scanned = 0
found = None
for alias, directory in (('/opt/python', base), ('/opt/site-packages', site)):
    for path in sorted(directory.rglob('*')):
        if not path.is_file() or path.is_symlink():
            continue
        with path.open('rb') as stream:
            if stream.read(4) != b'\x7fELF':
                continue
        scanned += 1
        result = subprocess.run([ldd, str(path)], capture_output=True, timeout=10, check=False)
        stdout = result.stdout.decode(errors='replace')
        if 'not found' in stdout:
            found = {'path': alias + '/' + path.relative_to(directory).as_posix(),
                     'ldd_exit_code': result.returncode,
                     'unresolved': re.findall(r'^\s*(\S+)\s+=>\s+not found\s*$', stdout, re.MULTILINE)}
            (output / 'ldd-stdout.private.txt').write_bytes(result.stdout)
            (output / 'ldd-stderr.private.txt').write_bytes(result.stderr)
            (output / 'selected-elf.private.txt').write_text(str(path) + '\n')
            break
    if found is not None:
        break
report = {'scope': 'first_missing_elf_inventory_diagnostic', 'scanned_elf_count': scanned,
          'first_missing': found, 'runtime_changed': False, 'evaluator_or_model_executed': False,
          'verdict': 'INCONCLUSIVE'}
(output / 'observations.json').write_text(json.dumps(report, indent=2) + '\n')
