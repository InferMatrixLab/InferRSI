"""Exercise loader-policy failures without invoking ldd or bubblewrap."""
import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('runtime_candidate', Path(__file__).with_name('runtime.py'))
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
checks = {}
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    base, site = root / 'base', root / 'site'
    for path in (base / 'lib', site):
        path.mkdir(parents=True)
    library = base / 'lib/libsynthetic.so'
    library.write_bytes(b'\x7fELFsynthetic')
    extension = site / 'extension.so'
    extension.write_bytes(b'\x7fELFsynthetic')
    outside = root / 'outside.so'
    outside.write_bytes(b'\x7fELFsynthetic')
    calls = []

    def successful(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, f'libsynthetic.so => {library}\n'.encode(), b'')

    with patch.dict(os.environ, {'LD_PRELOAD': '/synthetic-untrusted.so', 'LD_LIBRARY_PATH': '/synthetic-host'}):
        with patch.object(runtime.shutil, 'which', return_value='/usr/bin/ldd'):
            with patch.object(runtime.subprocess, 'run', side_effect=successful):
                assert runtime.system_dependencies((base, site)) == {}
            assert len(calls) == 2
            assert all(kw['env'] == {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'LD_LIBRARY_PATH': str(base / 'lib')} for _, kw in calls)
            checks['cleared_subprocess_environment_and_both_roots_scanned'] = True
            for name, code, stdout in (
                ('nonzero_rejected', 1, b''),
                ('missing_dependency_rejected_even_with_exit_zero', 0, b'libmissing.so => not found\n'),
                ('unexpected_external_dependency_rejected', 0, f'liboutside.so => {outside}\n'.encode()),
            ):
                result = subprocess.CompletedProcess(['/usr/bin/ldd'], code, stdout, b'')
                with patch.object(runtime.subprocess, 'run', return_value=result):
                    try:
                        runtime.system_dependencies((base, site))
                    except ValueError:
                        checks[name] = True
                    else:
                        raise AssertionError(name)
    locators = {'bwrap': '/synthetic/bwrap', 'python_root': str(base), 'site_root': str(site),
                'system_libraries': {}, 'python_relative': 'bin/python3.12'}
    args = runtime.command(locators, root / 'probe.py', {}, root / 'sentinel')
    index = args.index('LD_LIBRARY_PATH')
    assert args[index - 1:index + 2] == ['--setenv', 'LD_LIBRARY_PATH', '/opt/python/lib']
    assert '--clearenv' in args and '--disable-userns' in args and '--remount-ro' in args
    checks['sandbox_has_explicit_relocated_loader_directory_and_isolation_flags'] = True
report = {'scope': 'local_mocked_loader_controls', 'checks': checks, 'passed': all(checks.values()),
          'external_command_executed': False, 'runtime_qualified': False}
Path(__file__).with_name('loader-controls.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
