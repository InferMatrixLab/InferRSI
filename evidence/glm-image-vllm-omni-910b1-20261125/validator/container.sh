#!/usr/bin/env bash
set -euo pipefail
: "${ASCEND_RT_VISIBLE_DEVICES:?Launch inside npu run --gpus 2}"
: "${GLM_RSI_WORKSPACE:?Set this to the experiment workspace containing the frozen protocol, execution snapshots and outputs}"
: "${GLM_IMAGE_WEIGHTS:?Set this to the staged GLM-Image checkpoint directory}"
: "${GLM_OMNI_IMAGE:?Set this to the tested Ascend vLLM-Omni runtime image}"
[[ $ASCEND_RT_VISIBLE_DEVICES =~ ^[0-9]+,[0-9]+$ ]]
protocol=$(cd "$(dirname "$0")" && pwd -P)
mode=$1
source_dir=$2
result=$3
exec docker run --rm --init --runtime=ascend --privileged --shm-size=12g \
    -e ASCEND_RT_VISIBLE_DEVICES -e HF_HUB_OFFLINE=1 -e OMP_NUM_THREADS=4 -e PYTHONDONTWRITEBYTECODE=1 \
    -e GLM_IMAGE_MODEL=/weights/GLM-Image \
    -v "$GLM_RSI_WORKSPACE:$GLM_RSI_WORKSPACE" -v "$GLM_IMAGE_WEIGHTS:/weights/GLM-Image:ro" \
    -v /usr/local/Ascend/driver:/usr/local/Ascend/driver:ro -v /usr/local/Ascend/firmware:/usr/local/Ascend/firmware:ro \
    -v /etc/ascend_install.info:/etc/ascend_install.info:ro \
    -v "$source_dir:$source_dir:ro" -w /tmp --entrypoint bash "$GLM_OMNI_IMAGE" \
    -c 'export PYTHONPATH="$3:${PYTHONPATH:-}"; exec python -u "$1" "$2" "$3" "$4"' \
    bash "$protocol/engine.py" "$mode" "$source_dir" "$result"
