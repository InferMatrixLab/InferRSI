import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any

import torch
from vllm.v1.serial_utils import MsgpackDecoder, MsgpackEncoder
from vllm_omni.model_executor.models.minicpmo_4_5.handoff import (
    pack_handoff_tensor,
    unpack_handoff_tensor,
)
from vllm_omni.worker.gpu_model_runner import OmniGPUModelRunner

parser = argparse.ArgumentParser(
    description="CPU transport microbenchmark; run with the candidate on PYTHONPATH"
)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
if args.out.exists():
    raise FileExistsError(args.out)
ref = torch.linspace(-0.8, 0.8, 144000)
hidden = torch.linspace(-2, 2, 32 * 4096).reshape(32, 4096).to(torch.bfloat16)
encoder = MsgpackEncoder()
decoder = MsgpackDecoder(dict[str, Any])


def run(packed):
    payload = {
        "codes": {"ref": pack_handoff_tensor(ref) if packed else ref.tolist()},
        "hidden_states": {"tts": pack_handoff_tensor(hidden) if packed else hidden.tolist()},
    }
    received = decoder.decode(encoder.encode(payload))
    stored = {}
    for group, values in received.items():
        stored[group] = {}
        for key, value in values.items():
            OmniGPUModelRunner._store_value(None, stored[group], key, value, set())
    a = torch.as_tensor(unpack_handoff_tensor(stored["codes"]["ref"]), dtype=torch.float32)
    b = torch.as_tensor(unpack_handoff_tensor(stored["hidden_states"]["tts"]), dtype=torch.float32)
    return a, b


for packed in (False, True):
    a, b = run(packed)
    assert torch.equal(a, ref) and torch.equal(b, hidden.float())
for _ in range(10):
    run(False)
    run(True)
samples = {False: [], True: []}
for i in range(100):
    for packed in (False, True) if i % 2 == 0 else (True, False):
        start = time.perf_counter()
        run(packed)
        samples[packed].append((time.perf_counter() - start) * 1000)
result = {
    "scope": "CPU synthetic transport diagnostic, not service throughput",
    "shapes": {"reference": [144000], "hidden": [32, 4096]},
    "hidden_source_dtype": "bfloat16",
    "consumer_dtype": "float32",
    "warmup_each": 10,
    "iterations_each": 100,
    "order": "alternating AB/BA",
    "bitwise_values_equal": True,
    "results": {
        ("packed" if k else "legacy_list"): {
            "median_ms": statistics.median(v),
            "mean_ms": statistics.mean(v),
            "samples_ms": v,
        }
        for k, v in samples.items()
    },
}
args.out.write_text(json.dumps(result, indent=2) + "\n")
print({k: {s: t for s, t in v.items() if s != "samples_ms"} for k, v in result["results"].items()})
