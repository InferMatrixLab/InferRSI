import argparse
import asyncio
import json
from pathlib import Path

from bench.adapters import get_adapter
from bench.client import make_session
from bench.protocol import closed_loop, evaluate_run, save_run
from bench.workload import canonical_requests, load_seed_tts_rows, make_id_sets


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--adapter", required=True)
    p.add_argument("--url", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--concurrency", type=int, nargs="+", default=[1, 16, 32])
    p.add_argument("--requests", type=int, default=256)
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--plan", type=Path, required=True)

    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    rows = load_seed_tts_rows()
    sets = make_id_sets(rows)
    frozen = json.loads(a.plan.read_text())
    ids = frozen["quality_holdout_ids"]
    if len(ids) != 256 or len(set(ids)) != 256 or list(sets.tuning_pool[128:384]) != ids:
        raise ValueError("Holdout IDs differ from the frozen unused cohort")
    if a.requests != 256 or set(a.concurrency) != {1, 16, 32}:
        raise ValueError("Quality qualification requires 256 prompts at C1/C16/C32")
    adapter = get_adapter(a.adapter)
    # Exploratory steady-state baseline. No restart between cells; explicitly
    # distinct from the reference campaign's fresh-server certification.
    plan = (vars(a) | {"plan": str(a.plan)}) | {
        "cache_policy": "none",
        "qualification": "exploratory",
        "ids": sets.to_json(),
    }
    (out / "plan.json").write_text(json.dumps(plan, indent=2))
    async with make_session() as session:
        for c in a.concurrency:
            warm = canonical_requests(rows, sets.warmup(c))
            traces = await closed_loop(session, a.url, adapter, warm, c, timeout_s=180)
            result = evaluate_run("warmup", c, traces, measured=False)
            save_run(result, out / f"c{c}" / "warmup")
            if any(not r.ok for r in result.per_request):
                raise RuntimeError(f"C{c} warmup failed; inspect saved traces")
            reqs = canonical_requests(rows, ids)
            for k in range(a.repeats + 1):
                traces = await closed_loop(
                    session, a.url, adapter, reqs, c, timeout_s=180, record_raw=True
                )
                result = evaluate_run(f"run{k}", c, traces, measured=k > 0)
                save_run(result, out / f"c{c}" / f"run{k}")
                print(json.dumps(result.summary()), flush=True)
                if any(not r.ok for r in result.per_request):
                    raise RuntimeError(f"C{c} run{k} failed; inspect saved traces")


asyncio.run(main())
