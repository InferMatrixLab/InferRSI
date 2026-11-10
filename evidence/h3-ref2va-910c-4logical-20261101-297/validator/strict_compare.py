"""Compare complete H3 audit evidence without importing either inference arm."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

POINTS = ['initial_noise', 'post_step_000', 'post_step_009', 'post_step_024',
          'post_step_049', 'vae_inputs']
MEDIA_KEYS = ['video_frames', 'width', 'height', 'fps', 'rgb24_sha256',
              'audio_sample_rate', 'audio_channels', 'audio_samples',
              'pcm_f32_interleaved_sha256', 'finite_audio']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--candidate')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    missing, failures, checks = [], [], 0

    def load(path):
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError) as failure:
            missing.append({'path': str(path), 'error': str(failure)})
            return None

    def same(before, after, label):
        nonlocal checks
        checks += 1
        if before != after:
            failures.append({'check': label, 'baseline': before, 'observed': after})

    def audits(directory):
        summary, cleanup = load(directory / 'summary.json'), load(directory / 'cleanup.json')
        request = load(directory / 'request.json')
        if summary is None or cleanup is None or request is None:
            return None
        same(cleanup.get('passed'), True, str(directory) + ':cleanup')
        same(int(request['num_inference_steps']), 50, str(directory) + ':50_steps')
        same(summary['diagnostic'], 'audit', str(directory) + ':audit_mode')
        if summary['repetitions'] < 2:
            missing.append({'path': str(directory), 'error': 'Two measured audit requests are required'})
        records = []
        for sample in range(summary['repetitions']):
            index = summary['warmup'] + sample
            path = directory / 'diagnostics' / f'request-{index:03d}'
            value = {'media': load(directory / f'sample-{sample}.media.json'), 'ranks': {}}
            for rank in range(4):
                folder = path / f'rank-{rank}'
                config = load(folder / 'configuration.json')
                if config is not None:
                    same(config.get('steps'), 50, str(folder) + ':steps')
                    same(config.get('cache_backend') in (None, 'none'), True, str(folder) + ':cache_backend')
                    same(config.get('kv_offload_config'), None, str(folder) + ':kv_config')
                    same(config.get('reference_kv_state_created'), False, str(folder) + ':actual_kv_state')
                tensors = {}
                for point in POINTS:
                    pair = load(folder / (point + '.json'))
                    if pair is None:
                        continue
                    tensors[point] = {}
                    for stream in ['video', 'audio']:
                        data = pair[stream]
                        same(data['dtype'], 'torch.float32', str(folder) + ':' + point + ':' + stream + ':dtype')
                        tensors[point][stream] = {k: data[k] for k in ['shape', 'dtype', 'bytes', 'sha256']}
                        if rank == 0:
                            payload = data.get('tensor_file')
                            if payload is None or not (folder / payload).exists():
                                missing.append({'path': str(folder), 'error': point + ':' + stream + ':raw tensor missing'})
                                continue
                            raw = (folder / payload).read_bytes()
                            same(len(raw), data['bytes'], str(folder) + ':' + point + ':raw_length')
                            same(hashlib.sha256(raw).hexdigest(), data['sha256'], str(folder) + ':' + point + ':raw_hash')
                            same(bool(np.isfinite(np.frombuffer(raw, dtype='<f4')).all()), True,
                                 str(folder) + ':' + point + ':' + stream + ':finite')
                semantic_config = ({key: config[key] for key in
                                    ['steps', 'sampler', 'sigmas_video_hex', 'sigmas_audio_hex']}
                                   if config is not None else None)
                value['ranks'][str(rank)] = {'configuration': semantic_config, 'tensors': tensors}
            records.append(value)
        for index, value in enumerate(records):
            for rank in range(1, 4):
                same(value['ranks']['0']['tensors'], value['ranks'][str(rank)]['tensors'],
                     str(directory) + f':sample-{index}:global_state_rank-{rank}')
        return {'request': request, 'summary': summary, 'records': records}

    baseline = audits(Path(args.baseline))
    candidate = audits(Path(args.candidate)) if args.candidate else None
    if baseline is not None and baseline['records']:
        reference = baseline['records'][0]
        sides = [('baseline-repeatability', baseline)]
        if candidate is not None:
            same(baseline['request'], candidate['request'], 'matched_request')
            sides.append(('candidate-equivalence', candidate))
        for label, side in sides:
            for index, value in enumerate(side['records']):
                for rank in range(4):
                    same(reference['ranks'][str(rank)], value['ranks'][str(rank)],
                         f'{label}:sample-{index}:rank-{rank}:latent_and_schedule_bits')
                if reference['media'] is not None and value['media'] is not None:
                    same({k: reference['media'][k] for k in MEDIA_KEYS},
                         {k: value['media'][k] for k in MEDIA_KEYS},
                         f'{label}:sample-{index}:decoded_pixels_and_pcm')
    verdict = 'INCONCLUSIVE' if missing else 'FAIL' if failures else 'PASS'
    result = {'verdict': verdict, 'scope': 'specified latent points, schedule, decoded RGB24/PCM; no performance acceptance',
              'comparison': 'candidate versus baseline' if args.candidate else 'baseline repeatability in one fresh service',
              'checks': checks, 'failures': failures, 'missing_evidence': missing,
              'quality_contract': 'strict bit-exact; no tolerance or human check'}
    Path(args.output).write_text(json.dumps(result, indent=2))
    print(json.dumps({'verdict': verdict, 'checks': checks, 'failures': len(failures),
                      'missing': len(missing)}), flush=True)
    raise SystemExit({'PASS': 0, 'FAIL': 1, 'INCONCLUSIVE': 2}[verdict])


if __name__ == '__main__':
    main()
