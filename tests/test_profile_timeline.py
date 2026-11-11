import gzip
import hashlib
import json
import threading
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from inferrsi.observability.dashboard import dashboard_snapshot
from inferrsi.observability.dashboard_live import DashboardServer
from inferrsi.observability.profile_timeline import attach_profile, read_profiles


def event(cat, name, ts, dur):
    return {"ph": "X", "cat": cat, "name": name, "pid": 0, "tid": 1,
            "ts": ts, "dur": dur, "args": {"path": "/private/weights", "shape": [8, 4]}}


def fixture(root):
    (root / "campaign.json").write_text('{"campaign_id":"sample","review_layout":"profile_first"}')
    (root / "profiles").mkdir()
    meta = {"title": "Warm worker", "phase": "baseline", "round": None,
            "workload_id": "image", "comparison_key": "same-card-input-scope",
            "takeaway": "Time spent in the denoiser.", "next_action": "Compare dispatch."}
    review = root / "review.json"
    review.write_text(json.dumps(meta))
    # Cross a decoder chunk boundary and include non-duration events.
    events = [{"ph": "M", "name": "thread_name"},
              event("user_annotation", "worker", 10, 120), event("cpu_op", "launch", 11, 3)]
    events += [event("kernel", "projection", 20 + i, 0.8) for i in range(100)]
    body = json.dumps({"padding": "x" * 66000, "traceEvents": events, "end": 1}).encode()
    source = root / "profiles/baseline.json.gz"
    source.write_bytes(gzip.compress(body))
    return source, review


def test_complete_span_bins_and_full_table_survive_overview_sampling(tmp_path):
    source, review = fixture(tmp_path)
    attach_profile(tmp_path, capture_id="baseline", source="profiles/baseline.json.gz",
                   review=review)
    data = dashboard_snapshot(tmp_path)["data"]
    capture, = data["profile_captures"]
    assert not data["unavailable_profiles"]
    assert capture["start_us"] == 10 and capture["duration_us"] == 120
    assert capture["event_count"] == 102 and capture["displayed_event_count"] == 82
    gpu, = [t for t in capture["tracks"] if t["kind"] == "gpu"]
    assert len(gpu["bins"]) == 256 and max(gpu["bins"]) > 0
    ref = capture["source"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == ref["sha256"]
    raw = (tmp_path / ref["events_path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == ref["events_sha256"]
    full = json.loads(gzip.decompress(raw))
    assert len(full["events"]) == capture["event_count"]
    assert full["events"][-1][2:] == [119, 0.8]
    assert "/private" not in json.dumps(full) + json.dumps(capture)
    with pytest.raises(ValueError):
        attach_profile(tmp_path, capture_id="baseline", source="profiles/baseline.json.gz",
                       review=review)


def test_only_verified_local_projection_served_and_modified_raw_is_withheld(tmp_path):
    source, review = fixture(tmp_path)
    attach_profile(tmp_path, capture_id="baseline", source="profiles/baseline.json.gz",
                   review=review)
    cap = read_profiles(tmp_path)[0][0]
    with DashboardServer(tmp_path, None, 0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(base + cap["source"]["events_url"]) as result:
                assert result.getheader("Content-Encoding") == "gzip"
                assert len(json.loads(gzip.decompress(result.read()))["events"]) == 102
            for url in ("/profiles/baseline.json.gz", "/api/profile-events/" + "0" * 64):
                with pytest.raises(HTTPError) as exc:
                    urlopen(base + url)
                assert exc.value.code == 404
            source.write_bytes(b"changed")
            assert read_profiles(tmp_path) == ([], ["baseline"])
            with pytest.raises(HTTPError) as exc:
                urlopen(base + cap["source"]["events_url"])
            assert exc.value.code == 404
        finally:
            server.shutdown()
            thread.join()


def test_unsupported_capture_is_not_attached(tmp_path):
    source, review = fixture(tmp_path)
    source.write_bytes(gzip.compress(b'{"traceEvents":[{"ph":"B"}]}'))
    with pytest.raises(ValueError, match="no complete"):
        attach_profile(tmp_path, capture_id="b", source="profiles/baseline.json.gz", review=review)
    assert not (tmp_path / "profile-captures.jsonl").exists()
