#!/usr/bin/env bash
# Build a task-local tool; only its pure utility test and version/help are run.
#SBATCH --job-name=qwen38-bwrap-build
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:10:00
set -euo pipefail
umask 077
: "${TASK_ROOT:?}" "${BASE_PYTHON:?}" "${UV_BIN:?}" "${SOURCE_DIR:?}"
: "${OUTPUT_DIR:?}" "${BUILD_VENV:?}" "${INSTALL_PREFIX:?}"
: "${SCRIPT_SHA256:?}" "${EXTRACTOR_SHA256:?}" "${INPUTS_SHA256:?}"
: "${PYTHON_SHA256:?}" "${UV_SHA256:?}"
[[ -n ${SLURM_JOB_ID:-} && ${SLURM_GPUS_ON_NODE:-0} == 0 ]]
root=$(realpath -e "$TASK_ROOT")
inside_root() { case "$(realpath -m "$1")" in "$root"/*) ;; *) exit 2;; esac; }
for path in "$BASE_PYTHON" "$UV_BIN" "$SOURCE_DIR" "$OUTPUT_DIR" "$BUILD_VENV" "$INSTALL_PREFIX"; do inside_root "$path"; done
check_digest() {
    [[ $2 =~ ^[a-f0-9]{64}$ ]]
    [[ $(sha256sum "$1" | cut -d' ' -f1) == "$2" ]]
}
check_digest "$SOURCE_DIR/run.sbatch" "$SCRIPT_SHA256"
check_digest "$SOURCE_DIR/extract_source.py" "$EXTRACTOR_SHA256"
check_digest "$SOURCE_DIR/inputs.sha256" "$INPUTS_SHA256"
check_digest "$BASE_PYTHON" "$PYTHON_SHA256"
check_digest "$UV_BIN" "$UV_SHA256"
cmp "${BASH_SOURCE[0]}" "$SOURCE_DIR/run.sbatch"
(cd "$SOURCE_DIR" && sha256sum --check --strict inputs.sha256)
for path in "$OUTPUT_DIR" "$BUILD_VENV" "$INSTALL_PREFIX"; do [[ ! -e $path && ! -L $path ]]; done
task_uv=$UV_BIN
for variable in "${!UV_@}" "${!PIP_@}"; do [[ -z $variable ]] || unset "$variable"; done
export UV_OFFLINE=true UV_PYTHON_DOWNLOADS=never
export TMPDIR="$root/tmp/qwen38-bwrap-build-${SLURM_JOB_ID}"
export XDG_CACHE_HOME="$root/cache/qwen38-bwrap-build"
export UV_CACHE_DIR="$XDG_CACHE_HOME/uv" HF_HOME="$XDG_CACHE_HOME/huggingface"
export TORCH_HOME="$XDG_CACHE_HOME/torch" TRITON_CACHE_DIR="$XDG_CACHE_HOME/triton"
export VLLM_CACHE_ROOT="$XDG_CACHE_HOME/vllm" UV_PYTHON_INSTALL_DIR="$root/software/python"
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
unset PYTHONPATH PYTHONHOME PYTHONOPTIMIZE PYTHONINSPECT PYTHONSTARTUP VIRTUAL_ENV
unset DESTDIR
unset CC CXX CFLAGS CXXFLAGS CPPFLAGS LDFLAGS PKG_CONFIG_PATH PKG_CONFIG_LIBDIR PKG_CONFIG_SYSROOT_DIR
for path in "$TMPDIR" "$XDG_CACHE_HOME" "$UV_CACHE_DIR" "$HF_HOME" "$TORCH_HOME" "$TRITON_CACHE_DIR" "$VLLM_CACHE_ROOT" "$UV_PYTHON_INSTALL_DIR"; do inside_root "$path"; mkdir -p "$path"; done
mkdir "$OUTPUT_DIR"
completed=false
phase=dependency_preflight
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
cp "$SOURCE_DIR/run.sbatch" "$SOURCE_DIR/extract_source.py" "$SOURCE_DIR/inputs.sha256" "$OUTPUT_DIR/"
cd "$root"
export CC
CC=$(command -v cc)
printf '%s\n' "$CC" > "$OUTPUT_DIR/compiler-path.private.txt"
sha256sum "$(realpath -e "$CC")" > "$OUTPUT_DIR/compiler-sha256.private.txt"
"$CC" --version > "$OUTPUT_DIR/compiler-version.private.txt"
pkg-config --modversion libcap > "$OUTPUT_DIR/libcap-version.txt"
pkg-config --cflags --libs libcap > "$OUTPUT_DIR/libcap-flags.private.txt"
phase=build_environment
"$task_uv" --no-config --offline venv --python "$BASE_PYTHON" "$BUILD_VENV"
"$task_uv" --no-config --offline pip install --python "$BUILD_VENV/bin/python" \
    --no-index --find-links "$SOURCE_DIR/wheelhouse" --no-deps --no-build \
    --require-hashes -r "$SOURCE_DIR/build.lock"
"$BUILD_VENV/bin/python" -IB - "$OUTPUT_DIR/build-packages.json" <<'PY'
import importlib.metadata
import json
import sys
packages = {p.metadata['Name'].lower(): p.version for p in importlib.metadata.distributions()}
if packages != {'meson': '1.12.1', 'ninja': '1.13.2'}:
    raise ValueError('Unexpected build package set')
with open(sys.argv[1], 'x') as stream:
    json.dump(packages, stream, sort_keys=True)
    stream.write('\n')
PY
export PATH="$BUILD_VENV/bin:$PATH"
phase=source_extraction
"$BASE_PYTHON" -IB "$SOURCE_DIR/extract_source.py" \
    "$SOURCE_DIR/bubblewrap-0.13.1.tar.xz" "$OUTPUT_DIR/source"
phase=configure_compile
"$BUILD_VENV/bin/meson" setup "$OUTPUT_DIR/build" "$OUTPUT_DIR/source/bubblewrap-0.13.1" \
    --prefix="$INSTALL_PREFIX" --wrap-mode=nodownload \
    -Dpython="$BUILD_VENV/bin/python" -Dman=disabled \
    -Dbash_completion=disabled -Dzsh_completion=disabled -Dtests=true
"$BUILD_VENV/bin/meson" compile -C "$OUTPUT_DIR/build" -j 4 bwrap test-utils
phase=utility_test
"$BUILD_VENV/bin/meson" test -C "$OUTPUT_DIR/build" --no-rebuild --print-errorlogs test-utils
phase=task_local_install
"$BUILD_VENV/bin/meson" install -C "$OUTPUT_DIR/build" --no-rebuild --destdir=''
inside_root "$INSTALL_PREFIX/bin/bwrap"
[[ ! -u "$INSTALL_PREFIX/bin/bwrap" && ! -g "$INSTALL_PREFIX/bin/bwrap" ]]
phase=version_help_checks
"$INSTALL_PREFIX/bin/bwrap" --version > "$OUTPUT_DIR/version.txt"
[[ $(cat "$OUTPUT_DIR/version.txt") == 'bubblewrap 0.13.1' ]]
"$INSTALL_PREFIX/bin/bwrap" --help > "$OUTPUT_DIR/help.txt" 2>&1
for flag in --unshare-user --unshare-net --unshare-pid --disable-userns \
    --assert-userns-disabled --clearenv --remount-ro --size; do
    grep -Fq -- "$flag" "$OUTPUT_DIR/help.txt"
done
sha256sum "$INSTALL_PREFIX/bin/bwrap" > "$OUTPUT_DIR/binary-sha256.private.txt"
ldd "$INSTALL_PREFIX/bin/bwrap" > "$OUTPUT_DIR/linked-libraries.private.txt"
phase=postflight
check_digest "$SOURCE_DIR/run.sbatch" "$SCRIPT_SHA256"
check_digest "$SOURCE_DIR/extract_source.py" "$EXTRACTOR_SHA256"
check_digest "$SOURCE_DIR/inputs.sha256" "$INPUTS_SHA256"
(cd "$SOURCE_DIR" && sha256sum --check --strict inputs.sha256)
phase=complete
completed=true
