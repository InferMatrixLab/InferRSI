#!/usr/bin/env bash
set -eo pipefail
root=/dataset/home/z00897794/experiments/hunyuan3-ar-rsi
cd "$root"
export OMNI_REPO="$1"
deploy="$2"
out="$3"
mode="$4"
source native-stage-env.sh
test -n "$ASCEND_RT_VISIBLE_DEVICES"
export HF_MODULES_CACHE="$root/full-data/hfmodules" HCCL_CONNECT_TIMEOUT=120 HCCL_NPU_SOCKET_PORT_RANGE=auto
export HCCL_DETERMINISTIC=true
export LCCL_DETERMINISTIC=1
if [[ "$mode" = invariant* ]]; then
    export HCCL_DETERMINISTIC=strict VLLM_BATCH_INVARIANT=1
    if [[ "$mode" = invariant-opp* ]]; then
        source "$root/lossless-rsi/invariant-opp-only.sh"
    else
        source "$root/lossless-rsi/invariant-env.sh"
    fi
fi
jobdir=$(mktemp -d "$root/lossless-rsi/jobs/trial.XXXX")
echo "$jobdir" >> "$root/lossless-rsi/locations.txt"
cd "$jobdir"
trial=stage_trial.py
if [[ "$mode" = *fixed ]]; then trial=stage_fixed_admission.py; fi
python -u "$root/scheduling-rsi/stage.py" --scenario "$5" --model /dataset/models/HunyuanImage-3.0-Instruct-2ec2c78 --deploy "$deploy" --out "$out" > worker.log 2>&1 || { tail -30 worker.log; exit 1; }
