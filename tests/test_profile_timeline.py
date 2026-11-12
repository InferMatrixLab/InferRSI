import gzip
import hashlib
import json
import os
import threading
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from inferrsi.observability import profile_timeline
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


def test_distinct_long_kernel_names_survive_aggregation_and_compact_export(tmp_path):
    source, review = fixture(tmp_path)
    # Both ends of the display labels coincide. Even newlines remain significant.
    prefix, suffix = "kernel_template<" + "A" * 300, "B" * 100 + ">"
    names = [prefix + separator + suffix for separator in ("\n", " ")]
    events = [event("kernel", names[0], 0, 10), event("kernel", names[1], 10, 20)]
    source.write_bytes(gzip.compress(json.dumps(events).encode()))
    attach_profile(tmp_path, capture_id="long", source="profiles/baseline.json.gz", review=review)

    capture, = read_profiles(tmp_path)[0]
    ids = [hashlib.sha256(name.encode()).hexdigest() for name in names]
    stats = capture["stats"]
    assert [(s["name_sha256"], s["count"], s["total_us"]) for s in stats] == [
        (ids[1], 1, 20), (ids[0], 1, 10)]
    assert len({s["name"] for s in stats}) == 2 and all(len(s["name"]) <= 220 for s in stats)
    track, = capture["tracks"]
    assert [e["name_sha256"] for e in track["events"]] == ids
    full = json.loads(gzip.decompress((tmp_path / capture["source"]["events_path"]).read_bytes()))
    assert [full["names"][record[1]] for record in full["events"]] == names


def test_polls_reuse_digests_but_opening_rechecks_only_the_selected_source(tmp_path, monkeypatch):
    source, review = fixture(tmp_path)
    other = source.with_name("other.json")
    other.write_text(json.dumps([event("kernel", "other", 0, 1)]))
    for path in (source, other):
        attach_profile(tmp_path, capture_id=path.name, source=f"profiles/{path.name}",
                       review=review)

    reads = []
    raw = profile_timeline._raw

    def counted(path):
        reads.append(path)
        return raw(path)

    monkeypatch.setattr(profile_timeline, "_raw", counted)
    first, missing = read_profiles(tmp_path)
    assert not missing and reads == [source, other]
    assert read_profiles(tmp_path) == (first, []) and reads == [source, other]

    # Opening the later capture must not stream the earlier raw file, even on a cold cache.
    profile_timeline._overview_digest.cache_clear()
    reads.clear()
    digest = first[1]["source"]["events_sha256"]
    assert profile_timeline.profile_event_table(tmp_path, digest)
    assert reads == [other, tmp_path / first[1]["source"]["events_path"]]

    # Same-size edits with restored mtime must still fail before full events are served.
    read_profiles(tmp_path)
    info = other.stat()
    other.write_bytes(other.read_bytes().replace(b'"other"', b'"wrong"'))
    os.utime(other, ns=(info.st_atime_ns, info.st_mtime_ns))
    assert profile_timeline.profile_event_table(tmp_path, digest) is None


def test_poll_revalidates_an_atomically_replaced_profile(tmp_path):
    source, review = fixture(tmp_path)
    attach_profile(tmp_path, capture_id="baseline", source="profiles/baseline.json.gz",
                   review=review)
    assert len(read_profiles(tmp_path)[0]) == 1
    replacement = source.with_name("new.json.gz")
    info = source.stat()
    replacement.write_bytes(b"x" * info.st_size)
    os.utime(replacement, ns=(info.st_atime_ns, info.st_mtime_ns))
    replacement.replace(source)
    assert read_profiles(tmp_path) == ([], ["baseline"])


def test_lane_limit_counts_only_lanes_with_positive_duration(tmp_path):
    _, review = fixture(tmp_path)
    source = tmp_path / "profiles/lanes.json"
    events = [dict(event("cpu_op", "launch", 0, 1), tid=n) for n in range(512)]
    events.append(dict(event("cpu_op", "empty", 1, 0), tid=512))
    source.write_text(json.dumps(events))
    attach_profile(tmp_path, capture_id="fits", source="profiles/lanes.json", review=review)
    capture, = read_profiles(tmp_path)[0]
    assert capture["event_count"] == 512
    too_many = source.with_name("too-many.json")
    events[-1]["dur"] = 1
    too_many.write_text(json.dumps(events))
    with pytest.raises(ValueError, match="512 lanes"):
        attach_profile(tmp_path, capture_id="over", source="profiles/too-many.json", review=review)
    assert [c["id"] for c in read_profiles(tmp_path)[0]] == ["fits"]


def test_profile_history_uses_verified_preceding_search_not_round_number(tmp_path):
    source, review = fixture(tmp_path)
    meta = json.loads(review.read_bytes())
    meta.update(started_at="2026-11-11T08:41:43.000001Z",
                context_ids=["before", "same", "later", "untimed", "bad", "missing"],
                timing={"basis": "CUDA events", "stages_ms": {"worker": 50.5, "denoise": 40.0}})
    review.write_text(json.dumps(meta))
    attach_profile(tmp_path, capture_id="baseline", source=f"profiles/{source.name}", review=review)
    cap, = read_profiles(tmp_path)[0]
    assert cap["timing"] == meta["timing"]
    searches = {key: {"state": "verified", "captured_at": time} for key, time in [
        ("before", "2026-11-11T16:41:43+08:00"), ("same", meta["started_at"]),
        ("later", "2026-11-11T08:41:44Z"), ("untimed", "2026-11-11T08:41:40")]}
    searches["bad"] = {"state": "hash_mismatch"}
    links = profile_timeline.pre_profile_searches(cap, searches)
    assert [(x["context_id"], x["state"]) for x in links] == [
        ("before", "verified"), ("same", "not_before"), ("later", "not_before"),
        ("untimed", "unknown_time"), ("bad", "unverified"), ("missing", "unverified")]
    assert profile_timeline.pre_profile_searches({}, searches) == []


@pytest.mark.parametrize("extra", [
    {"context_ids": ["kb"]}, {"started_at": "2026-01-01T00:00:00"},
    {"timing": {"basis": "unknown", "stages_ms": {"CUDA": -1}}},
    {"timing": {"basis": "unknown", "stages_ms": {"CUDA": float("inf")}}},
])
def test_invalid_optional_history_is_not_attached(tmp_path, extra):
    source, review = fixture(tmp_path)
    review.write_text(json.dumps({**json.loads(review.read_bytes()), **extra}))
    with pytest.raises(ValueError):
        attach_profile(tmp_path, capture_id="baseline", source=f"profiles/{source.name}",
                       review=review)
    assert not (tmp_path / "profile-captures.jsonl").exists()
