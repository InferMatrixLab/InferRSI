# Usage: python bench_mlx.py <model-dir> --max-tokens N [--effort none] [--out result.json] [stream_generate key=value ...]
# Measures TTFT, prefill tok/s, decode tok/s and peak memory; the full output goes to <out>.txt
import argparse, json, time
import mlx.core as mx
from mlx_lm import load, stream_generate
from mlx_lm.sample_utils import make_sampler

PROMPT = ("用 Python 写一个线程安全的 LRU 缓存类，支持 get/put/容量上限和过期时间（TTL），"
          "附 3 个 pytest 用例。只输出代码。")

ap = argparse.ArgumentParser()
ap.add_argument("model")
ap.add_argument("--max-tokens", type=int, required=True)  # always given on the command line
ap.add_argument("--effort", default="none")  # a key of effort_map in the model's chat template
ap.add_argument("--out", default=None)
ap.add_argument("--runs", type=int, default=1)  # single run unless asked
ap.add_argument("--prompt", default=PROMPT)
ap.add_argument("kw", nargs="*")
a = ap.parse_args()
kw = {}
for s in a.kw:
    k, v = s.split("=", 1)
    kw[k] = int(v) if v.lstrip("-").isdigit() else v

t0 = time.time(); model, tok = load(a.model); load_s = time.time() - t0
msgs = [{"role": "user", "content": a.prompt}]
prompt = tok.apply_chat_template(msgs, add_generation_prompt=True, reasoning_effort=a.effort)
sampler = make_sampler(temp=0.0)  # greedy decoding: reproducible output, so changed results are detectable
res = []
for r in range(a.runs):
    mx.reset_peak_memory()
    t0 = time.time(); ttft = None; text = ""; last = None
    for resp in stream_generate(model, tok, prompt, max_tokens=a.max_tokens, sampler=sampler, **kw):
        if ttft is None: ttft = time.time() - t0
        text += resp.text; last = resp
    wall = time.time() - t0
    row = dict(run=r, load_s=load_s, ttft_s=ttft, prompt_tokens=last.prompt_tokens,
               prefill_tps=last.prompt_tps, gen_tokens=last.generation_tokens,
               decode_tps=last.generation_tps, peak_gb=mx.get_peak_memory() / 1e9,
               wall_s=wall, kw=kw)
    print(json.dumps(row, ensure_ascii=False), flush=True); res.append(row)
if a.out:
    json.dump(res, open(a.out, "w"), ensure_ascii=False, indent=1)
    open(a.out.rsplit(".", 1)[0] + ".txt", "w").write(text)
print("----- output -----\n" + text)
