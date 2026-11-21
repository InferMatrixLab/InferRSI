# Count op nodes in one decode-step graph (total and non-view, the latter ~ GPU kernels); an optional candidate file is applied first.
import sys, collections, re, importlib.util
import mlx.core as mx
from mlx_lm import load
from mlx_lm.models.cache import make_prompt_cache
model, tok = load(sys.argv[1])
if len(sys.argv) > 2:
    spec = importlib.util.spec_from_file_location("c", sys.argv[2]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); m.apply(model)
ids = mx.array(tok.encode("def lru_cache(capacity):"))[None]
cache = make_prompt_cache(model); out = model(ids, cache=cache); mx.eval(out)
for _ in range(3):
    y = mx.argmax(out[:, -1:], -1); out = model(y, cache=cache); mx.eval(out)
out = model(y, cache=cache)
mx.export_to_dot("step.dot", out)
txt = open("step.dot").read()
ops = re.findall(r'label ="?([A-Za-z_]+)', txt)
VIEW = {"Broadcast","Transpose","Reshape","Squeeze","Flatten","Unflatten","ExpandDims","StopGradient","Slice","Split"}
c = collections.Counter(o if not o.startswith("Compiled") else "Compiled*" for o in ops)
print("total", sum(c.values()), "non-view", sum(v for k, v in c.items() if k not in VIEW)); print(c.most_common(30))
