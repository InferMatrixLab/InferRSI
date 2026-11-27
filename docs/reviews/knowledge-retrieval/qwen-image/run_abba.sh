#!/usr/bin/env bash
set -euo pipefail
# Run from an existing one-card npu reservation. The four blocks share its physical device.
here=$(cd -- "$(dirname "$0")" && pwd)
: "${OMNI_CHECKOUT:?path to the pinned vllm-omni checkout}"
: "${CHECKPOINT:?path to Qwen-Image-2.1-Turbo}"
: "${RESULTS:?fresh output directory}"
mkdir -p "$RESULTS"
[[ $(git -C "$OMNI_CHECKOUT" rev-parse HEAD) == 399cc01d1bc4542964d91aaa17fb43862a8cf3b3 ]]
readarray -t blocks < <(python - "$here" <<'PLAN'
import json, sys
from collections import Counter
from pathlib import Path
root = Path(sys.argv[1])
arms = {a: json.loads((root / f"{name}.json").read_text())["rope"]
        for a, name in [("A", "raw"), ("B", "round")]}
counts = Counter()
for arm in json.loads((root / "protocol.json").read_text())["order"]:
    counts[arm] += 1
    print(f"{arm}{counts[arm]}:{arms[arm]}")
PLAN
)
[[ ${#blocks[@]} == 4 ]]
device=${ASCEND_RT_VISIBLE_DEVICES:?}
[[ "$device" =~ ^[0-9]+$ ]]
for spec in "${blocks[@]}"; do
  tag=${spec%:*}
  rope=${spec##*:}
  [[ ! -e "$RESULTS/$tag" && ! -e "$RESULTS/$tag.exit" ]]
  status=0
  docker run --rm --init --runtime=ascend --privileged --cgroupns=host --security-opt label=disable --network none --shm-size=4g \
    --device "/dev/davinci$device" --device /dev/davinci_manager --device /dev/devmm_svm --device /dev/hisi_hdc \
    -e ASCEND_RT_VISIBLE_DEVICES="$device" -e QWEN21_NPU_ROPE="$rope" -e DIFFUSION_ATTENTION_BACKEND=TORCH_SDPA \
    -e HF_HUB_OFFLINE=1 -e VLLM_NO_USAGE_STATS=1 -e OMP_NUM_THREADS=4 -e PYTHONDONTWRITEBYTECODE=1 \
    -v /usr/local/Ascend/driver:/usr/local/Ascend/driver:ro -v /usr/local/Ascend/firmware:/usr/local/Ascend/firmware:ro \
    -v /etc/ascend_install.info:/etc/ascend_install.info:ro -v "$OMNI_CHECKOUT":/engine:ro -v "$here/image_run.py":/run_image.py:ro \
    -v "$RESULTS":/results -v "$CHECKPOINT":/model:ro -w /tmp \
    sha256:9b520672249791a96e11dd424379c6eb3c91965c75738ba385efd43142236265 \
    bash -c 'source /usr/local/Ascend/ascend-toolkit/set_env.sh && export PYTHONPATH=/engine:${PYTHONPATH:-} && python /run_image.py "$1"' bash "$tag" || status=$?
  echo "$tag container exit $status"
  echo "$status" > "$RESULTS/$tag.exit"
  if [[ "$status" != 0 ]]; then
    [[ "$status" == 134 ]]
    python - "$RESULTS/$tag" <<'CHECK'
import hashlib, json, sys
from pathlib import Path
from PIL import Image
p = Path(sys.argv[1])
rows = json.loads((p / 'timings.json').read_text())
assert [r['seed'] for r in rows] == [40, 41, 42, 43, 44]
for r in rows:
    with Image.open(p / f"{r['seed']}.png") as im:
        assert im.size == (1280, 704)
        assert hashlib.sha256(im.convert('RGBA').tobytes()).hexdigest() == r['rgba_sha256']
CHECK
  fi
done
