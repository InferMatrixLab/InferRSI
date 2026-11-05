import argparse
import json
import math
from pathlib import Path

import soundfile as sf
import torch
from bench.workload import load_seed_tts_rows, make_id_sets
from scipy.signal import resample_poly
from vllm_omni.model_executor.models.minicpmo_4_5.batched_token2wav import BatchedToken2Wav
from vllm_omni.model_executor.models.minicpmo_4_5.minicpmo_4_5_token2wav import MiniCPMO45Token2wav

args_parser = argparse.ArgumentParser()
args_parser.add_argument("--model", type=Path, required=True)
args_parser.add_argument("--out", type=Path, required=True)
a = args_parser.parse_args()
a.out.parent.mkdir(parents=True, exist_ok=True)
r = a.out.parent
tmp = r / "setup-prompts"
tmp.mkdir(exist_ok=True)
torch.set_num_threads(4)
torch.backends.cudnn.allow_tf32 = False
torch.backends.cuda.matmul.allow_tf32 = False
model = MiniCPMO45Token2wav(str(a.model / "assets/token2wav"), device="cuda", float16=False)
backend = BatchedToken2Wav(model, setup_cache_size=0, cfm_tf32=True)
rows = load_seed_tts_rows()
ids = make_id_sets(rows).tuning_pool[:64]
byid = {x.row_id: x for x in rows}
features = []
for ident in ids:
    wav, sr = sf.read(byid[ident].ref_wav_path, dtype="float32")
    wav = wav.mean(axis=1) if wav.ndim == 2 else wav
    if len(wav) < 6 * sr:
        continue
    wav = wav[: 6 * sr]
    if sr != 24000:
        g = math.gcd(sr, 24000)
        wav = resample_poly(wav, 24000 // g, sr // g).astype("float32")
    p = tmp / f"{len(features)}.wav"
    sf.write(p, wav, 24000)
    features.append(backend.prepare_prompt(str(len(features)), str(p)))
    if len(features) == 4:
        break
assert len(features) == 4
assert len({(x.speech_tokens.shape[1], x.mels.shape[1]) for x in features}) == 1
results = []


def error(a, b):
    return float(torch.linalg.vector_norm(a - b) / torch.linalg.vector_norm(a).clamp_min(1e-12))


with torch.inference_mode():
    reference = [backend.setup_batch(x, 1)[0] for x in features]
    candidate = backend.setup_many(features)
    for i, (a, b) in enumerate(zip(reference, candidate)):
        metrics = {}
        for k in a.flow_cache:
            if k.startswith("conformer"):
                torch.testing.assert_close(a.flow_cache[k], b.flow_cache[k], rtol=0, atol=0)
            metrics[k] = error(a.flow_cache[k], b.flow_cache[k])
        tokens = features[i].speech_tokens[:, :28].contiguous()
        torch.manual_seed(2000 + i)
        aa, _ = backend.decode_batch(tokens, features[i], [a], last_chunk=False)
        torch.manual_seed(2000 + i)
        bb, _ = backend.decode_batch(tokens, features[i], [b], last_chunk=False)
        metrics["continuation_audio"] = error(aa[0], bb[0])
        results.append({"prompt_index": i, "errors": metrics})
        print(results[-1], flush=True)
report = {
    "scope": (
        "Four distinct six-second references from the first64 reused tuning IDs; "
        "individual encoders, shared FP32 prompt solve, paired continuation on "
        "reference speech tokens"
    ),
    "rows": results,
    "verdict": "PASS" if all(v <= 0.01 for x in results for v in x["errors"].values()) else "FAIL",
}
a.out.write_text(json.dumps(report, indent=2) + "\n")
print(report["verdict"], flush=True)
