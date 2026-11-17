"""Generate an offline profile-first review using only fabricated campaign records.

Usage: python tests/fixtures/dashboard_profile_review.py <new-output-directory>
"""

import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dashboard_experiments import native_inputs
from knowledge_retrieval import build as build_retrievals
from knowledge_retrieval import write

from inferrsi.apps.views.dashboard import write_dashboard
from inferrsi.harness.records.profile_timeline import attach_profile


def build(root: Path):
    root = root.resolve()
    # One measurement per round supports a paired-baseline trend.
    build_retrievals(root, runs=(
        ("repeat", "first", 1, "FAIL", -2, "failed"),
        ("second", "no-gain", 2, "INCONCLUSIVE", 0, "completed"),
        ("batched-dispatch", "batch", 3, "PASS", 16, "completed"),
    ))
    for run in (root / "runs").iterdir():
        native_inputs(run, "synthetic", "latency", "s", "minimize")
    # Tie the mock execution clock to the saved fixture retrievals so the
    # pre-profile link follows the same chronology on every regeneration.
    captures = [json.loads(path.read_bytes()) for path in (root / "knowledge").glob("*.json")]
    start = max(datetime.fromisoformat(item["captured_at"]) for item in captures)
    steps = []
    for phase, offset, projection_us in (("baseline", 1, 6200), ("candidate", 22, 5700)):
        at = start + timedelta(seconds=offset)
        title = f"Synthetic {phase} dispatch"
        number = 3 if phase == "candidate" else None
        spans = [
            ("user_annotation", "Dispatch", 0, 9200, 1),
            ("cpu_op", "Queue submission", 200, 750, 1),
            ("kernel", "Projection", 1000, projection_us, 2),
            ("kernel", "Normalize", 7450, 1100, 2),
        ]
        source = f"profiles/{phase}.json"
        write(root / source, {"traceEvents": [
            {"ph": "X", "cat": category, "name": name, "ts": ts, "dur": duration,
             "pid": 1, "tid": thread} for category, name, ts, duration, thread in spans
        ]})
        review = root / f"{phase}-review.json"
        write(review, {
            "title": title, "phase": phase, "round": number, "workload_id": "synthetic",
            "comparison_key": "synthetic-dispatch", "started_at": at.isoformat(),
            "context_ids": ["capture"], "takeaway": "Projection is the longest kernel.",
            "next_action": "Inspect the gap before normalization.",
        })
        attach_profile(root, capture_id=phase, source=source, review=review)
        steps.append({
            "kind": "profile_request", "label": title, "basis": "Synthetic fixture clock",
            "actor": "synthetic-worker", "round": number, "start": at.isoformat(),
            "end": (at + timedelta(microseconds=9200)).isoformat(),
        })
    manifest = root / "campaign.json"
    campaign = json.loads(manifest.read_bytes())
    timing = root / "experiment-timing.json"
    write(timing, {"schema_version": 1, "campaign_id": campaign["campaign_id"], "steps": steps})
    write(manifest, {**campaign, "review_layout": "profile_first",
                     "experiment_timing_sha256": hashlib.sha256(timing.read_bytes()).hexdigest()})
    return write_dashboard(root)


if __name__ == "__main__":
    print(build(Path(sys.argv[1])))
