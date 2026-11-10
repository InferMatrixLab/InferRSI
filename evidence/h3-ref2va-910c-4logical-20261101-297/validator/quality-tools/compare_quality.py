"""Apply the prospective relative-quality gates; missing samples never pass."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline-index', required=True)
    parser.add_argument('--candidate-index', required=True)
    parser.add_argument('--contract', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    path = Path(args.contract)
    contract = json.loads(path.read_text())
    contract_hash = digest(path)
    assert digest(Path(__file__)) == contract['comparison_sha256']
    gates = contract['gates']
    failures, missing, observed, checks = [], [], {}, 0

    def check(condition, label):
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(label)

    def read_index(name):
        records = json.loads(Path(name).read_text())['scores']
        result = {item['sample_id']: Path(item['path']) for item in records}
        check(len(result) == len(records), name + ': unique sample IDs')
        return result

    baseline_index, candidate_index = read_index(args.baseline_index), read_index(args.candidate_index)
    for sample in contract['samples']:
        key = sample['id']
        if key not in baseline_index or key not in candidate_index:
            missing.append(key)
            continue
        left, right = baseline_index[key], candidate_index[key]
        baseline, candidate = json.loads(left.read_text()), json.loads(right.read_text())
        for label, record, score_path in [('baseline', baseline, left), ('candidate', candidate, right)]:
            check(record['sample_id'] == key, key + ':' + label + ': ID')
            check(record['contract_sha256'] == contract_hash, key + ':' + label + ': contract')
            check(record['cpu_only'], key + ':' + label + ': scorer backend')
            check(digest(score_path.parent / 'features.npz') == record['features_sha256'],
                  key + ':' + label + ': descriptor hash')
            check(record['media']['media_integrity'] == 'PASS', key + ':' + label + ': media')
        arrays = []
        for score_path in [left, right]:
            with np.load(score_path.parent / 'features.npz', allow_pickle=False) as data:
                arrays.append({name: data[name] for name in data.files})
        a, b = arrays
        for name in ['dino', 'clip', 'clap', 'audio_rms_envelope', 'motion']:
            check(a[name].shape == b[name].shape, key + ':' + name + ': shape')
            check(bool(np.isfinite(a[name]).all() and np.isfinite(b[name]).all()), key + ':' + name + ': finite')
        similarities = {}
        for name in ['dino', 'clip', 'clap']:
            cosine = np.sum(a[name] * b[name], axis=-1)
            similarities[name] = {'mean': float(cosine.mean()), 'min': float(cosine.min()),
                                  'p05': float(np.quantile(cosine, 0.05))}
            check(float(cosine.mean()) >= gates[name + '_paired_mean_cosine_min'], key + ':' + name + ': similarity')
        check(similarities['dino']['p05'] >= gates['dino_paired_p05_cosine_min'], key + ': dino lower tail')
        check(similarities['clap']['min'] >= gates['clap_paired_segment_cosine_min'], key + ': clap segment')
        for metric in ['reference_clip_cosine', 'reference_dino_cosine', 'prompt_clip_cosine',
                       'audio_caption_clap_cosine']:
            check(candidate[metric] >= baseline[metric] - gates['adherence_max_absolute_cosine_drop'],
                  key + ':' + metric + ': adherence')
        rms_db = 20 * np.log10(candidate['media']['audio_rms'] / baseline['media']['audio_rms'])
        check(abs(rms_db) <= gates['audio_rms_max_abs_db'], key + ': audio level')
        check(candidate['clipping_fraction'] <= baseline['clipping_fraction'] + gates['clipping_max_fraction_increase'],
              key + ': audio clipping')
        envelope_error = np.linalg.norm(b['audio_rms_envelope'] - a['audio_rms_envelope']) / \
            max(np.linalg.norm(a['audio_rms_envelope']), 1e-12)
        check(envelope_error <= gates['audio_envelope_relative_l2_max'], key + ': audio temporal envelope')
        motion_a, motion_b = float(a['motion'].mean()), float(b['motion'].mean())
        if motion_a < gates['motion_floor']:
            check(motion_b < 2 * gates['motion_floor'], key + ': near-static motion')
            motion_ratio = None
        else:
            motion_ratio = motion_b / motion_a
            check(gates['motion_ratio_min'] <= motion_ratio <= gates['motion_ratio_max'], key + ': motion energy')
        check(baseline['media']['audio_samples'] == candidate['media']['audio_samples'], key + ': audio coverage')
        check(abs(candidate['pts_start_difference_seconds']) <= 1 / 24, key + ': media timestamp alignment')
        reduced_a = float(np.mean(list(baseline['vbench'].values())))
        reduced_b = float(np.mean(list(candidate['vbench'].values())))
        check(reduced_a > 0, key + ': positive baseline score')
        error = abs(reduced_b - reduced_a) / max(abs(reduced_a), 1e-12)
        check(error < gates['per_clip_reduced_vbench_relative_error_max'], key + ': clip score')
        observed[key] = {'seconds': sample['request']['seconds'], 'baseline': baseline['vbench'],
                         'candidate': candidate['vbench'], 'cosines': similarities,
                         'reduced_relative_error': error, 'audio_rms_db': float(rms_db),
                         'audio_envelope_relative_l2': float(envelope_error), 'motion_ratio': motion_ratio}
    tracks = {}
    for duration in ['5', '15']:
        required = [item['id'] for item in contract['samples'] if item['request']['seconds'] == duration]
        available = [key for key in required if key in observed]
        if len(available) != len(required):
            tracks[duration] = {'verdict': 'INCONCLUSIVE', 'missing': list(set(required) - set(available))}
            continue
        values = {side: {dimension: float(np.mean([observed[key][side][dimension] for key in required]))
                         for dimension in ['subject_consistency', 'background_consistency']}
                  for side in ['baseline', 'candidate']}
        total = {side: float(np.mean(list(values[side].values()))) for side in values}
        relative_error = abs(total['candidate'] - total['baseline']) / abs(total['baseline'])
        check(relative_error < gates['reduced_vbench_relative_error_max'], duration + ': reduced VBench total')
        for dimension in values['baseline']:
            error = abs(values['candidate'][dimension] - values['baseline'][dimension]) / abs(values['baseline'][dimension])
            check(error < gates['dimension_relative_error_max'], duration + ':' + dimension)
        tracks[duration] = {'dimension_means': values, 'reduced_total': total, 'relative_error': relative_error}
    verdict = 'FAIL' if failures else 'INCONCLUSIVE' if missing else 'PASS'
    result = {'verdict': verdict, 'contract_sha256': contract_hash, 'checks': checks,
              'failures': failures, 'missing': missing, 'observed': observed, 'tracks': tracks,
              'scope': contract['scope'], 'performance_acceptance': 'separate'}
    Path(args.output).write_text(json.dumps(result, indent=2, allow_nan=False))
    print(json.dumps({'verdict': verdict, 'checks': checks, 'failures': failures, 'missing': missing}), flush=True)
    return {'PASS': 0, 'FAIL': 1, 'INCONCLUSIVE': 2}[verdict]


if __name__ == '__main__':
    raise SystemExit(main())
