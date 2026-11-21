# One InferRSI-style round on a Mac: load the model once, alternate each candidate with the default path, score by measured decode speed.
# Usage: python rsi_mlx.py <model-dir> <round-dir> --split evolve|holdout --max-tokens N --reps R
#   Each <round-dir>/cands/*.py (not starting with "_") is a candidate defining apply(model) -> dict of stream_generate kwargs;
#   it may patch the model in place (swap ops, wrap mx.compile) and must define revert(model).
# Score: median paired ratio candidate/adjacent-default decode tok/s. Gate: greedy token ids identical to the default path
# (same length and same ids on every prompt).
# Noise: range of the default path's own runs. Below 5% difference: no conclusion.
# A candidate with an error, fewer than --reps pairs, or a failed revert is INCONCLUSIVE; its error and samples are kept.
# A speed win is only a screen: "speed screen passed, pending mechanism check". The mechanism gate
# (mechanism.py, count_ops2.py) is checked separately and is not read by this script.
import argparse, glob, importlib.util, json, os, statistics, time

# Code-generation workload. Split validation, as in earlier InferRSI campaigns:
# candidates are selected on "evolve"; the reported number is the "holdout" split.
SPLITS = {
    "evolve": [
        "用 Python 写一个线程安全的 LRU 缓存类，支持 get/put/容量上限和过期时间（TTL），附 3 个 pytest 用例。只输出代码。",
        "Write a Go HTTP server with a /healthz endpoint and a rate-limited /api/echo endpoint using a token bucket. Code only.",
    ],
    "holdout": [
        "用 TypeScript 写一个带重试和指数退避的 fetch 封装，支持超时取消，附用法示例。只输出代码。",
        "Write a Rust function that parses a CSV line with quoted fields and escaped quotes, with unit tests. Code only.",
    ],
}

def same_ids(run, ref_ids):
    """Quality gate: every prompt's token ids equal the default path's, including length."""
    return len(run) == len(ref_ids) and all(x["ids"] == ref for x, ref in zip(run, ref_ids))


def summary(runs):
    dec = [statistics.mean(x["dec"] for x in r) for r in runs]
    ttft = [statistics.mean(x["ttft"] for x in r) for r in runs]
    return dict(dec_med=statistics.median(dec), dec_all=dec, ttft_med=statistics.median(ttft),
                peak=max(x["peak"] for r in runs for x in r))


def pair_candidate(mod, model, run_once, base_runs, ref_ids, reps):
    """Alternate the default path with the candidate `reps` times. Keeps every sample and the error, if any."""
    runs = []; pairs = []; same = True; err = None; reverted = True
    try:
        for i in range(reps):
            base_runs.append(run_once({}))           # default path, alternated with the candidate
            kw = mod.apply(model); reverted = False
            r = run_once(kw); runs.append(r)
            pairs.append(summary([r])["dec_med"] / summary([base_runs[-1]])["dec_med"])  # paired with the adjacent default run, cancelling thermal drift
            mod.revert(model); reverted = True
            same = same and same_ids(r, ref_ids)
    except Exception as e:
        err = repr(e)
        if not reverted:
            try:
                mod.revert(model); reverted = True
            except Exception as e2:
                err += f"; revert failed: {e2!r}"
    s = summary(runs) if runs else {}
    return dict(s, paired=pairs, same_output=same, err=err, reverted=reverted, doc=(mod.__doc__ or "").strip())


def score(r, reps):
    """Verdict for one candidate. Only complete, error-free, reverted runs that pass the token gate are scored."""
    if r["err"] or not r["reverted"] or len(r["paired"]) != reps:
        return dict(verdict="INCONCLUSIVE")
    speedup = statistics.median(r["paired"])
    if not r["same_output"]:
        return dict(speedup=speedup, verdict="output changed: rejected")
    if abs(speedup - 1) < 0.05:
        return dict(speedup=speedup, verdict="<5%: no conclusion")
    return dict(speedup=speedup, verdict="speed screen passed, pending mechanism check" if speedup > 1 else "reject")


def main():
    import mlx.core as mx
    from mlx_lm import load, stream_generate
    from mlx_lm.sample_utils import make_sampler

    ap = argparse.ArgumentParser()
    ap.add_argument("model"); ap.add_argument("round_dir")
    ap.add_argument("--max-tokens", type=int, required=True)
    ap.add_argument("--reps", type=int, required=True)
    ap.add_argument("--only", default=None)
    ap.add_argument("--split", choices=list(SPLITS), required=True)
    a = ap.parse_args()

    model, tok = load(a.model)
    sampler = make_sampler(temp=0.0)
    prompts = [tok.apply_chat_template([{"role": "user", "content": p}], add_generation_prompt=True,
                                       reasoning_effort="none") for p in SPLITS[a.split]]

    def run_once(kw):
        out = []
        for p in prompts:
            mx.reset_peak_memory(); t0 = time.time(); ttft = None; ids = []; last = None
            for r in stream_generate(model, tok, p, max_tokens=a.max_tokens, sampler=sampler, **kw):
                if ttft is None: ttft = time.time() - t0
                ids.append(r.token); last = r
            out.append(dict(ttft=ttft, dec=last.generation_tps, pre=last.prompt_tps, n=last.generation_tokens,
                            peak=mx.get_peak_memory() / 1e9, ids=ids))
        return out

    log = open(os.path.join(a.round_dir, f"log-{a.split}.jsonl"), "a")
    def emit(d):
        print(json.dumps(d, ensure_ascii=False), flush=True); log.write(json.dumps(d, ensure_ascii=False) + "\n"); log.flush()

    run_once({})  # warm-up: the first pass compiles Metal kernels; not scored
    base_runs = [run_once({})]
    ref_ids = [x["ids"] for x in base_runs[0]]
    results = {}
    cands = sorted(p for p in glob.glob(os.path.join(a.round_dir, "cands", "*.py")) if not os.path.basename(p).startswith("_"))
    if a.only: cands = [c for c in cands if a.only in c]
    for path in cands:
        name = os.path.basename(path)[:-3]
        spec = importlib.util.spec_from_file_location(name, path); mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        results[name] = pair_candidate(mod, model, run_once, base_runs, ref_ids, a.reps)
        emit(dict(cand=name, **results[name]))

    b = summary(base_runs)
    noise = (max(b["dec_all"]) - min(b["dec_all"])) / b["dec_med"]
    emit(dict(cand="baseline", **b, noise_range=noise))
    for n, r in results.items():
        r.update(score(r, a.reps))
    json.dump(dict(baseline=b, noise_range=noise, cands=results), open(os.path.join(a.round_dir, f"score-{a.split}.json"), "w"),
              ensure_ascii=False, indent=1)
    for n, r in sorted(results.items(), key=lambda kv: -kv[1].get("dec_med", 0)):
        print(f"{n:24s} {r.get('dec_med', 0):7.2f} tok/s  x{r.get('speedup', 0):.3f}  same_output={r['same_output']}  {r.get('verdict')}  {r['err'] or ''}")
    print(f"baseline {b['dec_med']:.2f} tok/s  noise range {noise:.1%}")


if __name__ == "__main__":
    main()
