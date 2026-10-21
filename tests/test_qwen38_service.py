"""CPU protocol regressions only; synthetic observations never qualify a model/GPU."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from examples.qwen38_text.profiles import BF16_MODEL_ID, precision
from examples.qwen38_text.service_client import Client, EvidenceGap, payload
from examples.qwen38_text.service_fault import install_fault
from examples.qwen38_text.service_protocol import ERROR_IDS, SCOPE, read_protocol
from examples.qwen38_text.service_trial import child_imports, normalize_evidence
from examples.qwen38_text.service_validate import decode_stream, digest, functional


@pytest.fixture
def protocol():
    return {
        "schema_version": 1,
        "qualification_scope": SCOPE,
        "model_id": BF16_MODEL_ID,
        "precision": precision(BF16_MODEL_ID),
        "timeouts": dict.fromkeys(
            ("startup", "request", "release", "poll", "shutdown", "socket"), 2
        ),
        "limits": {
            "max_context_tokens": 128,
            "max_active_requests": 2,
            "max_connections": 4,
            "max_body_bytes": 4096,
            "max_response_bytes": 65536,
        },
        "cases": [
            {"id": "eos", "prompt": "hello", "max_tokens": 4},
            {"id": "unicode", "prompt": [2, 3], "max_tokens": 3},
        ],
        "concurrent_case_ids": ["eos", "unicode"],
        "eos_case_id": "eos",
        "survivor_case_id": "unicode",
        "lifecycle": {"id": "long", "prompt": "continue", "max_tokens": 100},
        "queued_case": {"id": "prefill", "prompt": "long prefill", "max_tokens": 100},
    }


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.update(concurrent_case_ids=["eos", "eos"]),
        lambda p: p["cases"][1].update(prompt="hello"),
        lambda p: p.update(eos_case_id=None),
        lambda p: p["queued_case"].update(id="../bad"),
        lambda p: p["timeouts"].pop("shutdown"),
        lambda p: p["limits"].update(max_connections=2),
    ],
)
def test_protocol_rejects_incomplete_or_masked_coverage(protocol, tmp_path, mutation):
    mutation(protocol)
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(protocol))
    with pytest.raises(ValueError):
        read_protocol(path, BF16_MODEL_ID)


def state(*active, closed=False, terminal=()):
    return {
        "active_request_ids": list(active),
        "active_requests": len(active),
        "capacity": 2,
        "available": 2 - len(active),
        "queued_requests": 0,
        "runner_state_count": len(active),
        "runner_state_bytes": 32 * len(active),
        "closed": closed,
        "terminal_requests": list(terminal),
    }


def ending(name, reason, prefilled=True, count=1):
    return {
        "request_id": name,
        "finish_reason": reason,
        "prefilled": prefilled,
        "token_count": count,
        "active_peer_request_ids": ["survivor-disconnected"],
    }


def output(reason="length"):
    return {"text": "中🙂�", "token_ids": [4, 5, 6], "finish_reason": reason}


def event(name, text, tokens, reason=None):
    return {
        "id": name,
        "request_id": name,
        "model": BF16_MODEL_ID,
        "choices": [{"index": 0, "text": text, "token_ids": tokens, "finish_reason": reason}],
    }


def stream(name, result=None, case=None, disconnected=False):
    result = result or output()
    events = [event(name, result["text"], result["token_ids"])]
    if not disconnected:
        events.append(event(name, "", [], result["finish_reason"]))
    return {
        "request": payload(
            BF16_MODEL_ID, case or {"prompt": "x", "max_tokens": 3}, name, stream=True
        ),
        "status": 200,
        "content_type": "text/event-stream",
        "events": events,
        "done_marker": not disconnected,
        "client_disconnect": disconnected,
        "error": None,
    }


def response(name, result=None):
    result = result or output()
    body = event(name, result["text"], result["token_ids"], result["finish_reason"])
    body["usage"] = {
        "prompt_tokens": 2,
        "completion_tokens": len(result["token_ids"]),
        "total_tokens": 2 + len(result["token_ids"]),
    }
    return {"status": 200, "content_type": "application/json", "body": body}


def ack(name):
    return {
        "status": 200,
        "body": {
            "request_id": name,
            "cancelled": True,
            "active_request_ids_before_cancel": [name, "survivor-cancelled"],
        },
    }


def server(closed=None):
    return {
        "ownership": {
            "mode": "inferrsi_trial_group",
            "server_pid": 12,
            "helper_pid": 11,
            "process_group_id": 11,
            "helper_process_group_id": 11,
            "server_start_new_session": False,
        },
        "cleanup": {
            "mode": "inferrsi_trial_group",
            "process_group_id": 11,
            "status": "completed",
            "remaining_pids": [],
            "kill_sent": False,
            "term_sent": True,
            "server_returncode": 0,
        },
        "closed_state": closed or state(closed=True),
    }


@pytest.fixture
def observations(protocol):
    public = {"initial_state": state(), "closed_state": state(closed=True), "cases": []}
    obs = {
        "initial_state": state(),
        "serial": [],
        "concurrent": [],
        "concurrent_release": [state()],
        "overlap": [state("concurrent-0", "concurrent-1")],
        "final_state": state(),
    }
    for index, case in enumerate(protocol["cases"]):
        name = case["id"]
        result = output("stop" if name == "eos" else "length")
        public["cases"].append({"id": name, "outputs": [result], "state": state()})
        obs["serial"].append(
            {
                "id": name,
                "request": payload(BF16_MODEL_ID, case, "json-" + name),
                "response": response("json-" + name, result),
                "stream": stream("sse-" + name, result, case),
                "release": [state()],
            }
        )
        obs["concurrent"].append(
            {"id": name, "stream": stream(f"concurrent-{index}", result, case)}
        )
    for reason in ("cancelled", "disconnected"):
        name = "lifecycle-" + reason
        obs[reason] = {
            "observed_first": True,
            "before": state(name, "survivor-" + reason),
            "overlap": [state(name, "survivor-" + reason)],
            "ack": ack(name),
            "stream": stream(name, output(reason), protocol["lifecycle"], reason == "disconnected"),
            "survivor": stream("survivor-" + reason, case=protocol["cases"][1]),
            "release": [state(terminal=[ending(name, reason)])],
            "reuse": response("reuse-" + reason, output("stop")),
            "reuse_release": [state()],
        }
    obs["capacity"] = {
        "during": [state("capacity-0", "capacity-1")],
        "overflow": {"status": 429},
        "duplicate": {"status": 400},
        "cancel_acknowledgements": [ack(f"capacity-{i}") for i in range(2)],
        "streams": [stream(f"capacity-{i}", output("cancelled")) for i in range(2)],
        "release": [state()],
    }
    queued = state("queue-blocker", "queue-target")
    queued["queued_requests"] = 1
    obs["queued_cancel"] = {
        "during": [queued],
        "ack": ack("queue-target"),
        "streams": [
            stream("queue-blocker", output("cancelled")),
            stream("queue-target", {"text": "", "token_ids": [], "finish_reason": "cancelled"}),
        ],
        "release": [state(terminal=[ending("queue-target", "cancelled", False, 0)])],
    }
    obs["errors"] = [
        {"id": name, "response": {"status": 400}, "release": [state()]} for name in ERROR_IDS
    ]
    http = {
        "http": obs,
        "shutdown_first_token": True,
        "shutdown_before": state("shutdown-active"),
        "shutdown_stream": stream("shutdown-active", output("shutdown")),
        "server": server(state(closed=True, terminal=[ending("shutdown-active", "shutdown")])),
        "restart": {
            **server(),
            "response": response("restart-check", output("stop")),
            "state": state(),
        },
    }
    fault_stream = stream(
        "injected-fault", {"text": "中", "token_ids": [4], "finish_reason": "error"}
    )
    fault_stream["events"].insert(1, {"error": {"type": "generation_error"}})
    fault_state = state()
    fault_state["fault_injection"] = {
        "kind": "harness_injected_runtime_error",
        "request_id": "injected-fault",
        "triggered": True,
        "successful_target_calls": 1,
        "source": "examples/qwen38_text/service_fault.py",
        "source_sha256": digest(
            Path(__file__).parents[1] / "examples/qwen38_text/service_fault.py"
        ),
    }
    http["fault"] = {
        **server(),
        "warmup": response("fault-warmup", output("stop")),
        "stream": fault_stream,
        "release": [state(terminal=[ending("injected-fault", "error")])],
        "reuse": response("fault-reuse", output("stop")),
        "state": fault_state,
    }
    return public, http


def test_complete_synthetic_functional_contract(protocol, observations):
    failures = []
    functional(*observations, protocol, failures)
    assert failures == []


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p, h: h["http"]["cancelled"]["survivor"]["events"][-1]["choices"][0].update(
            finish_reason="cancelled"
        ),
        lambda p, h: h["http"]["serial"][0]["stream"]["events"][0]["choices"][0].update(
            text="corrupt"
        ),
        lambda p, h: h["http"]["errors"][0]["response"].update(status=200),
        lambda p, h: h["http"]["cancelled"]["release"][-1].update(runner_state_bytes=32),
        lambda p, h: h["shutdown_stream"]["events"][-1]["choices"][0].update(finish_reason="stop"),
    ],
)
def test_complete_behavior_regression_fails(protocol, observations, mutation):
    mutation(*observations)
    failures = []
    functional(*observations, protocol, failures)
    assert failures


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p, h: h["http"].update(overlap=[]),
        lambda p, h: h["http"]["cancelled"].update(overlap=[]),
        lambda p, h: p["cases"][0]["outputs"][0].update(finish_reason="length"),
        lambda p, h: h["shutdown_stream"].update(done_marker=False),
        lambda p, h: h["fault"]["state"]["fault_injection"].update(triggered=False),
        lambda p, h: h["http"]["queued_cancel"]["release"][0]["terminal_requests"][0].update(
            prefilled=True
        ),
    ],
)
def test_missing_observation_is_gap(protocol, observations, mutation):
    mutation(*observations)
    with pytest.raises(EvidenceGap):
        functional(*observations, protocol, [])


@pytest.fixture
def socket_server():
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            name = body["request_id"]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            events = [
                event(name, "中", [4]),
                event(name, "🙂�", [5]),
                event(name, "", [], "stop"),
                "[DONE]",
            ]
            if name == "trailing":
                events.append("[DONE]")
            if name == "incomplete":
                events = events[:-2]
            for item in events:
                self.wfile.write(
                    (
                        "data: "
                        + (item if isinstance(item, str) else json.dumps(item, ensure_ascii=False))
                        + "\n\n"
                    ).encode()
                )
                self.wfile.flush()
            self.close_connection = True

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield Client("127.0.0.1", server.server_port, 2, 65536)
    server.shutdown()
    server.server_close()
    thread.join()


def test_real_socket_unicode_and_terminal_framing(socket_server):
    record = socket_server.stream({"request_id": "valid"}).finish()
    result = decode_stream(record, "valid", BF16_MODEL_ID)
    assert result == {"text": "中🙂�", "token_ids": [4, 5], "finish_reason": "stop"}


@pytest.mark.parametrize("name", ["trailing", "incomplete"])
def test_real_socket_missing_or_duplicate_done_rejected(socket_server, name):
    record = socket_server.stream({"request_id": name}).finish()
    with pytest.raises(EvidenceGap):
        decode_stream(record, name, BF16_MODEL_ID)


def test_fault_hook_is_request_specific_once_and_reusable():
    calls = []
    target = object()
    model = SimpleNamespace(forward=lambda *a, **k: calls.append(k["state"]) or "logits")
    engine = SimpleNamespace(
        runner=SimpleNamespace(model=model, _requests={}), provenance=lambda: {}
    )
    install_fault(engine)
    assert model.forward(state=object()) == "logits"
    engine.runner._requests["injected-fault"] = SimpleNamespace(state=target)
    assert model.forward(state=target) == "logits"
    with pytest.raises(RuntimeError, match="Harness-injected"):
        model.forward(state=target)
    engine.runner._requests.clear()
    assert model.forward(state=object()) == "logits"
    assert len(calls) == 3 and engine.provenance()["fault_injection"]["triggered"]


def test_child_origin_validation_precedes_redaction(tmp_path):
    root = tmp_path / "engine"
    root.mkdir()
    path = root / "module.py"
    path.write_text("# fixture")
    raw = {
        "module_origins": {"nanovllm": {"path": str(path), "sha256": digest(path)}},
        "command": ["python", str(tmp_path / "private-model")],
        "address": ["127.0.0.1", 9999],
    }
    normalized = normalize_evidence(raw, root)
    assert normalized["module_origins"]["nanovllm"]["path"] == "module.py"
    assert str(tmp_path) not in json.dumps(normalized)
    path.write_text("# changed")
    with pytest.raises(EvidenceGap):
        child_imports(raw, root)


@pytest.fixture
def bundle(tmp_path, protocol, observations):
    import copy

    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    run, workload, manifest = (
        tmp_path / name for name in ("run", "workload.json", "manifest.json")
    )
    write(workload, protocol)
    write(manifest, {"model_id": BF16_MODEL_ID, "revision": "a" * 40})
    sources = {}
    for label, namespace, modules in (
        ("control", "inferrsi", [""]),
        (
            "engine",
            "nanovllm",
            [
                "",
                ".qwen38.engine",
                ".qwen38.model",
                ".qwen38.runner",
                ".qwen38.loader",
                ".qwen38.server",
            ],
        ),
    ):
        imports = {}
        for suffix in modules:
            name = namespace + suffix
            relative = name.replace(".", "/") + ("/__init__.py" if not suffix else ".py")
            path = tmp_path / label / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# synthetic source\n")
            imports[name] = {"path": relative, "sha256": digest(path)}
        sources[label] = {
            "head": ("a" if label == "control" else "b") * 40,
            "snapshot_hash": ("c" if label == "control" else "d") * 64,
            "imports": imports,
        }
    locked = {
        side: {"available": True, **sources[label]}
        for side, label in (("baseline", "control"), ("candidate", "engine"))
    }
    spec = {
        "objective": "correctness",
        "comparison_scope": SCOPE,
        "model": BF16_MODEL_ID,
        "model_revision": "a" * 40,
        "workload_id": digest(workload),
        "repetitions": 1,
        "repo": str(tmp_path / "control"),
        "candidate_repo": str(tmp_path / "engine"),
    }
    write(run / "run.lock.json", spec)
    write(run / "repositories.lock.json", locked)
    write(run / "environment.json", {"requested_device_model": "Synthetic GPU"})
    info = {
        "model_id": BF16_MODEL_ID,
        "device_model": "Synthetic GPU",
        "device_type": "cuda",
        "device_count": 1,
        "precision": "bfloat16",
        "loader_report": {"scope": "text_only", "dtype": "bfloat16", "loaded_parameters": 1},
        "versions": {"torch": "synthetic", "transformers": "synthetic"},
        "module_origins": sources["engine"]["imports"],
    }
    for side, mode, obs in zip(("baseline", "candidate"), ("public", "http"), observations):
        obs["model_info"] = copy.deepcopy(info)
        if side == "candidate":
            for key in ("restart", "fault"):
                obs[key]["state"].update(copy.deepcopy(info))
        root = run / side / "trial-001"
        write(
            root / "result.json",
            {
                "schema_version": 1,
                "qualification_scope": SCOPE,
                "mode": mode,
                "model_id": BF16_MODEL_ID,
                "precision": precision(BF16_MODEL_ID),
                "complete": True,
                "model_revision": "a" * 40,
                "manifest_sha256": digest(manifest),
                "workload_sha256": digest(workload),
                "source_provenance": sources,
                "observations": obs,
            },
        )
        write(
            root / "execution.json",
            {
                "status": "completed",
                "returncode": 0,
                "cwd": spec["repo" if side == "baseline" else "candidate_repo"],
            },
        )
        write(root / "source.json", {"side": side, "before": locked[side], "after": locked[side]})
    return run, workload, manifest


@pytest.mark.parametrize(
    "kind,expected", [("valid", 0), ("tokens", 1), ("missing", 2), ("null", 2), ("source", 2)]
)
def test_validator_subprocess_written_verdict(bundle, kind, expected):
    import subprocess
    import sys

    run, workload, manifest = bundle
    path = run / "candidate/trial-001/result.json"
    data = json.loads(path.read_text())
    if kind == "tokens":
        data["observations"]["http"]["serial"][0]["stream"]["events"][0]["choices"][0]["text"] = (
            "bad"
        )
    elif kind == "missing":
        data["observations"]["http"]["overlap"] = []
    elif kind == "null":
        data["source_provenance"] = None
    elif kind == "source":
        data["source_provenance"]["engine"].pop("head")
    path.write_text(json.dumps(data))
    output_path = run / "validation.json"
    script = Path(__file__).parents[1] / "examples/qwen38_text/service_validate.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--run-dir",
            str(run),
            "--workload",
            str(workload),
            "--manifest",
            str(manifest),
            "--output",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == expected, result.stderr + result.stdout
    result = json.loads(output_path.read_text())
    assert result["verdict"] == {0: "PASS", 1: "FAIL", 2: "INCONCLUSIVE"}[expected]
    assert str(run.parent) not in output_path.read_text()


def test_synthetic_service_uses_common_correctness_loop(bundle, tmp_path):
    import sys

    from inferrsi.harness.runner import run_experiment
    from inferrsi.runspec import RunSpec

    fixture, workload, manifest = bundle
    frozen = json.loads((fixture / "run.lock.json").read_text())
    locked = json.loads((fixture / "repositories.lock.json").read_text())

    def command(side):
        return (
            sys.executable,
            "-c",
            "import shutil,sys;shutil.copyfile(sys.argv[1],sys.argv[2])",
            str(fixture / side / "trial-001/result.json"),
            "{result}",
        )

    script = Path(__file__).parents[1] / "examples/qwen38_text/service_validate.py"
    spec = RunSpec(
        repo=frozen["repo"],
        candidate_repo=frozen["candidate_repo"],
        objective="correctness",
        comparison_scope=SCOPE,
        repetitions=1,
        max_minutes=1,
        model=BF16_MODEL_ID,
        model_revision="a" * 40,
        workload_id=digest(workload),
        baseline_command=command("baseline"),
        candidate_command=command("candidate"),
        output_dir=str(tmp_path / "outputs"),
        validation_command=(
            sys.executable,
            str(script),
            "--run-dir",
            "{run_dir}",
            "--workload",
            str(workload),
            "--manifest",
            str(manifest),
            "--output",
            "{result}",
        ),
    )
    run = run_experiment(
        spec,
        {"requested_device_model": "Synthetic GPU"},
        snapshot=lambda path, *_: locked[
            "baseline" if str(path) == frozen["repo"] else "candidate"
        ],
    )
    result = json.loads((run / "evaluation.json").read_text())
    assert result["verdict"] == "PASS", result
    assert result["improvement_pct"] is None


@pytest.fixture
def lifecycle_socket():
    cancelled, disconnected = threading.Event(), threading.Event()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Connection", "close")
            if self.path.startswith("/v1/cancel/"):
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(ack("held")["body"]).encode())
                self.wfile.flush()
                cancelled.set()
            else:
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(
                    ("data: " + json.dumps(event("held", "中", [4])) + "\n\n").encode()
                )
                self.wfile.flush()
                import select
                import socket

                while not cancelled.wait(0.005):
                    if select.select([self.connection], [], [], 0)[0]:
                        if not self.connection.recv(1, socket.MSG_PEEK):
                            disconnected.set()
                            break
                else:
                    self.wfile.write(
                        (
                            "data: "
                            + json.dumps(event("held", "", [], "cancelled"))
                            + "\n\ndata: [DONE]\n\n"
                        ).encode()
                    )
                    self.wfile.flush()
            self.close_connection = True

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield Client("127.0.0.1", server.server_port, 2, 65536), disconnected
    cancelled.set()
    server.shutdown()
    server.server_close()
    thread.join()


def test_real_socket_cancel_control_and_terminal(lifecycle_socket):
    client, _ = lifecycle_socket
    held = client.stream({"request_id": "held"})
    assert held.wait_first()
    assert client.request("POST", "/v1/cancel/held", {})["body"]["cancelled"]
    record = held.finish()
    assert decode_stream(record, "held", BF16_MODEL_ID)["finish_reason"] == "cancelled"


def test_real_socket_disconnect_reaches_peer(lifecycle_socket):
    client, disconnected = lifecycle_socket
    held = client.stream({"request_id": "held"})
    assert held.wait_first()
    held.disconnect()
    record = held.finish()
    assert disconnected.wait(2)
    assert decode_stream(record, "held", BF16_MODEL_ID, disconnected=True)["token_ids"] == [4]


@pytest.mark.parametrize("reason", ["cancelled", "disconnected"])
def test_survivor_finished_before_lifecycle_linearization_is_gap(protocol, observations, reason):
    observed = observations[1]["http"][reason]
    if reason == "cancelled":
        observed["ack"]["body"]["active_request_ids_before_cancel"] = ["lifecycle-cancelled"]
    else:
        observed["release"][0]["terminal_requests"][0]["active_peer_request_ids"] = []
    with pytest.raises(EvidenceGap, match="Survivor was not active"):
        functional(*observations, protocol, [])


def test_missing_runtime_length_coverage_is_gap(protocol, observations):
    for case in observations[0]["cases"]:
        case["outputs"][0]["finish_reason"] = "stop"
    with pytest.raises(EvidenceGap, match="max-token"):
        functional(*observations, protocol, [])
