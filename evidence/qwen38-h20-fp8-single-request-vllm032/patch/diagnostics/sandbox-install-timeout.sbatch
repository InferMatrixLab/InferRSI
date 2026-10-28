#!/usr/bin/env bash
# Install a reviewed dependency freeze and run only the trusted benign probe.
#SBATCH --job-name=qwen38-eval-sandbox-install
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:30:00
set -euo pipefail
umask 077
: "${TASK_ROOT:?}"
: "${BASE_PYTHON:?}"
: "${UV_BIN:?}"
: "${SANDBOX_BUNDLE:?}"
: "${SANDBOX_FREEZE_SHA256:?}"
: "${SANDBOX_VENV:?}"
: "${INSTALL_SOURCE_DIR:?}"
: "${INSTALL_SCRIPT_SHA256:?}"
task_uv_executable=$UV_BIN
[[ -n ${SLURM_JOB_ID:-} && ${SLURM_GPUS_ON_NODE:-0} == 0 ]]
root=$(realpath -e "$TASK_ROOT")
check_path() {
    local value
    value=$(realpath -m "$1")
    case "$value" in "$root"/*) ;; *) echo 'Path escapes task root.' >&2; exit 2;; esac
}
for path in "$BASE_PYTHON" "$task_uv_executable" "$SANDBOX_BUNDLE" "$SANDBOX_VENV" "$INSTALL_SOURCE_DIR"; do
    check_path "$path"
done
source_dir=$(cd -- "$INSTALL_SOURCE_DIR" && pwd -P)
check_digest() {
    [[ "$2" =~ ^[a-f0-9]{64}$ ]]
    [[ $(sha256sum "$1" | cut -d' ' -f1) == "$2" ]]
}
check_digest "$source_dir/install-reviewed.sbatch" "$INSTALL_SCRIPT_SHA256"
cmp "${BASH_SOURCE[0]}" "$source_dir/install-reviewed.sbatch"
check_digest "$SANDBOX_BUNDLE/freeze.sha256" "$SANDBOX_FREEZE_SHA256"
(cd "$SANDBOX_BUNDLE" && sha256sum --check --strict freeze.sha256)
check_digest "$task_uv_executable" "$(cat "$SANDBOX_BUNDLE/uv-sha256.txt")"
check_digest "$BASE_PYTHON" "$(cat "$SANDBOX_BUNDLE/python-sha256.txt")"
for path in "$SANDBOX_BUNDLE/runtime.py" "$SANDBOX_BUNDLE/benign_probe.py" \
    "$SANDBOX_BUNDLE/source" "$SANDBOX_BUNDLE/wheelhouse"; do check_path "$path"; done
[[ ! -e "$SANDBOX_VENV" && ! -L "$SANDBOX_VENV" ]]
for task_resolver_variable in "${!UV_@}" "${!PIP_@}"; do
    if [[ -n "$task_resolver_variable" ]]; then unset "$task_resolver_variable"; fi
done
export TMPDIR="$root/tmp/qwen38-eval-sandbox-install-${SLURM_JOB_ID}"
export XDG_CACHE_HOME="$root/cache/qwen38-eval-sandbox"
export UV_CACHE_DIR="$XDG_CACHE_HOME/uv"
export HF_HOME="$XDG_CACHE_HOME/huggingface"
export TORCH_HOME="$XDG_CACHE_HOME/torch"
export TRITON_CACHE_DIR="$XDG_CACHE_HOME/triton"
export VLLM_CACHE_ROOT="$XDG_CACHE_HOME/vllm"
export UV_PYTHON_INSTALL_DIR="$root/software/python"
export UV_PYTHON_DOWNLOADS=never
export UV_HTTP_TIMEOUT=60
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
unset PYTHONPATH VIRTUAL_ENV
for path in "$TMPDIR" "$XDG_CACHE_HOME" "$UV_CACHE_DIR" "$HF_HOME" "$TORCH_HOME" \
    "$TRITON_CACHE_DIR" "$VLLM_CACHE_ROOT" "$UV_PYTHON_INSTALL_DIR"; do check_path "$path"; done
mkdir -p "$TMPDIR" "$UV_CACHE_DIR" "$HF_HOME" "$TORCH_HOME" "$TRITON_CACHE_DIR" "$VLLM_CACHE_ROOT"
cd "$root"
output="$SANDBOX_BUNDLE/installation-v1"
check_path "$output"
mkdir "$output"
trap 'status=$?; printf "%s\n" "$status" > "$output/exit-code"; exit "$status"' EXIT
cp "$source_dir/install-reviewed.sbatch" "$output/"
"$BASE_PYTHON" "$SANDBOX_BUNDLE/runtime.py" verify-source --bundle "$SANDBOX_BUNDLE"
[[ -z $(git -C "$SANDBOX_BUNDLE/source" ls-files --others --exclude-standard) ]]
"$task_uv_executable" --no-config venv --python "$BASE_PYTHON" "$SANDBOX_VENV"
"$task_uv_executable" --no-config pip install --python "$SANDBOX_VENV/bin/python" \
    --no-build --require-hashes --default-index https://pypi.org/simple -r "$SANDBOX_BUNDLE/build.lock"
"$task_uv_executable" --no-config pip install --python "$SANDBOX_VENV/bin/python" \
    --no-build --require-hashes --default-index https://pypi.org/simple \
    --find-links "$SANDBOX_BUNDLE/wheelhouse" -r "$SANDBOX_BUNDLE/dependencies.lock"
# A runtime dependency must not silently replace the reviewed build backend.
"$SANDBOX_VENV/bin/python" - "$SANDBOX_BUNDLE/build.lock" "$output/build-tools-verified.json" <<'PY'
import importlib.metadata
import json
import re
import sys
from pathlib import Path
expected = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", Path(sys.argv[1]).read_text(), re.M))
assert expected, "No build-tool pins found"
actual = {name: importlib.metadata.version(name) for name in expected}
Path(sys.argv[2]).write_text(json.dumps({"expected": expected, "actual": actual}, sort_keys=True) + "\n")
assert actual == expected, "Runtime installation changed the reviewed build tools"
PY
# Build only the authenticated EvalPlus checkout using the already locked tools.
"$task_uv_executable" --no-config --offline pip install --python "$SANDBOX_VENV/bin/python" \
    --no-deps --no-build-isolation "$SANDBOX_BUNDLE/source"
"$task_uv_executable" --no-config pip check --python "$SANDBOX_VENV/bin/python"
"$task_uv_executable" --no-config pip freeze --python "$SANDBOX_VENV/bin/python" > "$output/installed.private.txt"
"$BASE_PYTHON" "$SANDBOX_BUNDLE/runtime.py" verify-source --bundle "$SANDBOX_BUNDLE"
"$SANDBOX_VENV/bin/python" "$SANDBOX_BUNDLE/runtime.py" inventory --bundle "$SANDBOX_BUNDLE" \
    --output "$output/rootfs-before"
"$SANDBOX_VENV/bin/python" "$SANDBOX_BUNDLE/runtime.py" probe --bundle "$SANDBOX_BUNDLE" \
    --inventory "$output/rootfs-before" --output "$output/probe"
"$SANDBOX_VENV/bin/python" "$SANDBOX_BUNDLE/runtime.py" inventory --bundle "$SANDBOX_BUNDLE" \
    --output "$output/rootfs-after"
cmp "$output/rootfs-before/rootfs.json" "$output/rootfs-after/rootfs.json"
check_digest "$source_dir/install-reviewed.sbatch" "$INSTALL_SCRIPT_SHA256"
check_digest "$SANDBOX_BUNDLE/freeze.sha256" "$SANDBOX_FREEZE_SHA256"
(cd "$SANDBOX_BUNDLE" && sha256sum --check --strict freeze.sha256)
echo 'Trusted benign sandbox preparation completed; generated-code executor remains unqualified.'
