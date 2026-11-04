#!/usr/bin/env bash
# Build only two reviewed source archives; no evaluator or generated-code execution.
#SBATCH --job-name=qwen38-eval-reviewed-wheels
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:20:00
set -euo pipefail
umask 077
: "${TASK_ROOT:?}"
: "${BASE_PYTHON:?}"
: "${UV_BIN:?}"
: "${BUILD_SOURCE_DIR:?}"
: "${BUILD_BUNDLE:?}"
: "${BUILD_VENV:?}"
: "${BUILD_INPUTS_SHA256:?}"
: "${BUILD_SCRIPT_SHA256:?}"
task_uv_executable=$UV_BIN
[[ -n ${SLURM_JOB_ID:-} && ${SLURM_GPUS_ON_NODE:-0} == 0 ]]
root=$(realpath -e "$TASK_ROOT")
check_path() {
    local value
    value=$(realpath -m "$1")
    case "$value" in "$root"/*) ;; *) echo 'Path escapes task root.' >&2; exit 2;; esac
}
for path in "$BASE_PYTHON" "$task_uv_executable" "$BUILD_SOURCE_DIR" "$BUILD_BUNDLE" "$BUILD_VENV"; do
    check_path "$path"
done
source_dir=$(cd -- "$BUILD_SOURCE_DIR" && pwd -P)
check_digest() {
    [[ "$2" =~ ^[a-f0-9]{64}$ ]]
    [[ $(sha256sum "$1" | cut -d' ' -f1) == "$2" ]]
}
check_digest "$source_dir/build-reviewed.sbatch" "$BUILD_SCRIPT_SHA256"
cmp "${BASH_SOURCE[0]}" "$source_dir/build-reviewed.sbatch"
check_digest "$source_dir/inputs.sha256" "$BUILD_INPUTS_SHA256"
(cd "$source_dir" && sha256sum --check --strict inputs.sha256)
[[ ! -e "$BUILD_BUNDLE" && ! -L "$BUILD_BUNDLE" && ! -e "$BUILD_VENV" && ! -L "$BUILD_VENV" ]]
for task_resolver_variable in "${!UV_@}" "${!PIP_@}"; do
    if [[ -n "$task_resolver_variable" ]]; then unset "$task_resolver_variable"; fi
done
export TMPDIR="$root/tmp/qwen38-reviewed-wheels-${SLURM_JOB_ID}"
export XDG_CACHE_HOME="$root/cache/qwen38-reviewed-wheels"
export UV_CACHE_DIR="$XDG_CACHE_HOME/uv"
export UV_PYTHON_INSTALL_DIR="$root/software/python"
export UV_PYTHON_DOWNLOADS=never
export UV_HTTP_TIMEOUT=60
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
unset PYTHONPATH VIRTUAL_ENV
for path in "$TMPDIR" "$XDG_CACHE_HOME" "$UV_CACHE_DIR" "$UV_PYTHON_INSTALL_DIR"; do check_path "$path"; done
mkdir -p "$TMPDIR" "$UV_CACHE_DIR"
cd "$root"
"$BASE_PYTHON" -c 'import sys; assert sys.version_info[:2] == (3, 12)'
mkdir "$BUILD_BUNDLE"
trap 'status=$?; printf "%s\n" "$status" > "$BUILD_BUNDLE/exit-code"; exit "$status"' EXIT
cp "$source_dir/build-reviewed.sbatch" "$source_dir/inputs.sha256" "$source_dir/build.lock" \
    "$source_dir/wget-3.2.zip" "$source_dir/tempdir-0.7.1.tar.gz" "$BUILD_BUNDLE/"
"$task_uv_executable" --no-config venv --python "$BASE_PYTHON" "$BUILD_VENV"
"$task_uv_executable" --no-config pip install --python "$BUILD_VENV/bin/python" \
    --no-build --require-hashes --default-index https://pypi.org/simple -r "$BUILD_BUNDLE/build.lock"
"$task_uv_executable" --no-config pip check --python "$BUILD_VENV/bin/python"
"$task_uv_executable" --no-config pip freeze --python "$BUILD_VENV/bin/python" > "$BUILD_BUNDLE/build-installed.txt"
mkdir "$BUILD_BUNDLE/wheelhouse"
for archive in wget-3.2.zip tempdir-0.7.1.tar.gz; do
    "$task_uv_executable" --no-config --offline build "$BUILD_BUNDLE/$archive" \
        --python "$BUILD_VENV/bin/python" --no-build-isolation --wheel --no-create-gitignore \
        --out-dir "$BUILD_BUNDLE/wheelhouse"
done
(cd "$source_dir" && sha256sum --check --strict inputs.sha256)
check_digest "$source_dir/build-reviewed.sbatch" "$BUILD_SCRIPT_SHA256"
"$task_uv_executable" --version > "$BUILD_BUNDLE/uv-version.txt"
sha256sum "$task_uv_executable" | cut -d' ' -f1 > "$BUILD_BUNDLE/uv-sha256.txt"
sha256sum "$BASE_PYTHON" | cut -d' ' -f1 > "$BUILD_BUNDLE/python-sha256.txt"
(cd "$BUILD_BUNDLE" && sha256sum build-reviewed.sbatch inputs.sha256 build.lock \
    wget-3.2.zip tempdir-0.7.1.tar.gz build-installed.txt uv-version.txt uv-sha256.txt \
    python-sha256.txt wheelhouse/*.whl > output.sha256)
echo 'Reviewed source-wheel build completed; output review required before resolution or installation.'
