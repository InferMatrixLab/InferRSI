"""Run the frozen coverage cases on an already reserved server; quality only."""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace



def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--plan-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base-url', default='http://127.0.0.1:19421')
    parser.add_argument('--quality', choices=('lossless', 'high', 'server-default'), required=True)
    parser.add_argument('--timeout', type=float, default=14400)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    plan_path = args.plan_dir / 'heldout-quality.json'
    plan = json.loads(plan_path.read_text())
    inputs = json.loads((args.plan_dir / 'inputs.json').read_text())
    originals = {item['name']: item['sha256'] for item in inputs['assets']}
    required = {
        args.assets / 'input_video.mp4': originals['input_video.mp4'],
        args.assets / 'input_audio.mp3': originals['input_audio.mp3'],
        args.assets / 'prompt.txt': inputs['prompt_sha256'],
    }
    family = next(case for case in plan['cases'] if case['id'] == 'family-seed0')
    required[args.assets / 'heldout-family/input_video.mp4'] = family['input_video_sha256']
    required[args.assets / 'heldout-family/prompt.txt'] = family['prompt_sha256']
    for path, expected in required.items():
        if digest(path) != expected:
            raise ValueError(f'Frozen input mismatch: {path.name}')
    metadata = {'scope': 'quality coverage only; do not pool these timings with performance cells',
                'plan_sha256': digest(plan_path), 'cases': [case['id'] for case in plan['cases']],
                'quality': args.quality, 'steps': plan['steps'], 'duration_s': plan['duration_s']}
    if args.validate_only:
        print(json.dumps(metadata, indent=2))
        return
    from run_client import request

    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'scope.json').write_text(json.dumps(metadata, indent=2) + '\n')
    for case in plan['cases']:
        prefix = args.assets / 'heldout-family' if case['id'] == 'family-seed0' else args.assets
        request_args = SimpleNamespace(base_url=args.base_url, prompt=prefix / 'prompt.txt',
            video=prefix / 'input_video.mp4', audio=args.assets / 'input_audio.mp3',
            output=args.output, steps=plan['steps'], quality=args.quality, timeout=args.timeout)
        record = request(request_args, 'heldout-' + case['id'], plan['duration_s'], case['seed'])
        if not record['valid']:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
