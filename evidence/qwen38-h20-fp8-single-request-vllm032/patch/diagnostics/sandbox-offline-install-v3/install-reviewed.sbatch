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
: "${PACKAGE_AUDIT_SHA256:?}"
: "${WHEEL_BUNDLE:?}" "${WHEEL_MANIFEST_SHA256:?}"
: "${WHEEL_VERIFIER_SHA256:?}" "${PREFETCH_HELPER_SHA256:?}"
task_uv_executable=$UV_BIN
[[ -n ${SLURM_JOB_ID:-} && ${SLURM_GPUS_ON_NODE:-0} == 0 ]]
root=$(realpath -e "$TASK_ROOT")
check_path() {
    local value
    value=$(realpath -m "$1")
    case "$value" in "$root"/*) ;; *) echo 'Path escapes task root.' >&2; exit 2;; esac
}
for path in "$BASE_PYTHON" "$task_uv_executable" "$SANDBOX_BUNDLE" "$SANDBOX_VENV" "$INSTALL_SOURCE_DIR" "$WHEEL_BUNDLE"; do
    check_path "$path"
done
source_dir=$(cd -- "$INSTALL_SOURCE_DIR" && pwd -P)
check_digest() {
    if [[ ! "$2" =~ ^[a-f0-9]{64}$ ]]; then return 2; fi
    [[ $(sha256sum "$1" | cut -d' ' -f1) == "$2" ]]
}
check_digest "$source_dir/install-reviewed.sbatch" "$INSTALL_SCRIPT_SHA256"
check_digest "$source_dir/audit_packages.py" "$PACKAGE_AUDIT_SHA256"
check_digest "$source_dir/verify_wheels.py" "$WHEEL_VERIFIER_SHA256"
check_digest "$source_dir/prefetch.py" "$PREFETCH_HELPER_SHA256"
check_path "$WHEEL_BUNDLE/wheelhouse"
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
export UV_OFFLINE=true
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
unset PYTHONPATH PYTHONHOME PYTHONOPTIMIZE PYTHONINSPECT PYTHONSTARTUP VIRTUAL_ENV
for path in "$TMPDIR" "$XDG_CACHE_HOME" "$UV_CACHE_DIR" "$HF_HOME" "$TORCH_HOME" \
    "$TRITON_CACHE_DIR" "$VLLM_CACHE_ROOT" "$UV_PYTHON_INSTALL_DIR"; do check_path "$path"; done
mkdir -p "$TMPDIR" "$UV_CACHE_DIR" "$HF_HOME" "$TORCH_HOME" "$TRITON_CACHE_DIR" "$VLLM_CACHE_ROOT"
cd "$root"
output="$SANDBOX_BUNDLE/installation-v3"
check_path "$output"
mkdir "$output"
# BEGIN TERMINAL RECORD: an EXIT code alone never authenticates completion.
task_completed=false
task_signal=none
finish_installation() {
    local status=$?
    trap - EXIT
    if [[ "$status" == 0 && "$task_completed" != true ]]; then status=1; fi
    if [[ "$status" != 0 ]]; then task_completed=false; fi
    printf '%s\n' "$status" > "$output/exit-code"
    printf '{"completed":%s,"signal":"%s","exit_code":%s,"job_id":"%s"}\n' \
        "$task_completed" "$task_signal" "$status" "$SLURM_JOB_ID" > "$output/terminal-status.json"
    exit "$status"
}
trap finish_installation EXIT
trap 'task_completed=false; task_signal=TERM; exit 143' TERM
trap 'task_completed=false; task_signal=INT; exit 130' INT
trap 'task_completed=false; task_signal=HUP; exit 129' HUP
# END TERMINAL RECORD
cp "$source_dir/install-reviewed.sbatch" "$source_dir/audit_packages.py" \
    "$source_dir/verify_wheels.py" "$source_dir/prefetch.py" "$output/"
verify_offline_wheels() {
    "$BASE_PYTHON" -IB "$source_dir/verify_wheels.py" --bundle "$WHEEL_BUNDLE" \
        --build "$SANDBOX_BUNDLE/build.lock" --runtime "$SANDBOX_BUNDLE/dependencies.lock" \
        --sha256 "$WHEEL_MANIFEST_SHA256" --output "$1"
}
verify_offline_wheels "$output/wheels-before.json"
"$BASE_PYTHON" "$SANDBOX_BUNDLE/runtime.py" verify-source --bundle "$SANDBOX_BUNDLE"
[[ -z $(git -C "$SANDBOX_BUNDLE/source" ls-files --others --exclude-standard) ]]
"$task_uv_executable" --no-config venv --python "$BASE_PYTHON" "$SANDBOX_VENV"
"$task_uv_executable" --no-config --offline pip install --python "$SANDBOX_VENV/bin/python" \
    --no-deps --no-build --require-hashes --no-index \
    --find-links "$WHEEL_BUNDLE/wheelhouse" -r "$SANDBOX_BUNDLE/build.lock"
"$task_uv_executable" --no-config --offline pip install --python "$SANDBOX_VENV/bin/python" \
    --no-deps --no-build --require-hashes --no-index \
    --find-links "$WHEEL_BUNDLE/wheelhouse" -r "$SANDBOX_BUNDLE/dependencies.lock"
# Both reviewed lockfiles contain the full closure; no implicit dependencies.
"$SANDBOX_VENV/bin/python" -IB "$source_dir/audit_packages.py" \
    "$SANDBOX_BUNDLE/build.lock" "$SANDBOX_BUNDLE/dependencies.lock" dependencies \
    "$output/dependencies-verified.json"
# Build only the authenticated EvalPlus checkout using the already locked tools.
"$task_uv_executable" --no-config --offline pip install --python "$SANDBOX_VENV/bin/python" \
    --no-deps --no-build-isolation "$SANDBOX_BUNDLE/source"
"$SANDBOX_VENV/bin/python" -IB "$source_dir/audit_packages.py" \
    "$SANDBOX_BUNDLE/build.lock" "$SANDBOX_BUNDLE/dependencies.lock" evaluator \
    "$output/evaluator-packages-verified.json"
"$task_uv_executable" --no-config pip check --python "$SANDBOX_VENV/bin/python"
"$task_uv_executable" --no-config pip freeze --python "$SANDBOX_VENV/bin/python" > "$output/installed.private.txt"
"$BASE_PYTHON" "$SANDBOX_BUNDLE/runtime.py" verify-source --bundle "$SANDBOX_BUNDLE"
"$SANDBOX_VENV/bin/python" "$SANDBOX_BUNDLE/runtime.py" inventory --bundle "$SANDBOX_BUNDLE" \
    --output "$output/rootfs-before"
probe_status=0
"$SANDBOX_VENV/bin/python" "$SANDBOX_BUNDLE/runtime.py" probe --bundle "$SANDBOX_BUNDLE" \
    --inventory "$output/rootfs-before" --output "$output/probe" || probe_status=$?
printf '%s\n' "$probe_status" > "$output/probe-status"
post_status=0
run_postcheck() {
    local name=$1 status=0
    shift
    "$@" || status=$?
    printf '%s\t%s\n' "$name" "$status" >> "$output/postflight-status.tsv"
    if [[ "$status" != 0 ]]; then post_status=$status; fi
}
check_frozen_files() { (cd "$SANDBOX_BUNDLE" && sha256sum --check --strict freeze.sha256); }
run_postcheck inventory "$SANDBOX_VENV/bin/python" "$SANDBOX_BUNDLE/runtime.py" inventory \
    --bundle "$SANDBOX_BUNDLE" --output "$output/rootfs-after"
run_postcheck runtime-byte-comparison cmp "$output/rootfs-before/rootfs.json" "$output/rootfs-after/rootfs.json"
run_postcheck source "$BASE_PYTHON" "$SANDBOX_BUNDLE/runtime.py" verify-source --bundle "$SANDBOX_BUNDLE"
run_postcheck package-set "$SANDBOX_VENV/bin/python" -IB "$source_dir/audit_packages.py" \
    "$SANDBOX_BUNDLE/build.lock" "$SANDBOX_BUNDLE/dependencies.lock" evaluator \
    "$output/evaluator-packages-after.json"
run_postcheck batch-script check_digest "$source_dir/install-reviewed.sbatch" "$INSTALL_SCRIPT_SHA256"
run_postcheck audit-script check_digest "$source_dir/audit_packages.py" "$PACKAGE_AUDIT_SHA256"
run_postcheck wheel-verifier check_digest "$source_dir/verify_wheels.py" "$WHEEL_VERIFIER_SHA256"
run_postcheck prefetch-helper check_digest "$source_dir/prefetch.py" "$PREFETCH_HELPER_SHA256"
run_postcheck wheel-bytes verify_offline_wheels "$output/wheels-after.json"
run_postcheck freeze-manifest check_digest "$SANDBOX_BUNDLE/freeze.sha256" "$SANDBOX_FREEZE_SHA256"
run_postcheck freeze-files check_frozen_files
if [[ "$probe_status" != 0 ]]; then exit "$probe_status"; fi
if [[ "$post_status" != 0 ]]; then exit "$post_status"; fi
echo 'Trusted benign sandbox preparation completed; generated-code executor remains unqualified.'
task_completed=true
