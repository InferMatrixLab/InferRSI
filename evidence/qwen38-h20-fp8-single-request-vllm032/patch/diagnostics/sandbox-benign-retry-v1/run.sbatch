#!/usr/bin/env bash
# Reuse the installed evaluator; only inventory and the frozen trusted probe run.
#SBATCH --job-name=qwen38-eval-benign-retry
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:15:00
set -euo pipefail
umask 077
: "${TASK_ROOT:?}" "${SANDBOX_BUNDLE:?}" "${SANDBOX_FREEZE_SHA256:?}"
: "${SANDBOX_VENV:?}" "${SOURCE_DIR:?}" "${OUTPUT_DIR:?}"
: "${SCRIPT_SHA256:?}" "${PACKAGE_AUDIT_SHA256:?}" "${BWRAP_BIN:?}" "${BWRAP_SHA256:?}"
: "${PYTHON_SHA256:?}"
[[ -n ${SLURM_JOB_ID:-} && ${SLURM_GPUS_ON_NODE:-0} == 0 ]]
root=$(realpath -e "$TASK_ROOT")
check_path() { case "$(realpath -m "$1")" in "$root"/*) ;; *) exit 2;; esac; }
check_digest() {
    [[ $2 =~ ^[a-f0-9]{64}$ ]]
    [[ $(sha256sum "$1" | cut -d' ' -f1) == "$2" ]]
}
for path in "$SANDBOX_BUNDLE" "$SANDBOX_VENV" "$SOURCE_DIR" "$OUTPUT_DIR" "$BWRAP_BIN"; do check_path "$path"; done
check_digest "$SOURCE_DIR/run.sbatch" "$SCRIPT_SHA256"
check_digest "$SOURCE_DIR/audit_packages.py" "$PACKAGE_AUDIT_SHA256"
check_digest "$SANDBOX_BUNDLE/freeze.sha256" "$SANDBOX_FREEZE_SHA256"
check_digest "$SANDBOX_VENV/bin/python" "$PYTHON_SHA256"
check_digest "$BWRAP_BIN" "$BWRAP_SHA256"
cmp "${BASH_SOURCE[0]}" "$SOURCE_DIR/run.sbatch"
(cd "$SANDBOX_BUNDLE" && sha256sum --check --strict freeze.sha256)
[[ ! -e $OUTPUT_DIR && ! -L $OUTPUT_DIR ]]
export PATH="$(dirname "$BWRAP_BIN"):/usr/bin:/bin"
[[ $(command -v bwrap) == "$BWRAP_BIN" ]]
export TMPDIR="$root/tmp/qwen38-benign-retry-${SLURM_JOB_ID}"
export XDG_CACHE_HOME="$root/cache/qwen38-benign-retry-${SLURM_JOB_ID}"
export HF_HOME="$XDG_CACHE_HOME/huggingface" TORCH_HOME="$XDG_CACHE_HOME/torch"
export TRITON_CACHE_DIR="$XDG_CACHE_HOME/triton" VLLM_CACHE_ROOT="$XDG_CACHE_HOME/vllm"
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
unset PYTHONPATH PYTHONHOME PYTHONOPTIMIZE PYTHONINSPECT PYTHONSTARTUP VIRTUAL_ENV
for path in "$TMPDIR" "$XDG_CACHE_HOME" "$HF_HOME" "$TORCH_HOME" "$TRITON_CACHE_DIR" "$VLLM_CACHE_ROOT"; do check_path "$path"; mkdir -p "$path"; done
mkdir "$OUTPUT_DIR"
completed=false
signal_name=none
finish() {
    local status=$?
    trap - EXIT
    [[ $status != 0 || $completed == true ]] || status=1
    [[ $status == 0 ]] || completed=false
    printf '%s\n' "$status" > "$OUTPUT_DIR/exit-code"
    printf '{"completed":%s,"signal":"%s","exit_code":%s,"job_id":"%s"}\n' \
        "$completed" "$signal_name" "$status" "$SLURM_JOB_ID" > "$OUTPUT_DIR/terminal-status.json"
    exit "$status"
}
trap finish EXIT
trap 'signal_name=TERM; exit 143' TERM
trap 'signal_name=INT; exit 130' INT
trap 'signal_name=HUP; exit 129' HUP
cp "$SOURCE_DIR/run.sbatch" "$SOURCE_DIR/audit_packages.py" "$OUTPUT_DIR/"
cd "$root"
python="$SANDBOX_VENV/bin/python"
"$python" -IB "$SOURCE_DIR/audit_packages.py" "$SANDBOX_BUNDLE/build.lock" \
    "$SANDBOX_BUNDLE/dependencies.lock" evaluator "$OUTPUT_DIR/evaluator-packages-before.json"
"$python" -IB "$SANDBOX_BUNDLE/runtime.py" verify-source --bundle "$SANDBOX_BUNDLE"
[[ -z $(git -C "$SANDBOX_BUNDLE/source" ls-files --others --exclude-standard) ]]
"$python" -IB "$SANDBOX_BUNDLE/runtime.py" inventory --bundle "$SANDBOX_BUNDLE" \
    --output "$OUTPUT_DIR/rootfs-before"
probe_status=0
"$python" -IB "$SANDBOX_BUNDLE/runtime.py" probe --bundle "$SANDBOX_BUNDLE" \
    --inventory "$OUTPUT_DIR/rootfs-before" --output "$OUTPUT_DIR/probe" || probe_status=$?
printf '%s\n' "$probe_status" > "$OUTPUT_DIR/probe-status"
post_status=0
run_postcheck() {
    local name=$1 status=0
    shift
    "$@" || status=$?
    printf '%s\t%s\n' "$name" "$status" >> "$OUTPUT_DIR/postflight-status.tsv"
    if [[ $status != 0 ]]; then post_status=$status; fi
}
check_frozen_files() { (cd "$SANDBOX_BUNDLE" && sha256sum --check --strict freeze.sha256); }
run_postcheck inventory "$python" -IB "$SANDBOX_BUNDLE/runtime.py" inventory \
    --bundle "$SANDBOX_BUNDLE" --output "$OUTPUT_DIR/rootfs-after"
run_postcheck runtime-byte-comparison cmp "$OUTPUT_DIR/rootfs-before/rootfs.json" "$OUTPUT_DIR/rootfs-after/rootfs.json"
run_postcheck source "$python" -IB "$SANDBOX_BUNDLE/runtime.py" verify-source --bundle "$SANDBOX_BUNDLE"
run_postcheck package-set "$python" -IB "$SOURCE_DIR/audit_packages.py" "$SANDBOX_BUNDLE/build.lock" \
    "$SANDBOX_BUNDLE/dependencies.lock" evaluator "$OUTPUT_DIR/evaluator-packages-after.json"
run_postcheck batch-script check_digest "$SOURCE_DIR/run.sbatch" "$SCRIPT_SHA256"
run_postcheck audit-script check_digest "$SOURCE_DIR/audit_packages.py" "$PACKAGE_AUDIT_SHA256"
run_postcheck bwrap-binary check_digest "$BWRAP_BIN" "$BWRAP_SHA256"
run_postcheck python-binary check_digest "$python" "$PYTHON_SHA256"
run_postcheck freeze-manifest check_digest "$SANDBOX_BUNDLE/freeze.sha256" "$SANDBOX_FREEZE_SHA256"
run_postcheck freeze-files check_frozen_files
if [[ $probe_status != 0 ]]; then exit "$probe_status"; fi
if [[ $post_status != 0 ]]; then exit "$post_status"; fi
completed=true
