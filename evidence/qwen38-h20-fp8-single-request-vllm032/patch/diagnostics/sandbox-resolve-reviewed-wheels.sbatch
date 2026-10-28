#!/usr/bin/env bash
# Resolve-only successor using independently reviewed local dependency wheels.
#SBATCH --job-name=qwen38-eval-sandbox-prepare
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:30:00
set -euo pipefail
umask 077
: "${TASK_ROOT:?set the authorized task root}"
: "${BASE_PYTHON:?set a registered Python3.12 under TASK_ROOT}"
: "${UV_BIN:?set the existing uv executable under TASK_ROOT}"
: "${SANDBOX_SOURCE_DIR:?set the explicit staged sandbox helper directory}"
: "${SANDBOX_HELPER_SHA256:?set the reviewed runtime.py digest}"
: "${SANDBOX_PROBE_SHA256:?set the reviewed benign_probe.py digest}"
: "${SANDBOX_SCRIPT_SHA256:?set the reviewed submission-script digest}"
: "${SANDBOX_BUNDLE:?set a new resolution bundle under TASK_ROOT}"
: "${SANDBOX_VENV:?name the future dedicated environment; never created here}"
: "${WHEEL_BUILD_BUNDLE:?set the reviewed build output directory}"
: "${WHEEL_BUILD_MANIFEST_SHA256:?set its independently reviewed output manifest hash}"
task_uv_executable=$UV_BIN
phase=${1:-}
case "$phase" in resolve) ;; *) echo 'Use resolve.' >&2; exit 2;; esac
[[ -n ${SLURM_JOB_ID:-} && ${SLURM_GPUS_ON_NODE:-0} == 0 ]]
root=$(realpath -e "$TASK_ROOT")
check_path() {
    local value
    value=$(realpath -m "$1")
    case "$value" in "$root"/*) ;; *) echo 'Path escapes TASK_ROOT.' >&2; exit 2;; esac
}
for path in "$BASE_PYTHON" "$task_uv_executable" "$SANDBOX_SOURCE_DIR" "$SANDBOX_BUNDLE" "$SANDBOX_VENV" "$WHEEL_BUILD_BUNDLE"; do
    check_path "$path"
done
source_dir=$(cd -- "$SANDBOX_SOURCE_DIR" && pwd -P)
check_digest() {
    [[ "$2" =~ ^[a-f0-9]{64}$ ]]
    [[ $(sha256sum "$1" | cut -d' ' -f1) == "$2" ]]
}
check_sources() {
    check_digest "$source_dir/runtime.py" "$SANDBOX_HELPER_SHA256"
    check_digest "$source_dir/benign_probe.py" "$SANDBOX_PROBE_SHA256"
    check_digest "$source_dir/prepare-sandbox.sbatch" "$SANDBOX_SCRIPT_SHA256"
}
cmp "${BASH_SOURCE[0]}" "$source_dir/prepare-sandbox.sbatch"
check_sources
check_digest "$WHEEL_BUILD_BUNDLE/output.sha256" "$WHEEL_BUILD_MANIFEST_SHA256"
(cd "$WHEEL_BUILD_BUNDLE" && sha256sum --check --strict output.sha256)
for path in "$WHEEL_BUILD_BUNDLE/wheelhouse/wget-3.2-py3-none-any.whl" \
    "$WHEEL_BUILD_BUNDLE/wheelhouse/tempdir-0.7.1-py3-none-any.whl" \
    "$WHEEL_BUILD_BUNDLE/build.lock"; do check_path "$path"; done
# Ignore inherited resolver source/constraint/build policy; never print its values.
for task_resolver_variable in "${!UV_@}" "${!PIP_@}"; do
    if [[ -n "$task_resolver_variable" ]]; then unset "$task_resolver_variable"; fi
done
export TMPDIR="$root/tmp/qwen38-eval-sandbox-${SLURM_JOB_ID}"
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
    "$TRITON_CACHE_DIR" "$VLLM_CACHE_ROOT" "$UV_PYTHON_INSTALL_DIR"; do
    check_path "$path"
done
mkdir -p "$TMPDIR" "$XDG_CACHE_HOME" "$UV_CACHE_DIR" "$HF_HOME" "$TORCH_HOME" \
    "$TRITON_CACHE_DIR" "$VLLM_CACHE_ROOT"
cd "$root"
"$BASE_PYTHON" -c 'import sys; assert sys.version_info[:2] == (3, 12)'
source_revision=26d6d00bb1fd0fa37f39c99d5290da67891d1c5e
if [[ "$phase" == resolve ]]; then
    [[ ! -e "$SANDBOX_BUNDLE" && ! -L "$SANDBOX_BUNDLE" ]]
    mkdir "$SANDBOX_BUNDLE"
    trap 'status=$?; printf "%s\n" "$status" > "$SANDBOX_BUNDLE/resolve.exit-code"; exit "$status"' EXIT
    cp "$source_dir/runtime.py" "$source_dir/benign_probe.py" "$source_dir/prepare-sandbox.sbatch" "$SANDBOX_BUNDLE/"
    mkdir "$SANDBOX_BUNDLE/wheelhouse"
    cp "$WHEEL_BUILD_BUNDLE/wheelhouse/wget-3.2-py3-none-any.whl" \
        "$WHEEL_BUILD_BUNDLE/wheelhouse/tempdir-0.7.1-py3-none-any.whl" "$SANDBOX_BUNDLE/wheelhouse/"
    cp "$WHEEL_BUILD_BUNDLE/build.lock" "$SANDBOX_BUNDLE/"
    cp "$WHEEL_BUILD_BUNDLE/output.sha256" "$SANDBOX_BUNDLE/wheel-build-output.sha256"
    git -c http.lowSpeedLimit=1 -c http.lowSpeedTime=60 clone --filter=blob:none --no-checkout \
        https://github.com/evalplus/evalplus.git "$SANDBOX_BUNDLE/source"
    git -C "$SANDBOX_BUNDLE/source" fetch --depth=1 origin "$source_revision"
    git -C "$SANDBOX_BUNDLE/source" checkout --detach "$source_revision"
    "$BASE_PYTHON" "$source_dir/runtime.py" requirements --bundle "$SANDBOX_BUNDLE"
    cat > "$SANDBOX_BUNDLE/resolver-policy.json" <<'POLICY'
{"phase":"resolve","config_files":false,"inherited_UV_and_PIP_variables":"cleared","default_index":"https://pypi.org/simple","additional_indexes":[],"find_links":["reviewed_local_wheelhouse"],"build_allowed":false,"python_downloads":"never","http_timeout_seconds":60,"generated_code_executed":false}
POLICY
    "$task_uv_executable" --no-config pip compile "$SANDBOX_BUNDLE/dependencies.in" --python "$BASE_PYTHON" \
        --no-build --generate-hashes --default-index https://pypi.org/simple --no-header --no-annotate \
        --find-links "$SANDBOX_BUNDLE/wheelhouse" \
        --output-file "$SANDBOX_BUNDLE/dependencies.lock"
    "$task_uv_executable" --version > "$SANDBOX_BUNDLE/uv-version.txt"
    sha256sum "$task_uv_executable" | cut -d' ' -f1 > "$SANDBOX_BUNDLE/uv-sha256.txt"
    sha256sum "$BASE_PYTHON" | cut -d' ' -f1 > "$SANDBOX_BUNDLE/python-sha256.txt"
    check_sources
    check_digest "$WHEEL_BUILD_BUNDLE/output.sha256" "$WHEEL_BUILD_MANIFEST_SHA256"
    (cd "$WHEEL_BUILD_BUNDLE" && sha256sum --check --strict output.sha256)
    for name in wget-3.2-py3-none-any.whl tempdir-0.7.1-py3-none-any.whl; do
        cmp "$WHEEL_BUILD_BUNDLE/wheelhouse/$name" "$SANDBOX_BUNDLE/wheelhouse/$name"
    done
    cmp "$WHEEL_BUILD_BUNDLE/build.lock" "$SANDBOX_BUNDLE/build.lock"
    (
        cd "$SANDBOX_BUNDLE"
        sha256sum runtime.py benign_probe.py prepare-sandbox.sbatch resolver-policy.json source.json build.in dependencies.in \
            build.lock dependencies.lock wheel-build-output.sha256 wheelhouse/*.whl \
            uv-version.txt uv-sha256.txt python-sha256.txt > freeze.sha256
    )
    echo 'Resolution ready for independent source/dependency freeze review; no environment installed.'
fi
