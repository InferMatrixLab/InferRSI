"""Runtime boundary controls; fake audio here does not qualify model quality."""

import contextlib
import hashlib
import importlib.util
import io
import json
import struct
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from tests.engineering_task_support import load_task_module

tts = load_task_module("qwen3-tts-npu", "evaluation")


def module(name):
    spec = importlib.util.spec_from_file_location(
        "tts_test_" + name, str(tts.task_resources().joinpath(name + ".py"))
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.mark.parametrize("name", ["inference.py", "service.py", "model-assets.json"])
def test_frozen_runtime_drift_is_rejected(tmp_path, name):
    tts.prepare(
        tmp_path / "prepared",
        concurrencies=[1],
        warmups=1,
        scorer_id="fixture",
        gates={
            "min_improvement_pct": 0,
            "max_error_rate_increase": 0,
            "max_speaker_drop": 0,
            "max_duration_change_pct": 0,
            "max_ttfa_regression_pct": 0,
        },
    )
    (tmp_path / "prepared" / name).write_text("modified", encoding="utf-8")
    with pytest.raises(ValueError, match="runtime changed"):
        tts.load_prepared(tmp_path / "prepared")


def test_model_integrity_rejects_same_size_corruption(tmp_path):
    asset = tmp_path / "weights"
    asset.write_bytes(b"original")
    manifest = {
        "files": [
            {"path": "weights", "bytes": 8, "sha256": hashlib.sha256(b"original").hexdigest()}
        ]
    }
    baseline = module("baseline")
    assert baseline.verify_assets(tmp_path, manifest)[0]["bytes"] == 8
    asset.write_bytes(b"modified")
    with pytest.raises(ValueError, match="hash mismatch"):
        baseline.verify_assets(tmp_path, manifest)


@pytest.mark.parametrize("engine", ["vllm", "vllm_omni", "qwen3_tts_engine"])
def test_actual_dynamic_engine_import_blocked(engine):
    baseline = str(tts.task_resources().joinpath("baseline.py"))
    script = """
import importlib, importlib.util, sys
spec = importlib.util.spec_from_file_location('baseline', sys.argv[1])
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)
sys.meta_path.insert(0, baseline.EngineImportGuard())
assert importlib.util.find_spec(sys.argv[2]) is not None
try:
    importlib.import_module(sys.argv[2])
except ImportError as error:
    assert 'blocks engine import' in str(error)
else:
    raise AssertionError('engine import succeeded')
assert 'torch' not in sys.modules
"""
    subprocess.run([sys.executable, "-c", script, baseline, engine], check=True, timeout=15)


@contextlib.contextmanager
def standalone(factory, *, capacity=1, timeout=2):
    service = module("service").SpeechService(Path("unused"), factory, capacity)
    server = ThreadingHTTPServer(("127.0.0.1", 0), service.handler(timeout))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", service
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
        service.close()


class FakeModel:
    speakers = {"ryan", "vivian"}
    languages = {"english", "chinese"}

    def __init__(self, path):
        self.owner = threading.get_ident()
        self.payloads = []
        self.closed = False

    def generate(self, payload):
        assert threading.get_ident() == self.owner
        self.payloads.append(payload)
        return {
            "pcm": struct.pack("<4h", 120, -120, 240, -240),
            "sample_rate": 24000,
            "finish_reason": "stop",
            "codec_frames": 1,
        }

    def close(self):
        assert threading.get_ident() == self.owner
        self.closed = True


def test_bundled_service_works_with_existing_collector_and_owner_thread(tmp_path):
    with standalone(FakeModel) as (url, service):
        with urllib.request.urlopen(url + "/health", timeout=2) as response:
            assert json.load(response)["audio_delivery"] == "complete-waveform"
        for index, (voice, language) in enumerate((("Ryan", "English"), ("Vivian", "Chinese"))):
            result = tts._request(
                url + "/v1/audio/speech",
                {
                    "input": "different text " + str(index),
                    "voice": voice,
                    "language": language,
                },
                tmp_path,
                "r" + str(index),
                2,
            )
            assert result["success"]
            assert result["pcm_bytes"] == 8
            assert len(result["chunks"]) == 1
        assert service.model.payloads[1]["voice"] == "vivian"
        assert service.model.owner != threading.get_ident()
    assert service.model.closed


def test_request_timeout_does_not_release_running_model_slot(tmp_path):
    started, release = threading.Event(), threading.Event()

    class BlockingModel(FakeModel):
        def generate(self, payload):
            started.set()
            assert release.wait(5)
            return super().generate(payload)

    with standalone(BlockingModel, timeout=0.05) as (url, service):
        try:
            result = tts._request(url + "/v1/audio/speech", {"input": "first"}, tmp_path, "a", 2)
            assert started.is_set() and not result["success"]
            request = urllib.request.Request(
                url + "/v1/audio/speech", data=json.dumps({"input": "second"}).encode()
            )
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request, timeout=2)
            assert error.value.code == 503
        finally:
            release.set()
        # Barrier on the same executor: completion callbacks have returned the slot.
        service.executor.submit(lambda: None).result(timeout=2)
        result = tts._request(url + "/v1/audio/speech", {"input": "third"}, tmp_path, "c", 2)
        assert result["success"]


def request_handler(service):
    """Exercise the real handler with deterministic transport failure injection."""
    handler_type = service.handler(2)
    handler = handler_type.__new__(handler_type)
    payload = json.dumps({"input": "fixture"}).encode()
    handler.path = "/v1/audio/speech"
    handler.headers = {"Content-Length": str(len(payload))}
    handler.rfile = io.BytesIO(payload)
    handler.wfile = io.BytesIO()
    handler.send_response = lambda *args: None
    handler.send_header = lambda *args: None
    handler.end_headers = lambda: None
    return handler


@pytest.mark.parametrize("error_type", [BrokenPipeError, ConnectionResetError])
def test_header_disconnect_releases_slot_only_after_generation_finishes(error_type):
    started, release = threading.Event(), threading.Event()

    class BlockingModel(FakeModel):
        def generate(self, payload):
            started.set()
            assert release.wait(5)
            return super().generate(payload)

    service = module("service").SpeechService(Path("unused"), BlockingModel, 1)
    handler = request_handler(service)

    def disconnected():
        assert started.wait(2)
        raise error_type("synthetic header disconnect")

    handler.end_headers = disconnected
    try:
        # Capture the old handler's exception so the resource assertion also runs.
        try:
            handler.do_POST()
        except error_type:
            pass
        assert not service.capacity.acquire(blocking=False)
    finally:
        release.set()
        service.executor.submit(lambda: None).result(timeout=2)
        service.close()
    assert service.capacity.acquire(blocking=False), "completed generation leaked its slot"
    assert not service.capacity.acquire(blocking=False), "slot released more than once"


def test_submission_failure_releases_capacity(monkeypatch):
    service = module("service").SpeechService(Path("unused"), FakeModel, 1)
    handler = request_handler(service)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic submit failure")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(service.executor, "submit", fail)
            with pytest.raises(RuntimeError, match="synthetic submit failure"):
                handler.do_POST()
        assert service.capacity.acquire(blocking=False)
        assert not service.capacity.acquire(blocking=False)
    finally:
        service.close()


@pytest.mark.parametrize(
    "payload",
    [
        {"input": ""},
        {"input": "text", "voice": "missing"},
        {"input": "text", "seed": True},
        {"input": "text", "max_new_tokens": 1},
        {"input": "text", "response_format": "mp3"},
    ],
)
def test_invalid_request_never_reaches_model(payload):
    with standalone(FakeModel) as (url, service):
        request = urllib.request.Request(
            url + "/v1/audio/speech", data=json.dumps(payload).encode()
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=2)
        assert error.value.code == 400
        assert not service.model.payloads


def test_serve_cli_execs_verified_bundle(tmp_path, monkeypatch):
    main = load_task_module("qwen3-tts-npu", "benchmark").main

    prepared = tmp_path / "prepared"
    tts.prepare(
        prepared,
        concurrencies=[1],
        warmups=1,
        scorer_id="fixture",
        gates={
            "min_improvement_pct": 0,
            "max_error_rate_increase": 0,
            "max_speaker_drop": 0,
            "max_duration_change_pct": 0,
            "max_ttfa_regression_pct": 0,
        },
    )

    def execv(python, command):
        assert python == sys.executable
        assert command[:2] == [python, str((prepared / "baseline.py").resolve())]
        assert "--repo" not in command
        raise SystemExit(0)

    help_result = subprocess.run(
        [sys.executable, "-I", str(prepared / "benchmark.py"), "--help"],
        cwd=tmp_path, capture_output=True, text=True, timeout=15,
    )
    assert help_result.returncode == 0, help_result.stderr
    assert "prepare" in help_result.stdout and "assess" in help_result.stdout
    monkeypatch.setattr("os.execv", execv)
    with pytest.raises(SystemExit) as result:
        main(
            [
                "serve",
                "--prepared",
                str(prepared),
                "--model-path",
                str(tmp_path / "model"),
                "--port",
                "18090",
                "--identity-output",
                str(tmp_path / "identity.json"),
            ]
        )
    assert result.value.code == 0
