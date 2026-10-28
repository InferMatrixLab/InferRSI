#!/usr/bin/env bash
# Read only the selected system isolation tool's version/help/bytes in Slurm.
#SBATCH --job-name=qwen38-bwrap-capability
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:01:00
set -euo pipefail
umask 077
: "${TASK_ROOT:?}" "${SOURCE_DIR:?}" "${OUTPUT_DIR:?}" "${SCRIPT_SHA256:?}"
[[ -n ${SLURM_JOB_ID:-} && ${SLURM_GPUS_ON_NODE:-0} == 0 ]]
root=$(realpath -e "$TASK_ROOT")
inside_root() { case "$(realpath -m "$1")" in "$root"/*) ;; *) exit 2;; esac; }
for path in "$SOURCE_DIR" "$OUTPUT_DIR"; do inside_root "$path"; done
[[ $SCRIPT_SHA256 =~ ^[a-f0-9]{64}$ ]]
[[ $(sha256sum "$SOURCE_DIR/run.sbatch" | cut -d' ' -f1) == "$SCRIPT_SHA256" ]]
cmp "${BASH_SOURCE[0]}" "$SOURCE_DIR/run.sbatch"
[[ ! -e "$OUTPUT_DIR" && ! -L "$OUTPUT_DIR" ]]
export TMPDIR="$root/tmp/qwen38-bwrap-capability-${SLURM_JOB_ID}"
export XDG_CACHE_HOME="$root/cache/qwen38-bwrap-capability"
for path in "$TMPDIR" "$XDG_CACHE_HOME"; do inside_root "$path"; mkdir -p "$path"; done
mkdir "$OUTPUT_DIR"
cd "$root"
binary=$(command -v bwrap)
printf '%s\n' "$binary" > "$OUTPUT_DIR/binary-path.private.txt"
sha256sum "$binary" > "$OUTPUT_DIR/binary-sha256.private.txt"
"$binary" --version > "$OUTPUT_DIR/version.txt"
"$binary" --help > "$OUTPUT_DIR/help.txt" 2>&1
for flag in --unshare-user --unshare-net --unshare-pid --disable-userns \
    --assert-userns-disabled --clearenv --remount-ro --size; do
    present=false
    if grep -Fq -- "$flag" "$OUTPUT_DIR/help.txt"; then present=true; fi
    printf '%s\t%s\n' "$flag" "$present" >> "$OUTPUT_DIR/required-flags.tsv"
done
for tool in cc gcc meson ninja pkg-config; do
    command -v "$tool" >> "$OUTPUT_DIR/build-tool-paths.private.txt" || true
done
cp "$SOURCE_DIR/run.sbatch" "$OUTPUT_DIR/"
[[ $(sha256sum "$SOURCE_DIR/run.sbatch" | cut -d' ' -f1) == "$SCRIPT_SHA256" ]]
printf '0\n' > "$OUTPUT_DIR/exit-code"
