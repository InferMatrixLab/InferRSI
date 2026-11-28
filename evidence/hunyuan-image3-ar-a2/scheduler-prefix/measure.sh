#!/usr/bin/env bash
set -eo pipefail
cd /dataset/home/z00897794/experiments/hunyuan3-ar-rsi
w="$PWD/scheduling-rsi"; g="$PWD/rope-continuation"; cfg=benchmarks/hunyuan_ar_a2_research.yaml
export OMNI_REPO="$w/anchor"
source native-stage-env.sh
export HCCL_DETERMINISTIC=strict LCCL_DETERMINISTIC=1 VLLM_BATCH_INVARIANT=1
source "$PWD/lossless-rsi/invariant-opp-only.sh"
mkdir -p "$w/tmp";export TMPDIR="$w/tmp"
for b in budget1024 budget4096 prefix; do
 workload=$(sha256sum "$w/stage.py" "$w/fixed_admission.py" "$w/anchor/$cfg" "$w/check-trials.py" "$w/protocol.txt" | sha256sum | cut -d' ' -f1)
 PYTHONPATH="$g/inferrsi/src" "$root/runtime/bin/inferrsi" run --repo "$w/anchor" --candidate-repo "$w/$b" --repo-type vllm_omni --backend ascend --device-ids "$ASCEND_RT_VISIBLE_DEVICES" --device-model 910B1 --python "$root/runtime/bin/python" --scenario "hunyuan.ar.scheduling.$b" --mode config --agent codex --baseline-command "bash $w/trial.sh $w/anchor $w/anchor/$cfg {result} invariant-opp-fixed $b" --candidate-command "bash $w/trial.sh $w/$b $w/$b/$cfg {result} invariant-opp-fixed $b" --validation-command "$root/runtime/bin/python $w/check-trials.py $w $b" --metric-key output_tps --metric-unit tokens/s --comparison-scope stage --direction maximize --repetitions 3 --min-improvement-pct 2 --max-minutes 95 --workload-id "$workload" --model tencent/HunyuanImage-3.0-Instruct --model-revision 2ec2c78bee7d4b94157341fba86c4c2c7b1858b2 --output-dir "$w/runs-$b" >"$w/rsi-$b.log" 2>&1 || true
 tail -8 "$w/rsi-$b.log"
done
date -Is >"$w/finished"
