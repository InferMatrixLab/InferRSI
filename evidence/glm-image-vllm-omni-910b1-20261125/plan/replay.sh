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
session="$GLM_RSI_WORKSPACE/campaign"
inferrsi campaign start --directory "$session" --repo "$GLM_BASELINE" --include vllm_omni \
    --protocol "$bundle/validator" --instructions "$bundle/plan/TASK.md" \
    --measure-command 'bash {protocol}/container.sh measure {candidate} {result}' \
    --quality-command 'bash {protocol}/container.sh quality {candidate} {result}' \
    --metric-key latency_s --metric-unit s/image --direction minimize --quality-key quality \
    --scope 'Single warm 512x512 text-to-image request through native Omni.generate, including AR and 20-step diffusion, on 2x Ascend 910B1.' \
    --min-improvement-pct 3 --repetitions 2 --warmups 0 --rounds 3 --round-mode up_to \
    --max-minutes 420 --evaluation-timeout-seconds 8400 --final-reserve-seconds 8200 --knowledge on
inferrsi campaign diagnose --directory "$session" --bottleneck 'Repeated M-RoPE table construction in the AR decoder' --evidence "$bundle/plan/diagnosis.md"
inferrsi campaign knowledge --directory "$session" \
    --query 'Autoregressive transformer GLM image generation latency on Ascend NPU: invariant rotary position embeddings precompute reuse across decoder layers, same-token operator dispatch and identical output validation.' \
    --context-bytes 13000 --limit 6 > "$GLM_RSI_WORKSPACE/knowledge.json"
ref=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["reference"]["path"])' "$GLM_RSI_WORKSPACE/knowledge.json")
inferrsi campaign round --directory "$session" --candidate "$GLM_CANDIDATE" \
    --hypothesis 'Sharing M-RoPE tables eliminates repeated per-layer operations and preserves Q/K rotation and pixels.' \
    --strategy 'Share position-dependent tensors within one forward.' \
    --knowledge-ref "$ref#package:vllm_omni.ascend.diffusion.qwen_image_21_eager_t2i"
inferrsi campaign final --directory "$session" --reason 'Independently retest the retained implementation.'
