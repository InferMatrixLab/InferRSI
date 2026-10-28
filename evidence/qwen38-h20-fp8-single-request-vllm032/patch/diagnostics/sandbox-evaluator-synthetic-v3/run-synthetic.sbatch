#!/usr/bin/env bash
# Trusted handwritten evaluator diagnostic; no real task data or model output.
#SBATCH --job-name=qwen38-eval-synthetic-v3
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:15:00
set -euo pipefail
umask 077
: "${TASK_ROOT:?}"
: "${SANDBOX_BUNDLE:?}"
: "${SANDBOX_FREEZE_SHA256:?}"
: "${SANDBOX_VENV:?}"
: "${REFERENCE_INSTALLATION:?}"
: "${REFERENCE_ROOTFS_SHA256:?}"
: "${REFERENCE_TERMINAL_SHA256:?}"
: "${REFERENCE_SLURM_SHA256:?}"
: "${REFERENCE_JOB_ID:?}"
: "${REFERENCE_EXECUTION_SHA256:?}" "${REFERENCE_STDOUT_SHA256:?}"
: "${BWRAP_BIN:?}" "${BWRAP_SHA256:?}" "${PYTHON_SHA256:?}"
: "${SYNTHETIC_SOURCE_DIR:?}"
: "${SYNTHETIC_RUNTIME_SHA256:?}"
: "${SYNTHETIC_PROBE_SHA256:?}"
: "${SYNTHETIC_SCRIPT_SHA256:?}"
: "${SYNTHETIC_OUTPUT:?}"
unset PYTHONPATH PYTHONHOME PYTHONOPTIMIZE PYTHONINSPECT PYTHONSTARTUP VIRTUAL_ENV
[[ -n ${SLURM_JOB_ID:-} && ${SLURM_GPUS_ON_NODE:-0} == 0 ]]
root=$(realpath -e "$TASK_ROOT")
check_path() {
    local value
    value=$(realpath -m "$1")
    case "$value" in "$root"/*) ;; *) echo 'Path escapes task root.' >&2; exit 2;; esac
}
check_digest() {
    if [[ ! "$2" =~ ^[a-f0-9]{64}$ ]]; then return 2; fi
    [[ $(sha256sum "$1" | cut -d' ' -f1) == "$2" ]]
}
for path in "$SANDBOX_BUNDLE" "$SANDBOX_VENV" "$REFERENCE_INSTALLATION" \
    "$SYNTHETIC_SOURCE_DIR" "$SYNTHETIC_OUTPUT" "$BWRAP_BIN"; do check_path "$path"; done
source_dir=$(cd -- "$SYNTHETIC_SOURCE_DIR" && pwd -P)
check_digest "$SANDBOX_VENV/bin/python" "$PYTHON_SHA256"
check_digest "$BWRAP_BIN" "$BWRAP_SHA256"
export PATH="$(dirname "$BWRAP_BIN"):/usr/bin:/bin"
[[ $(command -v bwrap) == "$BWRAP_BIN" ]]
check_digest "$source_dir/run-synthetic.sbatch" "$SYNTHETIC_SCRIPT_SHA256"
cmp "${BASH_SOURCE[0]}" "$source_dir/run-synthetic.sbatch"
check_digest "$source_dir/runtime.py" "$SYNTHETIC_RUNTIME_SHA256"
check_digest "$source_dir/synthetic_probe.py" "$SYNTHETIC_PROBE_SHA256"
check_digest "$SANDBOX_BUNDLE/freeze.sha256" "$SANDBOX_FREEZE_SHA256"
(cd "$SANDBOX_BUNDLE" && sha256sum --check --strict freeze.sha256)
# Bind both the scheduler outcome and the repaired completion record.
check_digest "$REFERENCE_INSTALLATION/terminal-status.json" "$REFERENCE_TERMINAL_SHA256"
check_digest "$REFERENCE_INSTALLATION/slurm-final.private.txt" "$REFERENCE_SLURM_SHA256"
"$SANDBOX_VENV/bin/python" -IB - "$REFERENCE_INSTALLATION" "$REFERENCE_JOB_ID" <<'PYREF'
import json
import re
import sys
from pathlib import Path
reference = Path(sys.argv[1])
job = sys.argv[2]
if not re.fullmatch(r"[0-9]+", job):
    raise ValueError('Invalid reference job ID')
def unique_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate terminal-record key')
        value[key] = item
    return value
terminal = json.loads((reference / 'terminal-status.json').read_bytes(), object_pairs_hook=unique_keys)
if terminal.get('completed') is not True or type(terminal.get('exit_code')) is not int:
    raise ValueError('Reference terminal record has invalid types')
if terminal != {'completed': True, 'signal': 'none', 'exit_code': 0, 'job_id': job}:
    raise ValueError('Reference installation did not complete normally')
slurm = (reference / 'slurm-final.private.txt').read_text()
for key, value in {'JobId': job, 'JobState': 'COMPLETED', 'ExitCode': '0:0'}.items():
    actual = re.findall(r'(?<!\S)' + re.escape(key) + r'=(\S*)', slurm)
    if actual != [value]:
        raise ValueError('Reference scheduler outcome is not completed or unambiguous')
if (reference / 'exit-code').read_text().strip() != '0':
    raise ValueError('Reference exit marker mismatch')
PYREF
check_digest "$REFERENCE_INSTALLATION/rootfs-before/rootfs.json" "$REFERENCE_ROOTFS_SHA256"
cmp "$REFERENCE_INSTALLATION/rootfs-before/rootfs.json" "$REFERENCE_INSTALLATION/rootfs-after/rootfs.json"

check_digest "$REFERENCE_INSTALLATION/probe/execution.json" "$REFERENCE_EXECUTION_SHA256"
check_digest "$REFERENCE_INSTALLATION/probe/stdout.json" "$REFERENCE_STDOUT_SHA256"
"$SANDBOX_VENV/bin/python" -IB - "$REFERENCE_INSTALLATION" "$BWRAP_SHA256" <<'PYBENIGN'
import hashlib
import json
import sys
from pathlib import Path
reference = Path(sys.argv[1])
def unique_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate reference key')
        value[key] = item
    return value
def read(name):
    return json.loads((reference / name).read_bytes(), object_pairs_hook=unique_keys)
execution = read('probe/execution.json')
rootfs = read('rootfs-before/rootfs.json')
stdout_raw = (reference / 'probe/stdout.json').read_bytes()
stdout = json.loads(stdout_raw, object_pairs_hook=unique_keys)
if execution.get('phase') != 'trusted_benign_probe' or type(execution.get('exit_code')) is not int or execution['exit_code'] != 0 or execution.get('timed_out') is not False:
    raise ValueError('Reference benign execution did not succeed')
if execution.get('stdout_sha256') != hashlib.sha256(stdout_raw).hexdigest() or execution.get('rootfs_digest') != rootfs.get('rootfs_digest'):
    raise ValueError('Reference benign output or runtime identity mismatch')
if execution.get('executor') != rootfs.get('executor') or rootfs['executor']['binary_sha256'] != sys.argv[2]:
    raise ValueError('Reference executor identity mismatch')
expected_checks = {'environment_cleared', 'fixed_rlimits', 'host_paths_absent', 'limited_cpu_affinity', 'network_blocked', 'new_namespaces', 'no_new_privileges', 'nonroot_namespace_uid', 'only_loopback', 'readonly_runtime_and_root', 'relocated_python', 'zero_effective_capabilities'}
checks = stdout.get('checks')
if stdout.get('passed') is not True or not isinstance(checks, dict) or set(checks) != expected_checks or any(value is not True for value in checks.values()):
    raise ValueError('Reference benign invariants incomplete or failed')
PYBENIGN
[[ ! -e "$SYNTHETIC_OUTPUT" && ! -L "$SYNTHETIC_OUTPUT" ]]
export TMPDIR="$root/tmp/qwen38-eval-synthetic-v3-${SLURM_JOB_ID}"
export XDG_CACHE_HOME="$root/cache/qwen38-eval-synthetic-v3-${SLURM_JOB_ID}"
export HF_HOME="$XDG_CACHE_HOME/huggingface"
export TORCH_HOME="$XDG_CACHE_HOME/torch"
export TRITON_CACHE_DIR="$XDG_CACHE_HOME/triton"
export VLLM_CACHE_ROOT="$XDG_CACHE_HOME/vllm"
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
unset PYTHONPATH PYTHONHOME PYTHONOPTIMIZE PYTHONINSPECT PYTHONSTARTUP VIRTUAL_ENV
for path in "$TMPDIR" "$XDG_CACHE_HOME" "$HF_HOME" "$TORCH_HOME" \
    "$TRITON_CACHE_DIR" "$VLLM_CACHE_ROOT"; do check_path "$path"; done
mkdir -p "$TMPDIR" "$XDG_CACHE_HOME" "$HF_HOME" "$TORCH_HOME" "$TRITON_CACHE_DIR" "$VLLM_CACHE_ROOT"
mkdir "$SYNTHETIC_OUTPUT"
# BEGIN TERMINAL RECORD: an EXIT code alone never authenticates completion.
task_completed=false
task_signal=none
finish_synthetic() {
    local status=$?
    trap - EXIT
    if [[ "$status" == 0 && "$task_completed" != true ]]; then status=1; fi
    if [[ "$status" != 0 ]]; then task_completed=false; fi
    printf '%s\n' "$status" > "$SYNTHETIC_OUTPUT/exit-code"
    printf '{"completed":%s,"signal":"%s","exit_code":%s,"job_id":"%s"}\n' \
        "$task_completed" "$task_signal" "$status" "$SLURM_JOB_ID" > "$SYNTHETIC_OUTPUT/terminal-status.json"
    exit "$status"
}
trap finish_synthetic EXIT
trap 'task_completed=false; task_signal=TERM; exit 143' TERM
trap 'task_completed=false; task_signal=INT; exit 130' INT
trap 'task_completed=false; task_signal=HUP; exit 129' HUP
# END TERMINAL RECORD
cp "$source_dir/run-synthetic.sbatch" "$source_dir/runtime.py" "$source_dir/synthetic_probe.py" "$SYNTHETIC_OUTPUT/"
cd "$root"
"$SANDBOX_VENV/bin/python" -IB "$source_dir/runtime.py" inventory --bundle "$SANDBOX_BUNDLE" \
    --output "$SYNTHETIC_OUTPUT/rootfs-before"
"$SANDBOX_VENV/bin/python" -IB - "$REFERENCE_INSTALLATION/rootfs-before/rootfs.json" \
    "$SYNTHETIC_OUTPUT/rootfs-before/rootfs.json" <<'PY'
import json
import sys
from pathlib import Path
before, current = [json.loads(Path(path).read_bytes()) for path in sys.argv[1:]]
for record in (before, current):
    record.pop('rootfs_digest')
    record['entries'] = [row for row in record['entries'] if row['path'] != '/opt/probe.py']
if before != current:
    raise ValueError('Installed runtime changed beyond the explicitly bound trusted probe')
PY
probe_status=0
"$SANDBOX_VENV/bin/python" -IB "$source_dir/runtime.py" probe --bundle "$SANDBOX_BUNDLE" \
    --inventory "$SYNTHETIC_OUTPUT/rootfs-before" --output "$SYNTHETIC_OUTPUT/probe" || probe_status=$?
printf '%s\n' "$probe_status" > "$SYNTHETIC_OUTPUT/probe-status"
post_status=0
run_postcheck() {
    local name=$1 status=0
    shift
    "$@" || status=$?
    printf '%s\t%s\n' "$name" "$status" >> "$SYNTHETIC_OUTPUT/postflight-status.tsv"
    if [[ "$status" != 0 ]]; then post_status=$status; fi
}
check_frozen_files() { (cd "$SANDBOX_BUNDLE" && sha256sum --check --strict freeze.sha256); }
run_postcheck inventory "$SANDBOX_VENV/bin/python" -IB "$source_dir/runtime.py" inventory \
    --bundle "$SANDBOX_BUNDLE" --output "$SYNTHETIC_OUTPUT/rootfs-after"
run_postcheck runtime-byte-comparison cmp "$SYNTHETIC_OUTPUT/rootfs-before/rootfs.json" \
    "$SYNTHETIC_OUTPUT/rootfs-after/rootfs.json"
run_postcheck runtime-script check_digest "$source_dir/runtime.py" "$SYNTHETIC_RUNTIME_SHA256"
run_postcheck synthetic-probe check_digest "$source_dir/synthetic_probe.py" "$SYNTHETIC_PROBE_SHA256"
run_postcheck batch-script check_digest "$source_dir/run-synthetic.sbatch" "$SYNTHETIC_SCRIPT_SHA256"
run_postcheck freeze-manifest check_digest "$SANDBOX_BUNDLE/freeze.sha256" "$SANDBOX_FREEZE_SHA256"
run_postcheck freeze-files check_frozen_files
run_postcheck python-binary check_digest "$SANDBOX_VENV/bin/python" "$PYTHON_SHA256"
run_postcheck bwrap-binary check_digest "$BWRAP_BIN" "$BWRAP_SHA256"
if [[ "$probe_status" != 0 ]]; then exit "$probe_status"; fi
if [[ "$post_status" != 0 ]]; then exit "$post_status"; fi
echo 'Trusted synthetic evaluator diagnostic completed; generated-code executor remains unqualified.'
task_completed=true
