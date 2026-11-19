import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
summary = json.loads((root / 'results' / 'summary.json').read_text(encoding='utf-8'))
p = summary['performance']
assert abs(p['opus_50_step_recorded_speedup'] - 701.954369 / 166.172687) < 1e-12
vals = p['deepseek_seed_group_speedups']
assert abs(p['deepseek_10step_cachedit_recorded_speedup'] - sum(vals) / len(vals)) < 1e-12
print(json.dumps({'opus_speedup': p['opus_50_step_recorded_speedup'], 'deepseek_speedup': p['deepseek_10step_cachedit_recorded_speedup']}))
