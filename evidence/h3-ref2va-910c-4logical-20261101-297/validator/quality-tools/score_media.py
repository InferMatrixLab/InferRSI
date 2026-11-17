"""CPU-only, source-pinned descriptors for the H3 relative-quality contract."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
os.environ['TORCH_DEVICE_BACKEND_AUTOLOAD'] = '0'
sys.path[:0] = [str(ROOT / 'quality-adapter'), str(ROOT / 'source/clip'),
               str(ROOT / 'source/dino'), str(ROOT / 'validator')]
import av
import cv2
import numpy as np
from PIL import Image
import torch
import torch.nn.functional as F
import clip
import vision_transformer
from scipy.signal import resample_poly
from vbench.subject_consistency import subject_consistency
from vbench.background_consistency import background_consistency
from vbench.utils import dino_transform_Image
from check_media import inspect


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(array):
    return array / np.linalg.norm(array, axis=-1, keepdims=True).clip(1e-12)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--media', required=True)
    parser.add_argument('--request', required=True)
    parser.add_argument('--sample-id', required=True)
    parser.add_argument('--audio-caption', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--contract')
    args = parser.parse_args()
    torch.set_num_threads(8)
    request = json.loads(Path(args.request).read_text())
    assert int(request['num_inference_steps']) == 50
    duration = int(request['seconds'])
    expected_frames = {5: 124, 15: 362}[duration]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    source_media = Path(args.media).resolve()
    media_info = inspect(source_media, expected_frames)
    contract_hash = None
    if args.contract:
        path = Path(args.contract)
        contract = json.loads(path.read_text())
        contract_hash = digest(path)
        assert digest(Path(__file__)) == contract['scorer_sha256']
        sample = next(item for item in contract['samples'] if item['id'] == args.sample_id)
        assert sample['audio_caption'] == args.audio_caption
        for key in ['model', 'prompt', 'width', 'height', 'aspect_ratio', 'fps', 'seconds',
                    'num_inference_steps', 'seed', 'flow_shift', 'image_reference']:
            assert request[key] == sample['request'][key]
        for key in ['task', 'duration', 'audio_flow_shift']:
            assert json.loads(request['extra_params'])[key] == json.loads(sample['request']['extra_params'])[key]
        for entry in contract['weight_files']:
            assert digest(ROOT / entry['path']) == entry['sha256']
        for entry in contract['source_files']:
            assert digest(ROOT / entry['path']) == entry['sha256']
        assert digest(ROOT / 'assets/reference.png') == contract['reference_image_sha256']
    videos = output / 'videos'
    videos.mkdir()
    (videos / 'clip.mp4').symlink_to(source_media)
    frames = output / 'frames/clip'
    frames.mkdir(parents=True)
    pts, motion, previous = [], [], None
    decoded_hash = hashlib.sha256()
    with av.open(str(source_media)) as reader:
        for index, frame in enumerate(reader.decode(video=0)):
            pixels = frame.to_ndarray(format='rgb24')
            decoded_hash.update(pixels.tobytes())
            assert frame.time is not None
            pts.append(float(frame.time))
            Image.fromarray(pixels).save(frames / f'{index:05d}.png', compress_level=1)
            small = cv2.resize(pixels, (128, 72), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
            grey = small @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
            if previous is not None:
                motion.append(float(np.abs(grey - previous).mean()))
            previous = grey
    assert decoded_hash.hexdigest() == media_info['rgb24_sha256']
    assert len(pts) == expected_frames and np.all(np.diff(pts) > 0)
    assert np.max(np.abs(np.diff(pts) - 1 / 24)) < 1e-6
    weights = ROOT / 'quality-cache/weights'
    clip_model, transform = clip.load(str(weights / 'ViT-B-32.pt'), device='cpu', jit=False)
    dino = vision_transformer.vit_base(patch_size=16, num_classes=0)
    dino.load_state_dict(torch.load(weights / 'dino_vitbase16_pretrain.pth',
                                   map_location='cpu', weights_only=True), strict=True)
    dino.eval()
    dino_features, clip_features = [], []
    dino_hook = dino.register_forward_hook(lambda module, inputs, result:
                                          dino_features.append(result.detach().cpu().numpy()))
    clip_hook = clip_model.visual.register_forward_hook(lambda module, inputs, result:
                                                        clip_features.append(result.detach().cpu().numpy()))
    with torch.inference_mode():
        subject = subject_consistency(dino, [str(videos / 'clip.mp4')], 'cpu', True)
        background = background_consistency(clip_model, transform, [str(videos / 'clip.mp4')], 'cpu', True)
    dino_hook.remove()
    clip_hook.remove()
    dino_features = normalize(np.concatenate(dino_features))
    clip_features = normalize(np.concatenate(clip_features))
    assert dino_features.shape[0] == clip_features.shape[0] == expected_frames
    reference = Image.open(ROOT / 'assets/reference.png').convert('RGB')
    with torch.inference_mode():
        ref_clip = F.normalize(clip_model.encode_image(transform(reference).unsqueeze(0)), dim=-1).numpy()[0]
        ref_dino = F.normalize(dino(dino_transform_Image(224)(reference).unsqueeze(0)), dim=-1).numpy()[0]
        text_clip = F.normalize(clip_model.encode_text(clip.tokenize([request['prompt']])), dim=-1).numpy()[0]
    from transformers import ClapModel, ClapFeatureExtractor, RobertaTokenizerFast
    clap_path = ROOT / 'quality-cache/clap/8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a'
    extractor = ClapFeatureExtractor.from_pretrained(clap_path, local_files_only=True)
    tokenizer = RobertaTokenizerFast.from_pretrained(clap_path, local_files_only=True)
    clap_model = ClapModel.from_pretrained(clap_path, local_files_only=True, dtype=torch.float32).cpu().eval()
    assert all(parameter.device.type == 'cpu' for parameter in clap_model.parameters())
    audio, audio_pts = [], []
    with av.open(str(source_media)) as reader:
        for frame in reader.decode(audio=0):
            assert frame.time is not None
            audio_pts.append(float(frame.time))
            audio.append(frame.to_ndarray())
    audio = np.concatenate(audio, axis=1)
    assert np.all(np.diff(audio_pts) > 0)
    assert np.max(np.diff(audio_pts)) <= 1025 / 32000
    assert abs(pts[0] - audio_pts[0]) <= 1 / 24
    mono = resample_poly(audio.mean(axis=0), 3, 2)
    boundaries = np.linspace(0, len(mono), {5: 1, 15: 3}[duration] + 1).astype(int)
    clap_features = []
    with torch.inference_mode():
        for start, end in zip(boundaries[:-1], boundaries[1:]):
            np.random.seed(0)
            inputs = extractor(mono[start:end], sampling_rate=48000, return_tensors='pt')
            clap_features.append(clap_model.get_audio_features(**inputs).pooler_output.numpy()[0])
        audio_text = clap_model.get_text_features(**tokenizer([args.audio_caption], return_tensors='pt',
                                                              padding=True)).pooler_output.numpy()[0]
    clap_features = normalize(np.stack(clap_features))
    envelope = []
    for index in range(expected_frames):
        start, end = int(index * 32000 / 24), min(int((index + 1) * 32000 / 24), audio.shape[1])
        assert end > start
        envelope.append(float(np.sqrt(np.mean(audio[:, start:end].astype(np.float64) ** 2))))
    features = {'dino': dino_features, 'clip': clip_features, 'clap': clap_features,
                'audio_rms_envelope': np.array(envelope), 'motion': np.array(motion)}
    assert all(np.isfinite(value).all() for value in features.values())
    assert 'torch_npu' not in sys.modules
    np.savez_compressed(output / 'features.npz', **features)
    result = {'sample_id': args.sample_id, 'request': request, 'contract_sha256': contract_hash,
              'media_sha256': digest(source_media), 'media': media_info,
              'features_sha256': digest(output / 'features.npz'),
              'vbench': {'subject_consistency': subject[0], 'background_consistency': background[0]},
              'reference_clip_cosine': float((clip_features @ ref_clip).mean()),
              'reference_dino_cosine': float((dino_features @ ref_dino).mean()),
              'prompt_clip_cosine': float((clip_features @ text_clip).mean()),
              'audio_caption_clap_cosine': float((clap_features @ audio_text).mean()),
              'clipping_fraction': float(np.mean(np.abs(audio) >= 0.999)),
              'pts_start_difference_seconds': pts[0] - audio_pts[0],
              'cpu_only': True, 'quality_verdict': 'INCONCLUSIVE; descriptors require paired validation',
              'scope': 'relative BF16 quality proxies; timestamps do not establish semantic AV synchrony'}
    (output / 'score.json').write_text(json.dumps(result, indent=2, allow_nan=False))
    print(json.dumps({key: value for key, value in result.items() if key not in ('media', 'request')}), flush=True)


if __name__ == '__main__':
    main()
