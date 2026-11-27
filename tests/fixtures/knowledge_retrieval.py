"""Synthetic retrieval/adoption campaign, generated locally without model execution.

Run: PYTHONPATH=src python tests/fixtures/knowledge_retrieval.py <output-directory>
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from inferrsi.apps.views.dashboard import write_dashboard
from inferrsi.apps.views.search_attribution import import_search
from inferrsi.apps.workflows.campaign import create_campaign
from inferrsi.harness.records.campaign_records import record_candidate
from inferrsi.harness.records.optimization_log import record_log
from inferrsi.knowledge import knowledge_find
from inferrsi.knowledge._source_snapshot import source_entry
from inferrsi.knowledge.knowledge_operations import KnowledgeReader, _hash, _json


@contextmanager
def reader(root):
    """Use an isolated on-disk installed library and its matching catalog snapshot."""
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
    for path, content in library.items():
        target = root / path.removeprefix("data/skill_library/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    for record in records.values():
        core = record["skill_documents"]["original"]
        record["source_files"] = {source_entry(p): _hash(library[p])
                                  for p in (core, registry_path)}
    result = KnowledgeReader()
    result._records = records
    result._library = library, "sha256:" + _hash(_json({p: _hash(b) for p, b in library.items()}))
    with patch.object(knowledge_find, "installed_skill_root", return_value=root.resolve()):
        yield result


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, indent=2).encode("utf-8"))


DEFAULT_RUNS = (
    ("repeat", "first", 1, "FAIL", -2, "failed"),
    ("repeat", "retry", 1, "INCONCLUSIVE", 0, "failed"),
    ("second", "no-gain", 2, "FAIL", 0, "failed"),
)


def legacy_records():
    """Receipts recorded before free-text collection retired, including the original bodies."""
    with gzip.open(Path(__file__).with_name("pre_find_read_captures.json.gz"), "rt",
                   encoding="utf-8") as source:
        return json.load(source)


def install_legacy_capture(root, sample, context_id, *, collection="samples", diagnosis=None,
                           ranking_policy=None):
    """Place a recorded response into the synthetic campaign used by an importer test."""
    doc = legacy_records()[collection][sample]
    doc["campaign_id"] = json.loads((root / "campaign.json").read_bytes())["campaign_id"]
    doc["context_id"] = context_id
    if diagnosis is not None:
        doc["diagnosis_binding"] = diagnosis
    if ranking_policy is not None:
        doc["request"]["ranking_policy"] = ranking_policy
    raw = (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path = root / "knowledge" / (context_id + ".json")
    path.parent.mkdir(exist_ok=True)
    with path.open("xb") as file:
        file.write(raw)
    return path, hashlib.sha256(raw).hexdigest()


def build(root, *, runs=DEFAULT_RUNS):
    root = Path(root)
    create_campaign(root, "synthetic-retrieval")
    manifest = json.loads((root / "campaign.json").read_text())
    write(root / "campaign.json", {**manifest, "synthetic": True})
    captures = {}
    with reader(root / "corpus"):
        for name in ("capture", "catalog", "collect", "explicit", "no-ranking", "empty", "legacy"):
            _, captures[name] = install_legacy_capture(root, name, name, collection="example")
    captured = json.loads((root / "knowledge/capture.json").read_bytes())
    for candidate, run, number, verdict, gain, quality in runs:
        directory = root / "runs" / run
        write(directory / "run.lock.json", {"workload_id": "synthetic", "scenario": "http"})
        write(directory / "status.json", {"state": "completed"})
        write(directory / "evaluation.json", {
            "verdict": verdict, "metric_key": "latency", "metric_unit": "s",
            "direction": "minimize", "improvement_pct": gain,
            "baseline": {"median": 10}, "candidate": {"median": 10 - gain / 10},
            "source_integrity": {"verified": True}})
        write(directory / "validation/execution.json", {
            "status": quality, "returncode": 0 if quality == "completed" else 1,
        })
        if run == "retry":
            original = json.loads((root / "candidates/repeat/candidate.json").read_text())
            write(root / "candidates/repeat-retry/candidate.json", {**original, "run_id": run})
        else:
            record_candidate(root, candidate_id=candidate, run_id=run, round_number=number,
                             title="Synthetic " + candidate,
                             details={"change_kind": "code", "summary": "Synthetic code change",
                                      "code_locations": [{"path": "src/synthetic.py",
                                                          "revision": "a" * 40}]})
    # Search records pin candidate bytes, so the synthetic inputs use LF on every host.
    for path in (root / "candidates").glob("*/candidate.json"):
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
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
    trace.write_bytes("".join(json.dumps(e) + "\n" for e in events).encode("utf-8"))
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
