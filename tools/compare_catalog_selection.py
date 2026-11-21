"""Replay retained Agent decisions against Find on a pinned baseline checkout.

This is an observational retrieval comparison, not an optimization benchmark or
an automated model selector. Write decisions after reviewing the entire catalog.
The output directory must be new; failed reads are retained.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from time import perf_counter

BASELINE_SCRIPT = r'''
import json, sys
from inferrsi.knowledge.knowledge_find import (
    Corpus, find, installed_skill_projection, installed_skill_root, load_documents,
)
from inferrsi.knowledge.knowledge_operations import KnowledgeReader
rows = json.load(sys.stdin)
reader = KnowledgeReader(skill_root=installed_skill_root())
documents = load_documents()
by_id = {d.identity: d for d in documents}
corpus = Corpus(documents)
results = []
for row in rows:
    found = find(row['query'], corpus, limit=5)
    refs = []
    for item in found['items']:
        doc = by_id[item['id']]
        projection = installed_skill_projection(doc, reader.record)
        refs.append('package:' + projection['id'] if projection else doc.qualified)
    revisions = {ref: reader.read(ref).revision for ref in refs}
    read = reader.collect(ids=refs, revisions=revisions, context_bytes=131072, limit=5)
    results.append({'id': row['id'], 'found': found, 'read': read})
json.dump(results, sys.stdout, ensure_ascii=False)
'''


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--baseline-results", type=Path, help="Reuse retained unchanged baseline")
    parser.add_argument("--selections", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must be new; preserve earlier attempts")
    rows = json.loads(args.selections.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True)
    baseline_env = {**os.environ, "PYTHONPATH": str(args.baseline.resolve() / "src")}
    if args.baseline_results:
        raw = args.baseline_results.read_bytes()
    else:
        raw = subprocess.check_output([sys.executable, "-c", BASELINE_SCRIPT],
                                      input=json.dumps(rows).encode(), env=baseline_env,
                                      cwd=args.baseline)
    baseline = json.loads(raw)
    write(args.output / "baseline.json", baseline)

    import tiktoken

    from inferrsi.apps.knowledge import prepare_catalog_selection
    from inferrsi.knowledge.catalog_selection import CatalogSelection

    encoding = tiktoken.get_encoding("o200k_base")
    catalog = CatalogSelection()
    results = []
    for row, old in zip(rows, baseline):
        started = perf_counter()
        prepared = prepare_catalog_selection(
            catalog, row["query"], conditions=row["conditions"], token_budget=128000,
            reserved_tokens=4096, token_counter=lambda s: len(encoding.encode(s)),
            tokenizer="tiktoken:o200k_base",
        )
        if prepared["status"] != "selection_required":
            raise ValueError(f"Catalog over budget for {row['id']}")
        if prepared["snapshot_id"] != row["snapshot_id"]:
            raise ValueError("Decisions are stale: refresh the full catalog and reselect")
        result = catalog.complete(
            row["snapshot_id"], row["selections"], conditions=row["conditions"],
            context_bytes=131072, expansion_depth=1, expansion_items=5, expansion_bytes=32768,
        )
        write(args.output / f"candidate-{len(results) + 1:02d}.json", result)
        refs = [c["ref"] for c in result["contexts"]]
        selected = [c["ref"] for c in row["selections"]]
        results.append({
            "id": row["id"], "query": row["query"], "snapshot_id": row["snapshot_id"],
            "baseline_ids": [i["id"] for i in old["found"]["items"]],
            "baseline_delivered": [c["ref"] for c in old["read"].get("contexts", [])],
            "baseline_omissions": old["read"].get("context_omissions", []),
            "candidate_selected": selected, "candidate_delivered": refs,
            "expansion_added_entries": [r for r in refs if r not in selected],
            "candidate_omissions": result["omissions"], "judgments": result["judgments"],
            "expansion_paths": result["retrieval"]["assembly"]["paths"],
            "accounting": prepared["accounting"],
            "interface_seconds": perf_counter() - started,
            "model_selection_seconds": None, "actual_model_usage": None,
            "selector": "retained current-Agent choices; no new model call during replay",
        })
        print(row["id"], len(selected), "selected,", len(refs), "delivered", flush=True)
    write(args.output / "comparison.json", results)
    manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in args.output.iterdir() if p.is_file()}
    write(args.output / "sha256.json", manifest)


if __name__ == "__main__":
    main()
