"""Adjudicate complete native service functional observations; no latency claims."""

import argparse
import json
import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from examples.qwen38_text.profiles import (
    BF16_MODEL_ID,
    FP8_MODEL_ID,
    MODEL_IDS,
    check_precision,
    validate_native_loading,
)
from examples.qwen38_text.service_client import EvidenceGap, idle, payload
from examples.qwen38_text.service_protocol import ERROR_IDS, SCOPE, read_protocol
from examples.qwen38_text.validate import digest, local_file, read_json, source_identity


def need(condition, message):
    if not condition:
        raise EvidenceGap(message)


def check(condition, message, failures):
    if not condition:
        failures.append(message)


def zero_state(state, failures, label, *, closed=False):
    need(isinstance(state, dict), "Missing state observation")
    for key in (
        "active_requests",
        "capacity",
        "available",
        "queued_requests",
        "runner_state_count",
        "runner_state_bytes",
    ):
        need(type(state.get(key)) is int and state[key] >= 0, "Invalid state accounting")
    need(isinstance(state.get("active_request_ids"), list), "Missing active request identities")
    check(
        idle(state) and not state["active_request_ids"],
        label + ": state/capacity not released",
        failures,
    )
    check(state.get("closed") is closed, label + ": wrong closed state", failures)


def released(observations, failures, label):
    need(isinstance(observations, list) and bool(observations), "Missing release observations")
    zero_state(observations[-1], failures, label)
    return observations[-1]


def terminal(state, request_id):
    records = state.get("terminal_requests")
    need(isinstance(records, list), "Missing terminal request ledger")
    found = [record for record in records if record.get("request_id") == request_id]
    need(len(found) == 1, "Terminal request coverage missing or ambiguous")
    return found[0]


def decode_response(response, request_id, model_id):
    need(
        isinstance(response, dict) and response.get("status") == 200,
        "Successful completion response missing",
    )
    need(
        str(response.get("content_type", "")).startswith("application/json"),
        "Completion response content type missing",
    )
    body = response["body"]
    need(
        body.get("id") == request_id
        and body.get("request_id") == request_id
        and body.get("model") == model_id,
        "Response request/model identity mismatch",
    )
    choices = body.get("choices")
    need(
        isinstance(choices, list) and len(choices) == 1 and choices[0].get("index") == 0,
        "Completion choice coverage missing",
    )
    item = choices[0]
    need(
        isinstance(item.get("token_ids"), list)
        and all(type(token) is int and token >= 0 for token in item["token_ids"])
        and isinstance(item.get("text"), str),
        "Completion tokens/text missing",
    )
    usage = body.get("usage")
    need(
        isinstance(usage, dict)
        and type(usage.get("prompt_tokens")) is int
        and usage["prompt_tokens"] > 0,
        "Completion token accounting missing",
    )
    need(
        usage.get("completion_tokens") == len(item["token_ids"])
        and usage.get("total_tokens") == usage["prompt_tokens"] + len(item["token_ids"]),
        "Completion token accounting inconsistent",
    )
    return {key: item[key] for key in ("text", "token_ids", "finish_reason")}


def decode_stream(stream, request_id, model_id, *, disconnected=False, injected_error=False):
    need(
        isinstance(stream, dict) and stream.get("status") == 200 and stream.get("error") is None,
        "SSE transport incomplete",
    )
    need(
        str(stream.get("content_type", "")).startswith("text/event-stream"),
        "Missing SSE content type",
    )
    need(stream.get("request", {}).get("request_id") == request_id, "SSE request identity missing")
    need(stream.get("client_disconnect") is disconnected, "Wrong SSE disconnect observation")
    if not disconnected:
        need(stream.get("done_marker") is True, "SSE terminal marker missing")
    events = stream.get("events")
    need(isinstance(events, list), "SSE events missing")
    tokens, text, reason = [], "", None
    error_events = 0
    for event in events:
        need(isinstance(event, dict), "Malformed SSE event")
        if "error" in event:
            need(
                injected_error
                and reason is None
                and error_events == 0
                and isinstance(event["error"], dict)
                and event["error"].get("type") == "generation_error",
                "Unexpected SSE error event",
            )
            error_events += 1
            continue
        need(
            event.get("id") == request_id
            and event.get("request_id") == request_id
            and event.get("model") == model_id,
            "SSE event request/model identity mismatch",
        )
        choices = event.get("choices")
        need(
            isinstance(choices, list) and len(choices) == 1 and choices[0].get("index") == 0,
            "SSE event choice coverage missing",
        )
        item = choices[0]
        need(reason is None, "SSE emitted data after terminal event")
        need(
            isinstance(item.get("text"), str)
            and isinstance(item.get("token_ids"), list)
            and all(type(token) is int and token >= 0 for token in item["token_ids"]),
            "SSE token/delta coverage missing",
        )
        tokens.extend(item["token_ids"])
        text += item["text"]
        if item.get("finish_reason") is not None:
            need(
                not item["token_ids"] and not item["text"], "SSE terminal event contains token data"
            )
            reason = item["finish_reason"]
    if not disconnected:
        need(reason is not None, "SSE terminal reason missing")
    if injected_error:
        need(error_events == 1, "Injected generation error event missing")
    return {"token_ids": tokens, "text": text, "finish_reason": reason}


def compare(actual, expected, failures, label):
    check(actual == expected, label + ": tokens, decoded text or terminal reason differ", failures)


def validate_sources(record, spec, locked, trial_root, side):
    sources = record.get("source_provenance")
    need(
        isinstance(sources, dict) and set(sources) == {"control", "engine"},
        "Both source identities are required for both service roles",
    )
    for label, target, repo in (
        ("control", "baseline", spec["repo"]),
        ("engine", "candidate", spec["candidate_repo"]),
    ):
        identity = source_identity(locked[target], available=True)
        source = source_identity(sources[label])
        need(
            all(source[key] == identity[key] for key in ("head", "snapshot_hash")),
            "Service source differs from locked checkout",
        )
        imports = source.get("imports")
        need(isinstance(imports, dict), "Service imports missing")
        required = (
            {"inferrsi"}
            if label == "control"
            else {
                "nanovllm",
                "nanovllm.qwen38.engine",
                "nanovllm.qwen38.model",
                "nanovllm.qwen38.loader",
                "nanovllm.qwen38.runner",
            }
        )
        if label == "engine" and side == "candidate":
            required.add("nanovllm.qwen38.server")
        if label == "engine" and record["model_id"] == FP8_MODEL_ID:
            required |= {"nanovllm.qwen38.quant", "nanovllm.qwen38._triton_fp8"}
        need(required <= set(imports), "Required service import origins missing")
        prefix = "inferrsi" if label == "control" else "nanovllm"
        for name, imported in imports.items():
            need(name == prefix or name.startswith(prefix + "."), "Wrong source namespace")
            need(isinstance(imported, dict), "Malformed source import")
            path = local_file(Path(repo), imported.get("path"))
            need(digest(path) == imported.get("sha256"), "Service imported bytes differ")
    check_record = read_json(trial_root / "source.json")
    need(check_record.get("side") == side, "Wrong trial source check role")
    for stage in ("before", "after"):
        identity = source_identity(check_record.get(stage), available=True)
        need(
            all(identity[key] == locked[side][key] for key in ("head", "snapshot_hash")),
            "Service source changed during trial",
        )


def model_origins(info, record, engine_repo):
    origins = info.get("module_origins")
    expected = record["source_provenance"]["engine"]["imports"]
    need(
        isinstance(origins, dict) and set(expected) <= set(origins),
        "Per-process native module coverage missing",
    )
    for name, item in origins.items():
        need(
            isinstance(name, str)
            and (name == "nanovllm" or name.startswith("nanovllm."))
            and isinstance(item, dict),
            "Malformed per-process origin",
        )
        path = local_file(Path(engine_repo), item.get("path"))
        need(digest(path) == item.get("sha256"), "Per-process source bytes differ")
        if name in expected:
            need(item == expected[name], "Per-process origin differs from declared engine")


def model_info(info, model_id, device_model):
    need(
        isinstance(info, dict) and info.get("model_id") == model_id,
        "Service model identity missing",
    )
    need(
        info.get("device_model") == device_model
        and info.get("device_type") == "cuda"
        and info.get("device_count") == 1,
        "Service GPU qualification mismatch",
    )
    need(
        info.get("precision") == ("fp8" if model_id == FP8_MODEL_ID else "bfloat16"),
        "Service precision mismatch",
    )
    validate_native_loading(info.get("loader_report"), model_id)
    versions = info.get("versions")
    need(
        isinstance(versions, dict) and versions.get("torch") and versions.get("transformers"),
        "Service runtime versions missing",
    )
    if model_id == FP8_MODEL_ID:
        execution = info.get("fp8_execution")
        count = info["loader_report"]["fp8_linear_modules"]
        need(
            isinstance(execution, dict)
            and execution.get("modules") == count
            and execution.get("executed_modules") == count
            and type(execution.get("total_calls")) is int
            and execution["total_calls"] >= count
            and execution.get("weight_dtype") == "float8_e4m3fn"
            and execution.get("scale_dtype") == "float32"
            and execution.get("actual_dtypes_valid") is True
            and isinstance(execution.get("per_module_calls"), dict)
            and len(execution["per_module_calls"]) == count
            and all(type(n) is int and n > 0 for n in execution["per_module_calls"].values())
            and sum(execution["per_module_calls"].values()) == execution["total_calls"],
            "Actual service FP8 execution missing",
        )
        need(bool(versions.get("triton")), "Triton runtime version missing")
    return versions


def cleanup(server, failures, label):
    ownership, result = server.get("ownership"), server.get("cleanup")
    need(
        isinstance(ownership, dict) and isinstance(result, dict),
        "Service ownership/cleanup missing",
    )
    need(
        ownership.get("mode") == "inferrsi_trial_group"
        and ownership.get("server_start_new_session") is False
        and ownership.get("helper_pid") == ownership.get("process_group_id")
        and ownership.get("helper_pid") == ownership.get("helper_process_group_id")
        and type(ownership.get("server_pid")) is int,
        "Service process ownership unverified",
    )
    need(
        result.get("mode") == ownership["mode"]
        and result.get("process_group_id") == ownership["process_group_id"]
        and result.get("status") == "completed"
        and result.get("remaining_pids") == [],
        "Owned service descendants were not confirmed released",
    )
    check(
        result.get("kill_sent") is False
        and result.get("term_sent") is True
        and result.get("server_returncode") == 0,
        label + ": graceful shutdown failed",
        failures,
    )
    zero_state(server.get("closed_state"), failures, label, closed=True)


def functional(public, http, workload, failures):
    model_id = workload["model_id"]
    expected = {}
    need(len(public["cases"]) == len(workload["cases"]), "Public entry case coverage missing")
    zero_state(public["initial_state"], failures, "public initial")
    for case, observed in zip(workload["cases"], public["cases"]):
        need(
            observed.get("id") == case["id"] and len(observed["outputs"]) == 1,
            "Public entry case identity missing",
        )
        result = observed["outputs"][0]
        need(
            isinstance(result.get("text"), str)
            and isinstance(result.get("token_ids"), list)
            and all(type(token) is int and token >= 0 for token in result["token_ids"]),
            "Public entry generation missing",
        )
        check(
            0 < len(result["token_ids"]) <= case["max_tokens"]
            and result.get("finish_reason") in {"stop", "length"},
            "Public generation limit",
            failures,
        )
        check(
            result.get("finish_reason") != "length"
            or len(result["token_ids"]) == case["max_tokens"],
            "Public length termination differs from requested budget",
            failures,
        )
        expected[case["id"]] = result
        zero_state(observed["state"], failures, "public request")
    need(
        expected[workload["eos_case_id"]]["finish_reason"] == "stop",
        "Frozen EOS fixture did not observe a stop; EOS coverage missing",
    )
    zero_state(public["closed_state"], failures, "public close", closed=True)
    observations = http["http"]
    zero_state(observations["initial_state"], failures, "HTTP initial")
    need(len(observations["serial"]) == len(workload["cases"]), "HTTP serial coverage missing")
    for case, observed in zip(workload["cases"], observations["serial"]):
        name = case["id"]
        need(
            observed["id"] == name
            and observed["request"] == payload(model_id, case, "json-" + name),
            "HTTP serial input identity differs",
        )
        compare(
            decode_response(observed["response"], "json-" + name, model_id),
            expected[name],
            failures,
            "HTTP JSON " + name,
        )
        need(
            observed["stream"]["request"] == payload(model_id, case, "sse-" + name, stream=True),
            "HTTP SSE input identity differs",
        )
        compare(
            decode_stream(observed["stream"], "sse-" + name, model_id),
            expected[name],
            failures,
            "HTTP SSE " + name,
        )
        released(observed["release"], failures, "serial release")
    concurrent = observations["concurrent"]
    need(
        len(concurrent) == len(workload["concurrent_case_ids"]), "Concurrent case coverage missing"
    )
    ids = {f"concurrent-{index}" for index in range(len(concurrent))}
    need(
        any(ids <= set(state.get("active_request_ids", [])) for state in observations["overlap"]),
        "Concurrent admission overlap was not observed",
    )
    for index, (name, observed) in enumerate(zip(workload["concurrent_case_ids"], concurrent)):
        need(observed["id"] == name, "Concurrent request identity missing")
        case = next(case for case in workload["cases"] if case["id"] == name)
        need(
            observed["stream"]["request"]
            == payload(model_id, case, f"concurrent-{index}", stream=True),
            "Concurrent input identity differs",
        )
        compare(
            decode_stream(observed["stream"], f"concurrent-{index}", model_id),
            expected[name],
            failures,
            "Concurrent " + name,
        )
    released(observations["concurrent_release"], failures, "concurrent release")
    first = workload["cases"][0]["id"]
    for reason in ("cancelled", "disconnected"):
        observed = observations[reason]
        request_id = "lifecycle-" + reason
        need(
            observed["observed_first"] is True
            and {request_id, "survivor-" + reason} <= set(observed["before"]["active_request_ids"]),
            "Active lifecycle cancellation was not observed",
        )
        survivor_id = "survivor-" + reason
        need(
            any(
                {request_id, survivor_id} <= set(state.get("active_request_ids", []))
                for state in observed["overlap"]
            ),
            "Lifecycle isolation overlap missing",
        )
        survivor_case = next(
            case for case in workload["cases"] if case["id"] == workload["survivor_case_id"]
        )
        need(
            observed["survivor"]["request"]
            == payload(model_id, survivor_case, survivor_id, stream=True),
            "Survivor input mismatch",
        )
        compare(
            decode_stream(observed["survivor"], survivor_id, model_id),
            expected[workload["survivor_case_id"]],
            failures,
            reason + " survivor isolation",
        )
        stream = decode_stream(
            observed["stream"], request_id, model_id, disconnected=reason == "disconnected"
        )
        if reason == "cancelled":
            need(
                observed["ack"].get("status") == 200
                and observed["ack"].get("body", {}).get("cancelled") is True,
                "Active cancellation acknowledgement missing",
            )
            check(
                stream["finish_reason"] == "cancelled",
                "Acknowledged cancellation ignored",
                failures,
            )
        state = released(observed["release"], failures, reason + " release")
        end = terminal(state, request_id)
        check(end.get("finish_reason") == reason, reason + " terminal reason differs", failures)
        check(end.get("prefilled") is True, reason + " did not release a prefilled state", failures)
        compare(
            decode_response(observed["reuse"], "reuse-" + reason, model_id),
            expected[first],
            failures,
            reason + " capacity reuse",
        )
        released(observed["reuse_release"], failures, reason + " reuse release")
    capacity = observations["capacity"]
    capacity_ids = {
        f"capacity-{index}" for index in range(workload["limits"]["max_active_requests"])
    }
    need(
        any(
            capacity_ids <= set(state.get("active_request_ids", [])) for state in capacity["during"]
        ),
        "Full active capacity was not observed",
    )
    check(capacity["overflow"].get("status") == 429, "Capacity overflow not rejected", failures)
    check(
        capacity["duplicate"].get("status") == 400,
        "Duplicate active request not rejected",
        failures,
    )
    need(
        len(capacity["cancel_acknowledgements"]) == len(capacity_ids),
        "Saturation cancel probes missing",
    )
    check(
        all(
            item.get("status") == 200 and item.get("body", {}).get("cancelled") is True
            for item in capacity["cancel_acknowledgements"]
        ),
        "Control-plane cancel unavailable",
        failures,
    )
    need(len(capacity["streams"]) == len(capacity_ids), "Saturation streams missing")
    for index, stream in enumerate(capacity["streams"]):
        check(
            decode_stream(stream, f"capacity-{index}", model_id)["finish_reason"] == "cancelled",
            "Saturation cancellation ignored",
            failures,
        )
    released(capacity["release"], failures, "capacity release")
    queued = observations["queued_cancel"]
    need(
        any(
            state.get("queued_requests", 0) > 0
            and "queue-target" in state.get("active_request_ids", [])
            for state in queued["during"]
        ),
        "Queued cancellation was not observed",
    )
    need(
        queued["ack"].get("status") == 200
        and queued["ack"].get("body", {}).get("cancelled") is True,
        "Queued cancellation acknowledgement missing",
    )
    need(len(queued["streams"]) == 2, "Queued stream coverage missing")
    decode_stream(queued["streams"][0], "queue-blocker", model_id)
    target = decode_stream(queued["streams"][1], "queue-target", model_id)
    check(
        target["finish_reason"] == "cancelled" and not target["token_ids"],
        "Queued target produced tokens or ignored cancellation",
        failures,
    )
    state = released(queued["release"], failures, "queued release")
    end = terminal(state, "queue-target")
    need(end.get("prefilled") is False, "Cancellation raced with prefill; queued coverage missing")
    check(
        end.get("finish_reason") == "cancelled" and end.get("token_count") == 0,
        "Queued cancellation allocated/executed state",
        failures,
    )
    errors = observations["errors"]
    need(
        len(errors) == len(ERROR_IDS) and {item["id"] for item in errors} == ERROR_IDS,
        "Error/limit coverage missing",
    )
    for item in errors:
        check(
            item["response"].get("status") == 400, item["id"] + ": wrong HTTP rejection", failures
        )
        released(item["release"], failures, item["id"] + " release")
    zero_state(observations["final_state"], failures, "HTTP final")
    need(
        http["shutdown_first_token"] is True
        and "shutdown-active" in http["shutdown_before"]["active_request_ids"],
        "Shutdown with active request was not observed",
    )
    shutdown = decode_stream(http["shutdown_stream"], "shutdown-active", model_id)
    check(
        shutdown["finish_reason"] == "shutdown", "Active stream shutdown framing failed", failures
    )
    cleanup(http["server"], failures, "active shutdown")
    check(
        terminal(http["server"]["closed_state"], "shutdown-active").get("finish_reason")
        == "shutdown",
        "Active request not closed during shutdown",
        failures,
    )
    compare(
        decode_response(http["restart"]["response"], "restart-check", model_id),
        expected[first],
        failures,
        "restart generation",
    )
    zero_state(http["restart"]["state"], failures, "restart request")
    cleanup(http["restart"], failures, "restart shutdown")
    fault = http["fault"]
    compare(
        decode_response(fault["warmup"], "fault-warmup", model_id),
        expected[first],
        failures,
        "fault-process warmup",
    )
    injected = decode_stream(fault["stream"], "injected-fault", model_id, injected_error=True)
    marker = fault["state"].get("fault_injection")
    need(
        isinstance(marker, dict)
        and marker.get("kind") == "harness_injected_runtime_error"
        and marker.get("request_id") == "injected-fault"
        and marker.get("triggered") is True
        and marker.get("successful_target_calls") == 1
        and marker.get("source") == "examples/qwen38_text/service_fault.py"
        and marker.get("source_sha256") == digest(Path(__file__).with_name("service_fault.py")),
        "Real-call fault injection coverage missing",
    )
    check(
        injected["finish_reason"] == "error" and len(injected["token_ids"]) == 1,
        "Injected post-admission failure not terminated correctly",
        failures,
    )
    state = released(fault["release"], failures, "injected failure release")
    check(
        terminal(state, "injected-fault").get("finish_reason") == "error",
        "Injected failure ledger missing",
        failures,
    )
    compare(
        decode_response(fault["reuse"], "fault-reuse", model_id),
        expected[first],
        failures,
        "injected failure reuse",
    )
    zero_state(fault["state"], failures, "injected failure reuse")
    cleanup(fault, failures, "fault-process shutdown")


def validate(run_dir, workload_path, manifest_path, model_id):
    run_dir = Path(run_dir)
    workload, workload_hash = read_protocol(workload_path, model_id)
    manifest, spec = read_json(manifest_path), read_json(run_dir / "run.lock.json")
    environment = read_json(run_dir / "environment.json")
    locked = read_json(run_dir / "repositories.lock.json")
    check_precision(manifest, model_id)
    need(
        spec.get("objective") == "correctness"
        and spec.get("comparison_scope") == SCOPE
        and spec.get("model") == model_id
        and manifest.get("model_id") == model_id
        and spec.get("model_revision") == manifest.get("revision")
        and spec.get("workload_id") == workload_hash,
        "Service RunSpec/input identity mismatch",
    )
    repetitions = spec.get("repetitions")
    need(type(repetitions) is int and repetitions > 0, "Invalid service repetition coverage")
    failures, observations, versions = [], {}, None
    for side, mode in (("baseline", "public"), ("candidate", "http")):
        roots = sorted((run_dir / side).glob("trial-*"))
        need(
            [root.name for root in roots] == [f"trial-{n:03d}" for n in range(1, repetitions + 1)],
            "Service trial coverage missing",
        )
        observations[side] = []
        for root in roots:
            record, execution = read_json(root / "result.json"), read_json(root / "execution.json")
            need(
                execution.get("status") == "completed"
                and execution.get("returncode") == 0
                and record.get("complete") is True,
                "Service execution incomplete",
            )
            need(
                Path(execution["cwd"]).resolve()
                == Path(spec["repo" if side == "baseline" else "candidate_repo"]).resolve(),
                "Wrong service trial cwd",
            )
            identity = {
                "schema_version": 1,
                "qualification_scope": SCOPE,
                "mode": mode,
                "model_id": model_id,
                "model_revision": manifest["revision"],
                "manifest_sha256": digest(manifest_path),
                "workload_sha256": workload_hash,
            }
            need(
                all(record.get(key) == value for key, value in identity.items()),
                "Wrong service identity",
            )
            check_precision(record, model_id)
            validate_sources(record, spec, locked, root, side)
            observed = record["observations"]
            model_origins(observed["model_info"], record, spec["candidate_repo"])
            current = model_info(
                observed["model_info"], model_id, environment.get("requested_device_model")
            )
            if side == "candidate":
                for key in ("restart", "fault"):
                    model_origins(observed[key]["state"], record, spec["candidate_repo"])
                    need(
                        model_info(
                            observed[key]["state"],
                            model_id,
                            environment.get("requested_device_model"),
                        )
                        == current,
                        "Restart/fault process runtime differs",
                    )
            if versions is None:
                versions = current
            need(versions == current, "Service environment changed across trials")
            observations[side].append(observed)
    for public, http in zip(observations["baseline"], observations["candidate"]):
        functional(public, http, workload, failures)
    return {
        "verdict": "FAIL" if failures else "PASS",
        "qualification_scope": SCOPE,
        "reasons": failures,
        "limitations": [
            "L4 functional service scope only",
            "No performance or SLO claim",
            "Model correctness remains a separate teacher-forcing check",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run-dir", "workload", "manifest", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--model-id", choices=MODEL_IDS, default=BF16_MODEL_ID)
    args = parser.parse_args()
    try:
        result = validate(args.run_dir, args.workload, args.manifest, args.model_id)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        result = {
            "verdict": "INCONCLUSIVE",
            "qualification_scope": SCOPE,
            "reasons": [f"Incomplete service evidence ({type(error).__name__})"],
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result))
    return {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}[result["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
