import argparse
import asyncio
import json
from pathlib import Path
from bench.adapters import get_adapter
from bench.client import make_session
from bench.protocol import closed_loop, evaluate_run, save_run
from bench.workload import load_seed_tts_rows, make_id_sets, canonical_requests

async def main():
    p = argparse.ArgumentParser()
    p.add_argument('--adapter', required=True)
    p.add_argument('--url', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--concurrency', type=int, nargs='+', default=[1,2,4,8,16,32])
    p.add_argument('--requests', type=int, default=320)
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--eval-offset', type=int, default=0)
    p.add_argument('--id-set', choices=['eval', 'tuning'], default='eval')
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = load_seed_tts_rows()
    sets = make_id_sets(rows)
    adapter = get_adapter(a.adapter)
    # Exploratory steady-state baseline. No restart between cells; explicitly
    # distinct from the reference campaign's fresh-server certification.
    plan = vars(a) | {'cache_policy':'none', 'qualification':'exploratory', 'ids':sets.to_json()}
    (out/'plan.json').write_text(json.dumps(plan, indent=2))
    async with make_session() as session:
        for c in a.concurrency:
            warm = canonical_requests(rows, sets.warmup(c))
            traces = await closed_loop(session,a.url,adapter,warm,c,timeout_s=180)
            result = evaluate_run('warmup',c,traces,measured=False)
            save_run(result,out/f'c{c}'/'warmup')
            if any(not r.ok for r in result.per_request):
                raise RuntimeError(f'C{c} warmup failed; inspect saved traces')
            pool = sets.eval_pool if a.id_set == 'eval' else sets.tuning_pool
            pool = pool[a.eval_offset:]
            if a.eval_offset < 0 or a.requests > len(pool):
                raise ValueError('Requested count exceeds the selected disjoint pool')
            reqs=canonical_requests(rows, list(pool[:a.requests]))
            for k in range(a.repeats+1):
                traces=await closed_loop(session,a.url,adapter,reqs,c,timeout_s=180,record_raw=True)
                result=evaluate_run(f'run{k}',c,traces,measured=k>0)
                save_run(result,out/f'c{c}'/f'run{k}')
                print(json.dumps(result.summary()),flush=True)
                if any(not r.ok for r in result.per_request):
                    raise RuntimeError(f'C{c} run{k} failed; inspect saved traces')

asyncio.run(main())
