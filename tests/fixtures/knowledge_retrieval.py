"""Synthetic retrieval/adoption campaign, generated locally without model execution.

Run: PYTHONPATH=src python tests/fixtures/knowledge_retrieval.py <output-directory>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

from inferrsi.apps.campaign import capture_context, create_campaign, save_retrieval
from inferrsi.apps.views.dashboard import write_dashboard
from inferrsi.apps.views.search_attribution import import_search
from inferrsi.harness.records.campaign_records import record_candidate
from inferrsi.harness.records.optimization_log import record_log
from inferrsi.knowledge.catalog import search_knowledge
from inferrsi.knowledge.knowledge_operations import KnowledgeReader, _hash, _json


def reader():
    registry_path = "data/skill_library/skill-index.json"
    registry, library, records = {"schema_version": 1, "skills": {}}, {}, {}
    for name in ("a", "b", "c", "d", "e"):
        path = "methods/synthetic-" + name
        core = "data/skill_library/" + path + "/SKILL.md"
        registry["skills"]["synthetic-" + name] = {"path": path, "backend": "common"}
        library[core] = b"Synthetic launch guidance.\n"
        identity = "inferrsi.common.skills.synthetic_" + name
        records[identity] = {
            "id": identity, "title": "Synthetic launch", "summary": "Synthetic launch example",
            "tags": [], "applicability": {}, "sources": [{"type": "internal",
                "issue": "synthetic", "artifact": "fixture"}],
            "status": "candidate", "verification": "synthetic-only", "repo": "inferrsi",
            "backend": "common", "scenario": "skills.discovery", "tier": "contribution",
            "index_type": "packaged-skill", "skill_documents": {"original": core},
            "skill_metadata": {"name": "synthetic-" + name, "references": []},
        }
    library[registry_path] = _json(registry)
    for record in records.values():
        core = record["skill_documents"]["original"]
        record["source_files"] = {"src/inferrsi/" + p: _hash(library[p])
                                  for p in (core, registry_path)}
    result = KnowledgeReader()
    result._records = records
    result._library = library, "sha256:" + _hash(_json({p: _hash(b) for p, b in library.items()}))
    return result


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def build(root):
    root = Path(root)
    create_campaign(root, "synthetic-retrieval")
    manifest = json.loads((root / "campaign.json").read_text())
    write(root / "campaign.json", {**manifest, "synthetic": True})
    source = reader()
    budget = 2 * len(b"Synthetic launch guidance.\n")
    captures = {}
    path, captures["capture"] = capture_context(root, context_id="capture", reader=source,
                                               relevance="launch", context_bytes=budget)
    captured = json.loads(path.read_text())
    with patch("inferrsi.knowledge.catalog.knowledge_records",
               return_value=list(source.records().values())):
        _, captures["catalog"] = save_retrieval(root, context_id="catalog",
                                               result=search_knowledge("launch", explain=True))
    for name, options in {
        "collect": {"relevance": "launch", "context_bytes": budget},
        "explicit": {"ids": list(reversed(source.records())), "relevance": "launch"},
        "no-ranking": {}, "empty": {"query": "no-such-term"},
        "legacy": {"relevance": "launch"},
    }.items():
        result = source.collect(**options)
        if name == "legacy":
            result.pop("retrieval")
        _, captures[name] = save_retrieval(root, context_id=name, result=result)
    for candidate, run, number, verdict, gain in (
        ("repeat", "first", 1, "FAIL", -2),
        ("repeat", "retry", 1, "INCONCLUSIVE", 0),
        ("second", "no-gain", 2, "FAIL", 0),
    ):
        directory = root / "runs" / run
        write(directory / "run.lock.json", {"workload_id": "synthetic", "scenario": "http"})
        write(directory / "status.json", {"state": "completed"})
        write(directory / "evaluation.json", {
            "verdict": verdict, "metric_key": "latency", "metric_unit": "s",
            "direction": "minimize", "improvement_pct": gain,
            "baseline": {"median": 10}, "candidate": {"median": 10 - gain / 10},
            "source_integrity": {"verified": True}})
        write(directory / "validation/execution.json", {"status": "failed", "returncode": 1})
        if run == "retry":
            original = json.loads((root / "candidates/repeat/candidate.json").read_text())
            write(root / "candidates/repeat-retry/candidate.json", {**original, "run_id": run})
        else:
            record_candidate(root, candidate_id=candidate, run_id=run, round_number=number,
                             title="Synthetic " + candidate,
                             details={"change_kind": "code", "summary": "Synthetic code change",
                                      "code_locations": [{"path": "src/synthetic.py",
                                                          "revision": "a" * 40}]})
    first_ref = captured["items"][0]["ref"]
    log = {
        "schema_version": 2, "reviewed_by_caller": True, "campaign_id": "synthetic-retrieval",
        "goal": {"statement": "Synthetic retrieval review", "metric": "latency"},
        "knowledge": [{"context_id": name, "sha256": digest, "stage": "knowledge",
                       "purpose": "Synthetic fixture", "takeaways": [],
                       "used_refs": [captured["items"][-1]["ref"]] if name == "capture" else [],
                       "rejected_refs": []} for name, digest in captures.items()],
        "search_space": {"state": "partial", "missing_reason": "Synthetic example",
                         "dimensions": []},
        "iterations": [{"round": n, "hypothesis": "Synthetic hypothesis", "rationale": "Fixture",
                        "knowledge_refs": [], "context_ids": ids,
                        "candidates": [{"candidate_id": cid, "option_ids": [], "why": "Fixture"}],
                        "decision": {"outcome": "pending", "reason": "Synthetic example"}}
                       for n, cid, ids in ((1, "repeat", ["capture", "catalog"]),
                                           (2, "second", list(captures)[2:]))],
        "summary": {"state": "partial", "missing_reason": "Synthetic only", "successes": [],
                    "failures": [], "lessons": [], "limitations": ["No causal attribution"]},
    }
    write(root / "review-input.json", log)
    record_log(root, root / "review-input.json")
    trace = root / "synthetic-trace.jsonl"
    events = [{"type": "session_meta", "payload": {"id": "synthetic-session"}},
              {"type": "response_item", "payload": {"type": "function_call_output",
               "call_id": "synthetic", "output": captured["assembled_text"]}},
              {"type": "response_item", "payload": {"type": "message", "role": "assistant",
               "phase": "final_answer",
               "content": [{"type": "output_text", "text": "Use synthetic launch guidance."}]}}]
    trace.write_text("".join(json.dumps(e) + "\n" for e in events))
    review = root / "archive-review.json"
    write(review, {"task": "Synthetic review", "corpus": {
        "repository": "example/synthetic", "revision": "a" * 40, "root": "."},
        "capture_returns": {"capture": 2}, "decisions": [{
            "use": "used", "ref": first_ref, "event_line": 2, "passage_line": 1,
            "passage_path": captured["contexts"][0]["resources"][0]["path"],
            "decision_line": 3, "decision_quote": "Use synthetic launch guidance."}]})
    import_search(root, number=1, context_ids=["capture", "catalog"], trace=trace,
                  lines=[2, 3], knowledge_root=root / "corpus", complete=True,
                  archive_review=review)
    import_search(root, number=2, context_ids=list(captures)[2:])
    import_search(root, number=3)
    # Local traces identify a private input. The offline artifact does not include that path.
    write_dashboard(root)
    return root


if __name__ == "__main__":
    build(Path(sys.argv[1]))
