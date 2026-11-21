# Mechanism check: per decode step, time spent building the lazy graph in Python vs the whole step.
# A compile candidate should cut graph-building time (fewer small ops) and GPU time (fused kernels).
# Usage: python mechanism.py <model-dir> [candidate.py]
import sys, time, importlib.util, statistics
import mlx.core as mx
from mlx_lm import load
from mlx_lm.models.cache import make_prompt_cache

model, tok = load(sys.argv[1]); cand = sys.argv[2] if len(sys.argv) > 2 else None
if cand:
    spec = importlib.util.spec_from_file_location("c", cand); m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m); m.apply(model)
ids = mx.array(tok.encode("def lru_cache(capacity):"))[None]
cache = make_prompt_cache(model); out = model(ids, cache=cache); mx.eval(out)
y = mx.argmax(out[:, -1:], -1)
build, total = [], []
for i in range(60):  # 60 steps; the first 10 are warm-up (the first includes compilation)
    t0 = time.perf_counter(); out = model(y, cache=cache); t1 = time.perf_counter()
    y = mx.argmax(out[:, -1:], -1); mx.eval(y); t2 = time.perf_counter()
    if i >= 10: build.append(t1 - t0); total.append(t2 - t0)
print(f"{'cand' if cand else 'base'} build_ms={statistics.median(build)*1e3:.2f} step_ms={statistics.median(total)*1e3:.2f}")
