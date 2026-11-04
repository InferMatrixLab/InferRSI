#!/usr/bin/env bash
#SBATCH --job-name=qwen38-elf-dependency
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:03:00
set -euo pipefail
umask 077
: "${TASK_ROOT:?}" "${PYTHON_BIN:?}" "${SOURCE_DIR:?}" "${OUTPUT_DIR:?}"
: "${SCRIPT_SHA256:?}" "${DIAGNOSTIC_SHA256:?}" "${PYTHON_SHA256:?}"
[[ -n ${SLURM_JOB_ID:-} && ${SLURM_GPUS_ON_NODE:-0} == 0 ]]
root=$(realpath -e "$TASK_ROOT")
inside_root() { case "$(realpath -m "$1")" in "$root"/*) ;; *) exit 2;; esac; }
for path in "$PYTHON_BIN" "$SOURCE_DIR" "$OUTPUT_DIR"; do inside_root "$path"; done
check_digest() { [[ $2 =~ ^[a-f0-9]{64}$ ]] && [[ $(sha256sum "$1" | cut -d' ' -f1) == "$2" ]]; }
check_digest "$SOURCE_DIR/run.sbatch" "$SCRIPT_SHA256"
check_digest "$SOURCE_DIR/diagnose.py" "$DIAGNOSTIC_SHA256"
check_digest "$PYTHON_BIN" "$PYTHON_SHA256"
cmp "${BASH_SOURCE[0]}" "$SOURCE_DIR/run.sbatch"
[[ ! -e $OUTPUT_DIR && ! -L $OUTPUT_DIR ]]
export PATH=/usr/bin:/bin
export TMPDIR="$root/tmp/qwen38-elf-${SLURM_JOB_ID}"
export XDG_CACHE_HOME="$root/cache/qwen38-elf-${SLURM_JOB_ID}"
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
unset PYTHONPATH PYTHONHOME PYTHONOPTIMIZE PYTHONINSPECT PYTHONSTARTUP VIRTUAL_ENV
for path in "$TMPDIR" "$XDG_CACHE_HOME"; do inside_root "$path"; mkdir -p "$path"; done
mkdir "$OUTPUT_DIR"
completed=false
phase=diagnostic
signal_name=none
finish() {
    local status=$?
    trap - EXIT
    [[ $status != 0 || $completed == true ]] || status=1
    [[ $status == 0 ]] || completed=false
    printf '%s\n' "$status" > "$OUTPUT_DIR/exit-code"
    printf '{"completed":%s,"exit_code":%s,"phase":"%s","signal":"%s","job_id":"%s"}\n' \
        "$completed" "$status" "$phase" "$signal_name" "$SLURM_JOB_ID" > "$OUTPUT_DIR/terminal-status.json"
    exit "$status"
}
trap finish EXIT
trap 'signal_name=TERM; exit 143' TERM
trap 'signal_name=INT; exit 130' INT
trap 'signal_name=HUP; exit 129' HUP
cp "$SOURCE_DIR/run.sbatch" "$SOURCE_DIR/diagnose.py" "$OUTPUT_DIR/"
cd "$root"
"$PYTHON_BIN" -IB "$SOURCE_DIR/diagnose.py" "$OUTPUT_DIR"
check_digest "$SOURCE_DIR/run.sbatch" "$SCRIPT_SHA256"
check_digest "$SOURCE_DIR/diagnose.py" "$DIAGNOSTIC_SHA256"
check_digest "$PYTHON_BIN" "$PYTHON_SHA256"
phase=complete
completed=true
