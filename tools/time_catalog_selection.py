"""Time Find and two catalog implementations using retained Agent selections.

Each sample uses a fresh interpreter. Model selection, imports, tokenizer startup
and output serialization are outside the interface timing boundary. This is a CPU
retrieval measurement, not an inference optimization or model-quality benchmark.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
from pathlib import Path

WORKER = r'''
import hashlib, json, sys
from time import perf_counter
request = json.load(sys.stdin)
row = request['row']
accounting = None
if request['method'] == 'find':
    from inferrsi.knowledge.knowledge_find import (
        Corpus, find, installed_skill_projection, installed_skill_root, load_documents,
    )
    from inferrsi.knowledge.knowledge_operations import KnowledgeReader
    start = perf_counter()
    reader = KnowledgeReader(skill_root=installed_skill_root())
    documents = load_documents()
    by_id = {d.identity: d for d in documents}
    corpus = Corpus(documents)
    ready = perf_counter()
    found = find(row['query'], corpus, limit=5)
    ranked = perf_counter()
    refs = []
    for item in found['items']:
        doc = by_id[item['id']]
        projection = installed_skill_projection(doc, reader.record)
        refs.append('package:' + projection['id'] if projection else doc.qualified)
    revisions = {ref: reader.read(ref).revision for ref in refs}
    result = reader.collect(ids=refs, revisions=revisions, context_bytes=131072, limit=5)
    end = perf_counter()
    phases = {'corpus': ready-start, 'find': ranked-ready, 'read': end-ranked}
    chosen = [item['id'] for item in found['items']]
else:
    import tiktoken
    from inferrsi.apps.knowledge import prepare_catalog_selection
    from inferrsi.knowledge.catalog_selection import CatalogSelection
    encoding = tiktoken.get_encoding('o200k_base')
    start = perf_counter()
    catalog = CatalogSelection()
    prepared = prepare_catalog_selection(
        catalog, row['query'], conditions=row['conditions'], token_budget=128000,
        reserved_tokens=4096, token_counter=lambda s: len(encoding.encode(s)),
        tokenizer='tiktoken:o200k_base',
    )
    ready = perf_counter()
    if prepared['status'] != 'selection_required':
        raise RuntimeError('Unexpected budget fallback')
    if prepared['snapshot_id'] != row['snapshot_id']:
        raise RuntimeError('Source snapshot changed; refresh selections')
    result = catalog.complete(
        row['snapshot_id'], row['selections'], conditions=row['conditions'],
        context_bytes=131072, expansion_depth=1, expansion_items=5, expansion_bytes=32768,
    )
    end = perf_counter()
    phases = {'prepare': ready-start, 'complete': end-ready}
    chosen = [item['ref'] for item in row['selections']]
    accounting = prepared['accounting']
semantics = {
    'snapshot_id': result.get('snapshot_id'), 'chosen': chosen,
    'contexts': result.get('contexts', []), 'judgments': result.get('judgments', []),
    'omissions': result.get('omissions', []) + result.get('context_omissions', []),
    'paths': result.get('retrieval', {}).get('assembly', {}).get('paths', []),
}
fingerprint = hashlib.sha256(json.dumps(
    semantics, sort_keys=True, ensure_ascii=False, separators=(',', ':')
).encode()).hexdigest()
json.dump({
    'seconds': end-start, 'phase_seconds': phases, 'chosen': chosen,
    'delivered': [c['ref'] for c in semantics['contexts']],
    'omissions': semantics['omissions'], 'semantic_sha256': fingerprint,
    'snapshot_id': semantics['snapshot_id'], 'accounting': accounting,
    'external_calls': 0, 'model_calls_during_replay': 0,
}, sys.stdout, ensure_ascii=False)
'''


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True, help="Original Find checkout")
    parser.add_argument("--before", type=Path, required=True, help="Catalog before optimization")
    parser.add_argument("--after", type=Path, required=True, help="Catalog after optimization")
    parser.add_argument("--selections", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("repetitions must be positive")
    roots = {name: getattr(args, name).resolve() for name in ("baseline", "before", "after")}
    revisions = {}
    for name, root in roots.items():
        if subprocess.check_output(["git", "status", "--porcelain"], cwd=root).strip():
            parser.error(f"{name} must be a clean, pinned checkout")
        revisions[name] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()
    rows = json.loads(args.selections.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=False)
    write(args.output / "selections.json", rows)
    write(args.output / "protocol.json", {
        "revisions": revisions, "queries": len(rows), "repetitions": args.repetitions,
        "python": platform.python_version(), "architecture": platform.machine(),
        "order": "odd baseline/before/after; even after/before/baseline",
        "boundary": "fresh reader/corpus/catalog through source delivery; excludes imports, "
                    "tokenizer startup, process startup, serialization and Agent decisions",
        "cache": "fresh interpreter per arm/sample; OS page cache uncontrolled",
        "selection": "replay retained Agent choices; no model calls or new decisions",
        "external_channels": "no registry attached; no cann-bot or external calls",
        "context_bytes": 131072, "expansion_depth": 1, "expansion_items": 5,
        "expansion_bytes": 32768, "token_budget": 128000, "reserved_tokens": 4096,
        "tokenizer": "tiktoken:o200k_base", "task_benefit": "INCONCLUSIVE",
        "worker_sha256": hashlib.sha256(WORKER.encode()).hexdigest(),
    })
    (args.output / "worker.py").write_text(WORKER, encoding="utf-8")
    summaries = []
    for index, row in enumerate(rows, 1):
        samples = {name: [] for name in roots}
        for repeat in range(1, args.repetitions + 1):
            order = list(roots) if repeat % 2 else list(reversed(roots))
            for name in order:
                run = subprocess.run(
                    [sys.executable, str((args.output / "worker.py").resolve())],
                    cwd=roots[name], env={**os.environ, "PYTHONPATH": str(roots[name] / "src")},
                    input=json.dumps({"row": row, "method": "find" if name == "baseline"
                                      else "catalog"}), capture_output=True, text=True, timeout=120,
                )
                stem = f"{index:02d}-{repeat:02d}-{name}"
                if run.returncode:
                    (args.output / f"{stem}-error.log").write_text(run.stderr, encoding="utf-8")
                    raise RuntimeError(f"{stem} failed; retained stderr")
                sample = json.loads(run.stdout)
                write(args.output / f"{stem}.json", sample)
                if (samples[name]
                        and sample["semantic_sha256"] != samples[name][0]["semantic_sha256"]):
                    raise RuntimeError(f"{stem}: result changed between repetitions")
                samples[name].append(sample)
                print(f"{row['id']} {repeat} {name}: {sample['seconds']:.4f}s", flush=True)
            if samples["before"][-1]["semantic_sha256"] != samples["after"][-1]["semantic_sha256"]:
                raise RuntimeError("Optimization changed cards, resource bytes or result semantics")
        summary = {"id": row["id"], "query": row["query"], "semantics_equal": True, "arms": {}}
        for name, values in samples.items():
            times = [value["seconds"] for value in values]
            summary["arms"][name] = {
                "seconds": times, "mean_seconds": statistics.mean(times),
                "median_seconds": statistics.median(times), "min_seconds": min(times),
                "max_seconds": max(times), "chosen": values[0]["chosen"],
                "delivered": values[0]["delivered"], "omissions": values[0]["omissions"],
                "semantic_sha256": values[0]["semantic_sha256"],
                "phase_mean_seconds": {
                    key: statistics.mean(v["phase_seconds"][key] for v in values)
                    for key in values[0]["phase_seconds"]
                },
            }
        summaries.append(summary)
        write(args.output / "summary.json", summaries)
    write(args.output / "sha256.json", {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in args.output.iterdir() if path.is_file()
    })


if __name__ == "__main__":
    main()
