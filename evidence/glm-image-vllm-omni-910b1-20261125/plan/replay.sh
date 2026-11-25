#!/usr/bin/env bash
# Run with npu run --gpus 2 -- bash plan/replay.sh inside the documented environment.
set -euo pipefail
: "${ASCEND_RT_VISIBLE_DEVICES:?Reserve two devices with npu run}"
: "${GLM_RSI_WORKSPACE:?Set an absolute directory for the retained experiment}"
: "${GLM_BASELINE:?Set the stock vLLM-Omni checkout directory}"
: "${GLM_CANDIDATE:?Set the candidate vLLM-Omni checkout directory}"
: "${GLM_IMAGE_WEIGHTS:?Set the staged checkpoint directory}"
: "${GLM_OMNI_IMAGE:?Set the compatible local Ascend runtime image}"
bundle=$(cd "$(dirname "$0")/.." && pwd -P)
cohort=${GLM_COHORT:-shared}
case "$cohort" in
    shared)
        data="$bundle"
        task="$bundle/plan/TASK.md"
        diagnosis="$bundle/plan/diagnosis.md"
        query='Autoregressive transformer GLM image generation latency on Ascend NPU: invariant rotary position embeddings precompute reuse across decoder layers, same-token operator dispatch and identical output validation.'
        hypothesis='Sharing M-RoPE tables eliminates repeated per-layer operations and preserves Q/K rotation and pixels.'
        strategy='Share position-dependent tensors within one forward.'
        extra=()
        rounds=3
        knowledge_bytes=13000
        ;;
    packed)
        data="$bundle/incremental"
        task="$data/criteria.md"
        diagnosis="$data/diagnosis.md"
        query='Ascend rotary embedding fuse Q and K BF16 kernel dispatch exact rounding group query attention fused QKV layout partial rotary batch token'
        hypothesis=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["hypothesis"])' "$data/decision.json")
        strategy=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["strategy"])' "$data/decision.json")
        mapfile -t extra < <(python - "$data/decision.json" <<'PYTHON'
import json
import sys

decision = json.load(open(sys.argv[1]))
for option in decision["alternatives"]:
    print("--alternative")
    print(option)
print("--selection-reason")
print(decision["selection_reason"])
PYTHON
        )
        rounds=2
        knowledge_bytes=16000
        ;;
    *) echo 'GLM_COHORT must be shared or packed' >&2; exit 2 ;;
esac
rsi_python=${GLM_RSI_PYTHON:-python}
GLM_OMNI_IMAGE=$("$rsi_python" -B "$bundle/plan/preflight.py" "$cohort")
export GLM_OMNI_IMAGE
session="$GLM_RSI_WORKSPACE/campaign-$cohort"
"$rsi_python" -m inferrsi campaign start --directory "$session" --repo "$GLM_BASELINE" --include vllm_omni \
    --protocol "$data/validator" --instructions "$task" \
    --measure-command 'bash {protocol}/container.sh measure {candidate} {result}' \
    --quality-command 'bash {protocol}/container.sh quality {candidate} {result}' \
    --metric-key latency_s --metric-unit s/image --direction minimize --quality-key quality \
    --scope 'Single warm 512x512 text-to-image request through native Omni.generate, including AR and 20-step diffusion, on 2x Ascend 910B1.' \
    --min-improvement-pct 3 --repetitions 2 --warmups 0 --rounds "$rounds" --round-mode up_to \
    --max-minutes 420 --evaluation-timeout-seconds 8400 --final-reserve-seconds 8200 --knowledge on
"$rsi_python" -m inferrsi campaign diagnose --directory "$session" --bottleneck 'GLM-Image autoregressive position-embedding overhead' --evidence "$diagnosis"
"$rsi_python" -m inferrsi campaign knowledge --directory "$session" \
    --query "$query" --context-bytes "$knowledge_bytes" --limit 6 > "$GLM_RSI_WORKSPACE/knowledge.json"
ref=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["reference"]["path"])' "$GLM_RSI_WORKSPACE/knowledge.json")
"$rsi_python" -m inferrsi campaign round --directory "$session" --candidate "$GLM_CANDIDATE" \
    --hypothesis "$hypothesis" --strategy "$strategy" "${extra[@]}" \
    --knowledge-ref "$ref#package:vllm_omni.ascend.diffusion.qwen_image_21_eager_t2i"
"$rsi_python" -m inferrsi campaign final --directory "$session" --reason 'Independently retest the retained implementation.'
