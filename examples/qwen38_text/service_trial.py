"""Owned native public-entry or HTTP service trial; no service performance metric."""

import argparse
import importlib
import json
import os
import sys
import time
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

# Invoke as a module from a snapshotted control checkout; engine imports are pinned below.
from examples.qwen38_text.profiles import BF16_MODEL_ID, MODEL_IDS, precision
from examples.qwen38_text.provenance import capture_sources, import_records
from examples.qwen38_text.service_client import (
    Client,
    EvidenceGap,
    idle,
    observe_queued_cancel,
    observe_service,
    payload,
    poll_state,
)
from examples.qwen38_text.service_protocol import SCOPE, read_protocol
from examples.qwen38_text.trial import verify_manifest
from inferrsi.infra.processes import launch_server, stop_server


def child_imports(info, engine_repo):
    """Convert actual child-process origins to the shared relative source format."""
    import hashlib

    origins = info.get("module_origins")
    if not isinstance(origins, dict) or not origins:
        raise EvidenceGap("Child engine import provenance missing")
    root = Path(engine_repo).resolve(strict=True)
    records = {}
    for name, record in origins.items():
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise EvidenceGap("Child engine import origin malformed")
        path = Path(record["path"]).resolve(strict=True)
        if (
            not (name == "nanovllm" or name.startswith("nanovllm."))
            or not path.is_relative_to(root)
            or hashlib.sha256(path.read_bytes()).hexdigest() != record.get("sha256")
        ):
            raise EvidenceGap("Child engine source origin or bytes mismatch")
        records[name] = {"path": path.relative_to(root).as_posix(), "sha256": record["sha256"]}
    return records


def public_trial(args, workload, result):
    root = args.engine_repo.resolve(strict=True)
    import_records("nanovllm", root)
    sys.path.insert(0, str(root))
    importlib.invalidate_caches()
    from nanovllm import LLM, SamplingParams

    import_records("nanovllm", root)
    engine = LLM(
        str(args.model_path),
        max_context_tokens=workload["limits"]["max_context_tokens"],
        max_active_requests=workload["limits"]["max_active_requests"],
    )
    result.update(initial_state=engine.stats(), cases=[])
    try:
        for case in workload["cases"]:
            output = engine.generate(
                [case["prompt"]],
                SamplingParams(
                    temperature=0,
                    max_tokens=case["max_tokens"],
                    ignore_eos=False,
                ),
                use_tqdm=False,
            )
            result["cases"].append({"id": case["id"], "outputs": output, "state": engine.stats()})
        result["model_info"] = engine.provenance()
    finally:
        engine.close()
        result["closed_state"] = engine.stats()
    return result


def start_owned_server(args, workload, root, *, fault=False):
    root.mkdir()
    ready, final = root / "ready.json", root / "shutdown.json"
    limits, timeouts = workload["limits"], workload["timeouts"]
    command = [
        sys.executable,
        "-m",
        "nanovllm.qwen38.server",
        "--model",
        str(args.model_path),
        "--host",
        "127.0.0.1",
        "--port",
        "0",
        "--ready-file",
        str(ready),
        "--shutdown-file",
        str(final),
    ]
    if fault:
        command[1:3] = [
            str(Path(__file__).with_name("service_fault.py")),
            str(args.engine_repo.resolve()),
        ]
    for key in ("max_context_tokens", "max_active_requests", "max_connections", "max_body_bytes"):
        command += ["--" + key.replace("_", "-"), str(limits[key])]
    command += ["--socket-timeout", str(timeouts["socket"])]
    environment = os.environ.copy()
    # A module launched from this cwd must resolve the exact requested engine checkout.
    environment["PYTHONPATH"] = str(args.engine_repo.resolve())
    with (root / "server.log").open("wb") as log:
        process, ownership = launch_server(command, args.engine_repo, environment, log)
    record = {"ownership": ownership, "command": command}
    try:
        deadline = time.monotonic() + timeouts["startup"]
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise EvidenceGap("Owned server exited before readiness")
            if ready.exists():
                try:
                    info = json.loads(ready.read_text())
                    host, port = info["address"]
                    client = Client(
                        host,
                        port,
                        timeouts["request"],
                        limits["max_response_bytes"],
                        root / "http-observations.jsonl",
                    )
                    health = client.request("GET", "/health")
                    if health["status"] == 200:
                        record.update(ready=info, health=health)
                        child_imports(info, args.engine_repo)
                        return process, client, record, final
                except (OSError, ValueError, KeyError):
                    pass
            time.sleep(timeouts["poll"])
        raise EvidenceGap("Owned server readiness deadline expired")
    except BaseException:
        record["cleanup"] = stop_server(process, ownership, timeouts["shutdown"])
        (root / "startup-failure.json").write_text(json.dumps(record, indent=2))
        raise


def stop_owned_server(process, record, final, timeout):
    record["cleanup"] = stop_server(process, record["ownership"], timeout)
    if final.is_file():
        record["closed_state"] = json.loads(final.read_text())


def http_trial(args, workload, result):
    process, client, server, final = start_owned_server(
        args, workload, args.output.parent / "server"
    )
    result["server"] = server
    shutdown_stream = None
    try:
        result["http"] = observe_service(client, workload)
        result["http"]["queued_cancel"] = observe_queued_cancel(client, workload)
        result["model_info"] = client.state()
        shutdown_stream = client.stream(
            payload(workload["model_id"], workload["lifecycle"], "shutdown-active", stream=True)
        )
        result["shutdown_first_token"] = shutdown_stream.wait_first()
        result["shutdown_before"] = client.state()
    finally:
        stop_owned_server(process, server, final, workload["timeouts"]["shutdown"])
        if shutdown_stream is not None:
            result["shutdown_stream"] = shutdown_stream.finish()
    # A fresh process must recover readiness and the same generation after active shutdown.
    process, client, restarted, final = start_owned_server(
        args,
        workload,
        args.output.parent / "restart",
    )
    result["restart"] = restarted
    try:
        restarted["response"] = client.request(
            "POST",
            "/v1/completions",
            payload(
                workload["model_id"],
                workload["cases"][0],
                "restart-check",
            ),
        )
        restarted["state"] = client.state()
    finally:
        stop_owned_server(process, restarted, final, workload["timeouts"]["shutdown"])
    process, client, fault, final = start_owned_server(
        args,
        workload,
        args.output.parent / "fault",
        fault=True,
    )
    result["fault"] = fault
    try:
        fault["warmup"] = client.request(
            "POST",
            "/v1/completions",
            payload(
                workload["model_id"],
                workload["cases"][0],
                "fault-warmup",
            ),
        )
        stream = client.stream(
            payload(workload["model_id"], workload["lifecycle"], "injected-fault", stream=True)
        )
        fault["stream"] = stream.finish()
        fault["release"] = poll_state(
            client, idle, workload["timeouts"]["release"], workload["timeouts"]["poll"]
        )
        fault["reuse"] = client.request(
            "POST",
            "/v1/completions",
            payload(
                workload["model_id"],
                workload["cases"][0],
                "fault-reuse",
            ),
        )
        fault["state"] = client.state()
    finally:
        stop_owned_server(process, fault, final, workload["timeouts"]["shutdown"])
    return result


def normalize_evidence(value, engine_repo):
    """Validate raw origins before retaining only relative, publishable records."""
    if isinstance(value, list):
        return [normalize_evidence(item, engine_repo) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key == "module_origins":
            result[key] = child_imports(value, engine_repo)
        elif key == "command":
            result[key] = "<owned-server-command; private runtime log>"
        elif key == "address":
            result[key] = ["<owned-loopback>", "<ephemeral-port>"]
        else:
            result[key] = normalize_evidence(item, engine_repo)
    return result


def run(args):
    workload, workload_hash = read_protocol(args.workload, args.model_id)
    manifest_hash = verify_manifest(
        args.model_path, args.manifest, args.model_revision, args.model_id
    )
    if args.output.exists():
        raise ValueError("Refusing to overwrite service trial result")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "schema_version": 1,
        "qualification_scope": SCOPE,
        "mode": args.mode,
        "model_id": args.model_id,
        "precision": precision(args.model_id),
        "model_revision": args.model_revision,
        "manifest_sha256": manifest_hash,
        "workload_sha256": workload_hash,
        "complete": False,
    }
    try:
        result["observations"] = {}
        if args.mode == "public":
            public_trial(args, workload, result["observations"])
        else:
            http_trial(args, workload, result["observations"])
        result["source_provenance"] = capture_sources(
            args.engine_repo, excluded_run_dir=args.output.parents[2]
        )
        if args.mode == "http":
            result["source_provenance"]["engine"]["imports"] = child_imports(
                result["observations"]["model_info"],
                args.engine_repo,
            )
        result["complete"] = True
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        result["gap"] = type(error).__name__  # Never echo private paths or exception strings.
    result = normalize_evidence(result, args.engine_repo)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("engine-repo", "model-path", "manifest", "workload", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--model-id", choices=MODEL_IDS, default=BF16_MODEL_ID)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--mode", choices=("public", "http"), required=True)
    args = parser.parse_args()
    try:
        run(args)
    except Exception as error:
        print(f"Service trial incomplete ({type(error).__name__})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
