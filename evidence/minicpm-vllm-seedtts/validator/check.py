"""Component-only S3 exact replay protocol; does not certify service RTF."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

p = argparse.ArgumentParser()
p.add_argument('--candidate', required=True)
p.add_argument('--result', required=True)
p.add_argument('--quality', action='store_true')
args = p.parse_args()
sys.path.insert(0, args.candidate)
import torch
import s3tokenizer
from vllm.config import ModelConfig, VllmConfig

assert hashlib.sha256(Path(s3tokenizer.model_v2.__file__).read_bytes()).hexdigest() == 'c4ddd7b6e95f050a2575309baef8eba990a56654b1893e2e03f95c0bd0e0677f'

torch.set_num_threads(4)
torch.manual_seed(17)
model = Path('/data/models/hub/models--openbmb--MiniCPM-o-4_5/snapshots/503e754207c94da6bb26850b4469f367c9ea3582/assets/token2wav/speech_tokenizer_v2_25hz.onnx')
tokenizer = s3tokenizer.load_model(str(model)).cuda().eval()
tokenizer.encoder.freqs_cis = tokenizer.encoder.freqs_cis.cuda()
def eager(mels, lengths):
    h, n = tokenizer.encoder(mels, lengths)
    return tokenizer.quantizer.encode(h), n
forward = eager
candidate_file = Path(args.candidate) / 'vllm_omni/model_executor/models/minicpmo_4_5/s3_cuda_graph.py'
if candidate_file.exists():
    from vllm_omni.model_executor.models.minicpmo_4_5.s3_cuda_graph import S3CudaGraph
    config = VllmConfig()
    config.model_config = ModelConfig.__new__(ModelConfig)
    config.model_config.multimodal_config = None
    forward = S3CudaGraph(tokenizer, config)

samples = []
with torch.inference_mode():
    for frames in (600, 1200):
        lengths = torch.tensor([frames], dtype=torch.int32, device='cuda')
        mel = torch.randn(1, 128, frames, device='cuda')
        for _ in range(5):
            forward(mel, lengths)
        if args.quality:
            for i in range(8):
                mel.normal_()
                actual = forward(mel, lengths)
                expected = eager(mel, lengths)
                for a, b in zip(actual, expected, strict=True):
                    torch.testing.assert_close(a, b, rtol=0, atol=0)
        else:
            for _ in range(5):
                torch.cuda.synchronize()
                start = time.perf_counter()
                for _ in range(20):
                    forward(mel, lengths)
                torch.cuda.synchronize()
                samples.append((time.perf_counter() - start) * 1000 / 20)
result = {'quality': True} if args.quality else {'latency_ms': statistics.median(samples), 'samples_ms': samples}
if args.quality:
    references = json.loads(Path(__file__).with_name('references.json').read_text())
    data = Path('/data/models/hub/datasets--zhaochenyang20--seed-tts-eval/snapshots/8f5e1aa2a35d42f42e940074c1983358b9491f89/en/prompt-wavs')
    if candidate_file.exists():
        forward = S3CudaGraph(tokenizer, config)
    with torch.inference_mode():
        for ref in references:
            wav = data / ref['file']
            assert hashlib.sha256(wav.read_bytes()).hexdigest() == ref['sha256']
            audio = s3tokenizer.load_audio(str(wav))
            mel, lengths = s3tokenizer.padding([s3tokenizer.log_mel_spectrogram(audio)])
            assert mel.shape[-1] <= 3000
            mel, lengths = mel.cuda(), lengths.cuda()
            expected = eager(mel, lengths)
            for _ in range(3):
                for a, b in zip(forward(mel, lengths), expected, strict=True):
                    torch.testing.assert_close(a, b, rtol=0, atol=0)
    result['real_references'] = len(references)
    if candidate_file.exists():
        result['graph_stats'] = forward.graph.get_cumulative_stats()
        assert result['graph_stats']['num_graphs'] == 2
result['scope'] = 'L0/L1 S3 only (16 real references plus synthetic inputs); service acceptance INCONCLUSIVE'
Path(args.result).write_text(json.dumps(result, indent=2))
