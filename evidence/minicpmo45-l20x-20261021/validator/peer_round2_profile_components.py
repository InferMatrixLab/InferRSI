import argparse
import functools
import json
import time
from pathlib import Path

import torch
import vllm_omni.model_executor.models.step_audio2.step_audio2_token2wav as core_module
from vllm_omni.model_executor.models.minicpmo_4_5.batched_token2wav import BatchedToken2Wav
from vllm_omni.model_executor.models.minicpmo_4_5.minicpmo_4_5_token2wav import MiniCPMO45Token2wav

parser = argparse.ArgumentParser()
parser.add_argument("--model", type=Path, required=True)
parser.add_argument(
    "--prompts",
    type=Path,
    required=True,
    help="Directory containing the four normalized six-second tuning WAVs from the setup probe",
)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
args.out.parent.mkdir(parents=True, exist_ok=True)
torch.set_num_threads(4)
torch.backends.cudnn.allow_tf32 = False
torch.backends.cuda.matmul.allow_tf32 = True
model = MiniCPMO45Token2wav(
    str(args.model / "assets/token2wav"), device="cuda", drop_upstream_chunk_att_buffers=True
)
model.enable_device_spk_embedding(use_trt=False)
backend = BatchedToken2Wav(
    model,
    setup_cache_size=0,
    cfm_tf32=True,
    connector_config={"codec_chunk_frames": 25, "codec_left_context_frames": 3},
    cfm_graph_config={
        "enabled": True,
        "fused_body": True,
        "micro_batch_size": 4,
        "max_graph_batch": 32,
        "max_graphs": 32,
        "offset_bucket_frames": 50,
    },
)
records = []


def wrap(obj, name, label):
    original = getattr(obj, name)

    @functools.wraps(original)
    def measured(*args, **kwargs):
        torch.cuda.synchronize()
        start = time.perf_counter()
        result = original(*args, **kwargs)
        torch.cuda.synchronize()
        records.append({"component": label, "seconds": time.perf_counter() - start})
        return result

    setattr(obj, name, measured)


wrap(model._core.audio_tokenizer, "quantize", "s3_tokens")
wrap(model._core, "_forward_spk_embedding", "speaker")
wrap(core_module, "load_audio", "audio_load")
wrap(core_module.s3tokenizer, "log_mel_spectrogram", "s3_mel")
wrap(core_module.kaldi, "fbank", "speaker_fbank")
wrap(core_module, "mel_spectrogram", "flow_mel")
wrap(model._core, "_prepare_prompt", "prompt_total")
wrap(backend, "setup_batch", "setup_total")
wrap(backend, "_decode_cfm", "cfm_total")
wrap(backend, "_encode_chunk_eager", "encoder_eager")
wrap(backend, "decode_batch", "decode_total")
paths = sorted(args.prompts.glob("*.wav"))
assert len(paths) == 4
with torch.inference_mode():
    for repeat in range(3):
        for i, p in enumerate(paths):
            before = len(records)
            f = backend.prepare_prompt(f"{repeat}-{i}", str(p))
            state = backend.setup_batch(f, 1)[0]
            tokens = f.speech_tokens[:, :28].contiguous()
            for step in range(4):
                audio, states = backend.decode_batch(tokens, f, [state], last_chunk=step == 3)
                state = states[0]
            for row in records[before:]:
                row.update(repeat=repeat, prompt_index=i)
            print("DONE", repeat, i, flush=True)
result = {
    "scope": (
        "Four reused tuning references; CFM graphs enabled, HiFT/encoder eager. "
        "Inclusive synchronized timings; first iteration excluded, not service throughput"
    ),
    "rows": records,
    "cuda_peak_bytes": torch.cuda.max_memory_allocated(),
}
args.out.write_text(json.dumps(result, indent=2) + "\n")
for k in sorted({x["component"] for x in records}):
    vals = [x["seconds"] for x in records if x["component"] == k and x["repeat"] > 0]
    print(k, len(vals), sum(vals) / len(vals), flush=True)
