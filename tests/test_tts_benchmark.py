"""CPU transport/assessment controls use synthetic audio and synthetic scorer values."""

import base64
import contextlib
import json
import shutil
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tests.engineering_task_support import load_task_module

tts = load_task_module("qwen3-tts-npu", "evaluation")
main = load_task_module("qwen3-tts-npu", "benchmark").main


@contextlib.contextmanager
def service(events, *, chunked=False):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            if chunked:
                self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for event in events:
                data = b"data: " + json.dumps(event).encode() + b"\n\n"
                if chunked:
                    data = f"{len(data):x}\r\n".encode() + data + b"\r\n"
                self.wfile.write(data)
            if chunked:
                self.wfile.write(b"0\r\n\r\n")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1/audio/speech"
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def events(pcm=None, terminal="stop"):
    pcm = pcm if pcm is not None else struct.pack("<240h", *([1000, -1000] * 120))
    # Splitting a sample across deltas is valid. First-byte timing would be wrong.
    result = [
        {"type": "speech.audio.delta", "audio": base64.b64encode(b).decode()}
        for b in (pcm[:1], pcm[1:])
    ]
    if terminal is not None:
        result.append({"type": "speech.audio.done", "finish_reason": terminal})
    return result


def prepared(tmp_path):
    root = tmp_path / "prepared"
    tts.prepare(
        root,
        concurrencies=[1],
        warmups=1,
        scorer_id="synthetic-fixture-v1",
        gates={
            "min_improvement_pct": 10,
            "max_error_rate_increase": 0.01,
            "max_speaker_drop": 0.02,
            "max_duration_change_pct": 5,
            "max_ttfa_regression_pct": 10,
        },
    )
    return root


@pytest.mark.parametrize("terminal", [None, "length", "error"])
def test_incomplete_or_truncated_audio_is_rejected(tmp_path, terminal):
    with service(events(terminal=terminal)) as url:
        result = tts._request(url, {"input": "fixture"}, tmp_path, "request", 2)
    assert not result["success"]
    assert (tmp_path / "request.wav").is_file()


@pytest.mark.parametrize("chunked", [False, True])
def test_pcm_sample_split_and_terminal_are_accepted(tmp_path, chunked):
    with service(events(), chunked=chunked) as url:
        result = tts._request(url, {"input": "fixture"}, tmp_path, "request", 2)
    assert result["success"]
    assert result["ttfa_seconds"] == result["chunks"][1]["seconds"]
    assert result["pcm_bytes"] == 480


def test_silent_audio_is_rejected(tmp_path):
    with service(events(pcm=b"\0" * 480)) as url:
        result = tts._request(url, {"input": "fixture"}, tmp_path, "request", 2)
    assert not result["success"]


@pytest.mark.parametrize("stream", ["heartbeats", "partial_line", "headers", "chunked", "stall"])
def test_absolute_deadline_covers_all_response_reads(tmp_path, stream):
    stop = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            header = b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
            if stream == "headers":
                chunk = b"X-Heartbeat: alive\r\n"
            elif stream == "chunked":
                header += b"Transfer-Encoding: chunked\r\n\r\n"
                # A chunk-size line that never ends also must respect the deadline.
                chunk = b"0"
            else:
                header += b"\r\n"
                chunk = b": heartbeat\n\n" if stream == "heartbeats" else b":"
            try:
                self.wfile.write(header)
                self.wfile.flush()
                if stream == "stall":
                    if stop.wait(0.3):
                        return
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                    stop.wait(1)
                else:
                    for _ in range(60):
                        self.wfile.write(chunk)
                        self.wfile.flush()
                        if stop.wait(0.02):
                            break
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        started = time.perf_counter()
        result = tts._request(
            f"http://127.0.0.1:{server.server_port}/v1/audio/speech",
            {"input": "fixture"}, tmp_path, "deadline", 0.4,
        )
        elapsed = time.perf_counter() - started
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
        worker.join()
    assert result.get("error") == "TimeoutError", result
    assert not result["success"]
    assert 0.35 <= result["elapsed_seconds"] <= elapsed < 0.6
    assert (tmp_path / "deadline.wav").is_file()
    assert tts.read(tmp_path / "deadline.json") == result


@pytest.fixture
def comparison(tmp_path):
    plan = prepared(tmp_path)
    before, after = tmp_path / "baseline", tmp_path / "candidate"
    with service(events()) as url:
        tts.collect(plan, before, endpoint=url, model="synthetic-model", timeout=2)
    shutil.copytree(before, after)
    document = tts.read(after / "result.json")
    # Hand-authored 2x timing fixture isolates the offline arithmetic from wall noise.
    for cohort in document["cohorts"]:
        for row in cohort["requests"] + cohort["warmups"]:
            row["elapsed_seconds"] *= 0.5
            row["ttfa_seconds"] *= 0.5
        cohort["wall_seconds"] *= 0.5
        cohort["metrics"] = tts.summarize(cohort["requests"], cohort["wall_seconds"])
    tts.write(after / "result.json", document)
    quality = {"scorer_id": "synthetic-fixture-v1"}
    for side, directory in (("baseline", before), ("candidate", after)):
        quality[side] = [
            {
                "id": row["id"],
                "pcm_sha256": row["pcm_sha256"],
                "error_rate": 0.01,
                "speaker_similarity": 0.8,
            }
            for cohort in tts.read(directory / "result.json")["cohorts"]
            for row in cohort["warmups"] + cohort["requests"]
        ]
    path = tmp_path / "quality.json"
    tts.write(path, quality)
    return plan, before, after, path


def test_offline_assessment_recomputes_ratio(comparison):
    result = tts.assess(*comparison)
    assert result["verdict"] == "PASS"
    assert result["speedup"] == pytest.approx(2)


def test_missing_audio_quality_is_inconclusive(comparison):
    plan, before, after, quality = comparison
    quality.unlink()
    result = tts.assess(plan, before, after, quality)
    assert result["verdict"] == "INCONCLUSIVE"
    assert result["speedup"] is None


@pytest.mark.parametrize("field,value", [("error_rate", 0.5), ("speaker_similarity", 0.1)])
def test_faster_candidate_with_quality_loss_fails(comparison, field, value):
    quality = tts.read(comparison[-1])
    quality["candidate"][0][field] = value
    tts.write(comparison[-1], quality)
    result = tts.assess(*comparison)
    assert result["verdict"] == "FAIL"
    assert result["speedup"] is None


@pytest.mark.parametrize("change", ["audio", "missing_score", "wrong_pcm", "wrong_payload"])
def test_evidence_mismatch_has_no_usable_score(comparison, change):
    _, _, after, path = comparison
    if change == "audio":
        with (after / "c1-r0.wav").open("ab") as output:
            output.write(b"unused trailing bytes")
        # Change a byte in actual sample data, not merely container padding.
        audio = bytearray((after / "c1-r0.wav").read_bytes())
        audio[44] ^= 1
        (after / "c1-r0.wav").write_bytes(audio)
    elif change == "wrong_payload":
        document = tts.read(after / "result.json")
        document["cohorts"][0]["requests"][0]["payload_sha256"] = "wrong"
        tts.write(after / "result.json", document)
    else:
        quality = tts.read(path)
        if change == "missing_score":
            quality["candidate"].pop()
        else:
            quality["candidate"][0]["pcm_sha256"] = "wrong"
        tts.write(path, quality)
    result = tts.assess(*comparison)
    assert result["verdict"] == "INCONCLUSIVE"
    assert result["speedup"] is None


def test_prepared_launcher_drift_is_rejected(tmp_path):
    plan = prepared(tmp_path)
    (plan / "baseline.py").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="launcher changed"):
        tts.load_prepared(plan)
    assert (
        tts.assess(plan, tmp_path / "base", tmp_path / "candidate", tmp_path / "quality")["verdict"]
        == "INCONCLUSIVE"
    )


def test_cli_assess_exit_code_and_packaged_resource(comparison, capsys):
    assert tts.task_resources().joinpath("baseline.py").is_file()
    plan, before, after, quality = comparison
    assert (
        main(
            [
                "assess",
                "--prepared",
                str(plan),
                "--baseline",
                str(before),
                "--candidate",
                str(after),
                "--quality",
                str(quality),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["speedup"] == pytest.approx(2)


def test_concurrency_cannot_exceed_actual_request_count(tmp_path):
    policy = tts.read(prepared(tmp_path) / "policy.json")
    with pytest.raises(ValueError, match="Concurrency exceeds"):
        tts.prepare(
            tmp_path / "too-wide",
            concurrencies=[16],
            warmups=1,
            gates=policy["gates"],
            scorer_id="synthetic-fixture-v1",
        )
