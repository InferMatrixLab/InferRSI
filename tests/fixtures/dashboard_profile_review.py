"""Generate an offline profile-first review using only fabricated campaign records.

Usage: python tests/fixtures/dashboard_profile_review.py <new-output-directory>
"""

import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from dashboard_experiments import native_inputs
from knowledge_retrieval import build as build_retrievals
from knowledge_retrieval import write

from inferrsi.apps.views.dashboard import write_dashboard
from inferrsi.harness.records.profile_timeline import attach_profile


def build(root: Path):
    root = root.resolve()
    # Freeze the two recorded clocks before hashing the synthetic evidence.
    start = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    with (
        patch("inferrsi.__version__", "0+synthetic"),
        patch("inferrsi.apps.campaign.__version__", "0+synthetic"),
        patch("inferrsi.harness.records.knowledge_capture.datetime", wraps=datetime) as clock,
        patch("inferrsi.harness.records.optimization_log.datetime", wraps=datetime) as log_clock,
    ):
        clock.now.return_value = start
        log_clock.now.return_value = start
        build_retrievals(root, runs=(
            ("repeat", "first", 1, "FAIL", -2, "failed"),
            ("second", "no-gain", 2, "INCONCLUSIVE", 0, "completed"),
            ("batched-dispatch", "batch", 3, "PASS", 16, "completed"),
        ))
    # The projection includes each search file's digest. Normalize the fabricated
    # files before projecting them rather than rewriting hashes in the output.
    for path in (root / "search").rglob("*.json"):
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
    for run in (root / "runs").iterdir():
        native_inputs(run, "synthetic", "latency", "s", "minimize")
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
    output = write_dashboard(root)
    output.write_bytes(output.read_bytes().replace(b"\r\n", b"\n"))
    return output


if __name__ == "__main__":
    print(build(Path(sys.argv[1])))
