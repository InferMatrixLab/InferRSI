import argparse
import json
import math
from pathlib import Path

import soundfile as sf
import torch
from bench.workload import load_seed_tts_rows, make_id_sets
from scipy.signal import resample_poly
from vllm_omni.model_executor.models.cosyvoice3.utils import mel_spectrogram
from vllm_omni.model_executor.models.step_audio2.step_audio2_token2wav import _build_hift

args_parser = argparse.ArgumentParser()
args_parser.add_argument("--model", type=Path, required=True)
args_parser.add_argument("--out", type=Path, required=True)
a = args_parser.parse_args()
a.out.parent.mkdir(parents=True, exist_ok=True)
r = a.out.parent
torch.set_num_threads(4)
torch.backends.cuda.matmul.allow_tf32 = False
torch.backends.cudnn.allow_tf32 = False
model = _build_hift()
weights = torch.load(a.model / "assets/token2wav/hift.pt", map_location="cpu", weights_only=True)
model.load_state_dict({k.replace("generator.", ""): v for k, v in weights.items()}, strict=True)
model = model.cuda().eval()
rows = load_seed_tts_rows()
ids = make_id_sets(rows).tuning_pool[:16]
byid = {x.row_id: x for x in rows}
results = []
with torch.inference_mode():
    for i, ident in enumerate(ids):
        wav, sr = sf.read(byid[ident].ref_wav_path, dtype="float32")
        wav = wav.mean(axis=1) if wav.ndim == 2 else wav
        if sr != 24000:
            g = math.gcd(sr, 24000)
            wav = resample_poly(wav, 24000 // g, sr // g).astype("float32")
        mel = mel_spectrogram(
            torch.from_numpy(wav).unsqueeze(0),
            n_fft=1920,
            num_mels=80,
            sampling_rate=24000,
            hop_size=480,
            win_size=1920,
            fmin=0,
            fmax=8000,
            center=False,
        ).cuda()
        assert mel.shape[-1] >= 56
        for width in [16, 50, 56]:
            x = mel[..., :width].contiguous()
            source = torch.empty(1, 1, 0, device="cuda")
            pair = []
            for enabled in [False, True]:
                model.upsample_tf32 = enabled
                torch.manual_seed(1000 + i)
                pair.append(tuple(y.clone() for y in model.inference(x, source)))
                assert (
                    not torch.backends.cudnn.allow_tf32
                    and not torch.backends.cuda.matmul.allow_tf32
                )
            torch.testing.assert_close(pair[0][1], pair[1][1], rtol=0, atol=0)
            err = float(
                torch.linalg.vector_norm(pair[1][0] - pair[0][0])
                / torch.linalg.vector_norm(pair[0][0]).clamp_min(1e-12)
            )
            results.append(
                {
                    "prompt_index": i,
                    "mel_frames": width,
                    "relative_l2": err,
                    "max_absolute": float((pair[1][0] - pair[0][0]).abs().max()),
                }
            )
        print(i, max(x["relative_l2"] for x in results[-3:]), flush=True)
report = {
    "scope": (
        "48 real-speech windows, official HiFT weights, matched random source, empty source cache"
    ),
    "rows": results,
    "max_relative_l2": max(x["relative_l2"] for x in results),
    "verdict": "PASS" if all(x["relative_l2"] <= 0.01 for x in results) else "FAIL",
}
a.out.write_text(json.dumps(report, indent=2) + "\n")
print(report["verdict"], report["max_relative_l2"], flush=True)
