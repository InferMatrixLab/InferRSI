import argparse
import hashlib
import json
import time
from pathlib import Path

import torch
import torchaudio
from torchaudio.compliance import kaldi
from vllm.config import ModelConfig, VllmConfig
from vllm_omni.model_executor.models.cosyvoice3.speaker_embedding_torch import get_campplus_torch
from vllm_omni.model_executor.models.minicpmo_4_5.speaker_cuda_graph import SpeakerCudaGraph

parser = argparse.ArgumentParser(
    description="Check exact Torch CAM++ graph replay on four reused reference WAVs"
)
parser.add_argument("--model-assets", type=Path, required=True)
parser.add_argument("--prompts", type=Path, required=True)
parser.add_argument("--out", type=Path, required=True)
a = parser.parse_args()
paths = sorted(a.prompts.glob("*.wav"))
assert len(paths) == 4, "Expected four normalized reference WAVs"

torch.set_num_threads(4)
torch.backends.cudnn.allow_tf32 = False
torch.backends.cuda.matmul.allow_tf32 = True
model = get_campplus_torch(str(a.model_assets / "campplus.onnx"), "cuda")
features = []
for p in paths:
    wav, sr = torchaudio.load(p)
    if sr != 16000:
        wav = torchaudio.functional.resample(wav, sr, 16000)
    feat = kaldi.fbank(wav, num_mel_bins=80, dither=0, sample_frequency=16000)
    feat -= feat.mean(dim=0, keepdim=True)
    features.append(feat.cuda())

config = VllmConfig()
config.model_config = ModelConfig.__new__(ModelConfig)
config.model_config.multimodal_config = None
wrapper = SpeakerCudaGraph(model, config)
rows = []
with torch.inference_mode():
    for i, feat in enumerate(features):
        wrapper(feat)
        captured = wrapper(feat)
        eager = model(feat)
        eager2 = model(feat)
        torch.cuda.synchronize()

        def measure(fn):
            vals = []
            for _ in range(20):
                torch.cuda.synchronize()
                start = time.perf_counter()
                fn()
                torch.cuda.synchronize()
                vals.append(time.perf_counter() - start)
            return sum(vals) / len(vals)

        def replay():
            return wrapper(feat)

        row = {
            "index": i,
            "reference_sha256": hashlib.sha256(paths[i].read_bytes()).hexdigest(),
            "shape": list(feat.shape),
            "eager_repeat_equal": torch.equal(eager, eager2),
            "graph_equal": torch.equal(eager, captured),
            "max_abs": float((eager - captured).abs().max()),
            "eager_s": measure(lambda: model(feat)),
            "graph_s": measure(replay),
        }
        rows.append(row)
        print(row, flush=True)

d = {
    "scope": "Four reused references; CAM++ component diagnostic, not service performance",
    "rows": rows,
    "gate": "PASS" if all(x["graph_equal"] and x["eager_repeat_equal"] for x in rows) else "FAIL",
}
a.out.write_text(json.dumps(d, indent=2) + "\n")
assert d["gate"] == "PASS", d
