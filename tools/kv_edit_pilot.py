"""Secret-free, SCRIPTED KV edit/check worker and existing-executor supervisor.

This module cannot call a model provider. It exercises the real fixed-tool and
sandbox path with supplied response DATA. A future paid launcher is a separately
reviewed integration, not a switch or credential/config option offered here.
"""

import argparse
import hashlib
import json
import math
import os
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

# -I worker bootstrap: this exact trusted checkout, never cwd/PYTHONPATH/home.
ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT / "src"))

from inferrsi.harness import kv_edit_workbench as workbench  # noqa: E402
from inferrsi.harness import kv_reclamation as kv  # noqa: E402
from inferrsi.infra.artifacts import atomic_write_json  # noqa: E402
from inferrsi.infra.executors.local import execute_command  # noqa: E402
from inferrsi.model import anthropic_agent as provider  # noqa: E402
from inferrsi.model import anthropic_edit_agent as edit  # noqa: E402
from inferrsi.model.request_guard import (  # noqa: E402
    ENV_KEYS,
    authorize_request,
    gate_environment,
)

SCHEMA = "kv-scripted-worker-v1"
FILES = ("tools/kv_edit_pilot.py", "tools/kv_worker_supervisor.py",
         "src/inferrsi/harness/kv_edit_workbench.py",
         "src/inferrsi/harness/kv_reclamation.py",
         "src/inferrsi/harness/skill_eval_engineering.py", "src/inferrsi/harness/runner.py",
         "src/inferrsi/harness/evaluation.py", "src/inferrsi/harness/reporting.py",
         "src/inferrsi/infra/executors/local.py", "src/inferrsi/infra/processes.py",
         "src/inferrsi/infra/artifacts.py", "src/inferrsi/runspec.py",
         "src/inferrsi/claim.py", "src/inferrsi/summary_chart.py")
FIELDS = {"schema", "plan_sha256", "execution_id", "arm", "model", "client", "edit_plan",
          "input_token_ceiling", "suite_sha256", "baseline_sha256", "responses_sha256",
          "actor_sha256", "dependencies", "prompt"}


def _read_json(path, limit=16 * 1024 * 1024):
    return json.loads(kv.read_regular(Path(path), limit), object_pairs_hook=provider.unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def dependencies():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in FILES}


def _plan(value):
    if type(value) is not dict or set(value) != {
            "files", "limits", "check_ids", "metric_key", "metric_unit", "direction",
            "callbacks_sha256"}:
        raise ValueError("Wrong frozen edit-plan shape")
    return edit.EditPlan(files=tuple(edit.ExposedFile(**f) for f in value["files"]),
        limits=edit.EditLimits(**value["limits"]), check_ids=tuple(value["check_ids"]),
        **{k: value[k] for k in ("metric_key", "metric_unit", "direction", "callbacks_sha256")})


def prepare_scripted(inputs, workspace, plan, suite, baseline, responses, *,
                     plan_sha256, execution_id, arm, model, spec, prompt, input_token_ceiling):
    """Freeze offline inputs. No discovery, credentials, provider calls or ledger writes."""
    inputs = Path(inputs)
    if (not edit._sha(plan_sha256) or arm not in {"A2", "A3"}
            or type(responses) is not list or not 0 < len(responses) <= spec["max_requests"]
            or type(prompt) is not str):
        raise ValueError("Explicit frozen scripted inputs required")
    actual = edit.freeze_files(workspace, [f.path for f in plan.files])
    if actual != plan.files or kv.source_bytes(Path(workspace) / "candidate.py") != baseline:
        raise ValueError("Staged inputs differ from frozen actor manifest/baseline")
    scripts = provider.canonical(responses).encode()
    if len(scripts) > spec["max_requests"] * provider.MAX_RESPONSE:
        raise ValueError("Scripted response file exceeds fixed response bound")
    deps = dependencies()
    callback_binding = {"dependencies": deps, "suite_sha256": edit.digest(suite.serialized),
                        "baseline_sha256": edit.digest(baseline),
                        "responses_sha256": edit.digest(scripts), "prompt": prompt}
    plan = replace(plan, callbacks_sha256=edit.fingerprint(callback_binding))
    identity = edit.frozen_identity(plan, model, spec, input_token_ceiling)
    config = {"schema": SCHEMA, "plan_sha256": plan_sha256, "execution_id": execution_id,
              "arm": arm, "model": model, "client": spec, "edit_plan": asdict(plan),
              "input_token_ceiling": input_token_ceiling,
              "suite_sha256": edit.digest(suite.serialized),
              "baseline_sha256": edit.digest(baseline), "responses_sha256": edit.digest(scripts),
              "actor_sha256": edit.fingerprint(identity), "dependencies": deps, "prompt": prompt}
    inputs.mkdir(parents=True, exist_ok=False)
    (inputs / "suite.json").write_bytes(suite.serialized)
    (inputs / "baseline.py").write_bytes(baseline)
    (inputs / "responses.json").write_bytes(scripts)
    atomic_write_json(inputs / "worker.json", config)
    return config


def checked_inputs(inputs):
    inputs = Path(inputs)
    config = _read_json(inputs / "worker.json", 2 * 1024 * 1024)
    if (type(config) is not dict or set(config) != FIELDS or config["schema"] != SCHEMA
            or config["arm"] not in {"A2", "A3"} or config["dependencies"] != dependencies()):
        raise ValueError("Wrong scripted worker identity/dependencies")
    plan = _plan(config["edit_plan"])
    binding = {k: config[k] for k in ("dependencies", "suite_sha256", "baseline_sha256",
                                    "responses_sha256", "prompt")}
    if plan.callbacks_sha256 != edit.fingerprint(binding):
        raise ValueError("Visible callback/prompt/script binding changed")
    identity = edit.frozen_identity(plan, config["model"], config["client"],
                                    config["input_token_ceiling"])
    if edit.fingerprint(identity) != config["actor_sha256"]:
        raise ValueError("Frozen actor identity changed")
    raw = {}
    for name, field, limit in (("suite.json", "suite_sha256", 16 * 1024 * 1024),
                              ("baseline.py", "baseline_sha256", plan.limits.max_source_bytes),
                              ("responses.json", "responses_sha256",
                               config["client"]["max_requests"] * provider.MAX_RESPONSE)):
        raw[name] = kv.read_regular(inputs / name, limit)
        if edit.digest(raw[name]) != config[field]:
            raise ValueError("Frozen scripted input changed")
    suite = workbench.VisibleSuite(raw["suite.json"])
    responses = _read_json(inputs / "responses.json", len(raw["responses.json"]))
    if type(responses) is not list or not 0 < len(responses) <= config["client"]["max_requests"]:
        raise ValueError("Invalid bounded scripted response collection")
    return config, plan, suite, raw["baseline.py"], responses


def _known_usage(response, config, deadline):
    """Only known compatible raw usage is relayed; never response text or errors."""
    try:
        if (time.monotonic() >= deadline or type(response) is not dict
                or response.get("type") != "message" or response.get("role") != "assistant"
                or response.get("model") != config["model"]
                or response.get("stop_reason") != "tool_use"
                or type(response.get("content")) is not list
                or any(not provider.valid_content_block(c) for c in response["content"])
                or len(provider.canonical(response).encode()) > provider.MAX_RESPONSE):
            return None
        usage = provider.token_usage(response.get("usage"))
        if (usage["input_tokens"] > config["input_token_ceiling"]
                or usage["output_tokens"] > config["client"]["max_output_tokens"]):
            return None
        return {k: response["usage"][k] for k in ("input_tokens", "output_tokens",
                "cache_read_input_tokens", "cache_creation_input_tokens")}
    except Exception:
        return None


def scripted_worker(inputs, workspace, output, deadline, *, environment, emit):
    """Fixed worker body. Test injection is via module mocks, never CLI commands."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    bridge = output.parent / "bridge"
    result = {"schema": SCHEMA, "status": "failed", "model_calls": 0,
              "provider_charges_usd": 0, "scope": "scripted adapter qualification only"}
    try:
        config, plan, suite, baseline, responses = checked_inputs(inputs)
        gate = gate_environment(environment)
        if (not math.isfinite(deadline)
                or not 0 < deadline - time.monotonic() <= plan.limits.max_seconds):
            raise ValueError("Invalid inherited absolute deadline")
        # No actor/provider request occurs if the real sandbox cannot be established.
        result["isolation"] = kv.probe_isolation(output / "isolation", deadline,
            [str(Path(inputs).resolve()), str(bridge.resolve()), str(ROOT),
             f"/proc/{os.getppid()}/environ"])
        bench = workbench.VisibleWorkbench(plan, suite, baseline, output / "workbench")
        grant, sent = None, 0

        def authorize(value, inherited):
            nonlocal grant
            if inherited != deadline:
                return False
            grant = dict(value)
            atomic_write_json(bridge / "pending.json", grant)
            authorize_request(provider.canonical(grant).encode(), environment=gate,
                              timeout=max(0.001, deadline - time.monotonic()))
            return True

        def send(payload, spec, remaining):
            nonlocal sent
            if (grant is None or edit.digest(provider.canonical(payload).encode())
                    != grant["request_sha256"] or sent >= len(responses)):
                raise ValueError("No exact scripted request grant/response")
            value = responses[sent]
            sent += 1
            atomic_write_json(bridge / "complete.json", {
                "grant": grant, "usage": _known_usage(value, config, deadline)})
            return value

        # These values describe simulated request slots, not a fresh paid claim.
        requests = config["client"]["max_requests"]
        slots = edit.RequestSlots(config["plan_sha256"], {config["arm"]: requests},
            10170000, requests * 10170000, execution_id=config["execution_id"])
        answer = edit.run_edit_agent(workspace, plan, config["prompt"], config["model"],
            config["client"], deadline, emit, arm=config["arm"], slots=slots,
            authorize=authorize, send=send, visible_checks=bench.visible_checks,
            visible_benchmark=bench.visible_benchmark, retain_revision=bench.retain_revision,
            input_token_ceiling=config["input_token_ceiling"])
        source = answer.pop("artifact_source").encode("utf-8")
        final = output / "final"
        final.mkdir()
        (final / "candidate.py").write_bytes(source)
        atomic_write_json(final / "receipt.json", answer)
        result.update(status="completed", artifact=answer, simulated_requests=sent)
    except kv.SandboxUnavailable:
        result.update(status="inconclusive", reason="sandbox_unavailable")
    except provider.AgentError as error:
        result["reason"] = str(error)
    except Exception:
        result["reason"] = "scripted_worker_error"
    atomic_write_json(output / "result.json", result)
    return 0 if result["status"] == "completed" else 1


def run_supervised(inputs, workspace, output, deadline, *, admission=None, execute=execute_command):
    """SCRIPTED ONLY; shared private supervisor retains all deadline/admission semantics."""
    from tools.kv_worker_supervisor import supervise

    config, plan, _, _, _ = checked_inputs(inputs)

    def command(inputs, workspace, worker_output, inherited):
        return (sys.executable, "-I", str(Path(__file__).resolve()), "--offline-worker",
                "--inputs", str(inputs.resolve()), "--workspace", str(workspace.resolve()),
                "--output", str(worker_output), "--deadline", repr(inherited))

    result = supervise(config, plan, inputs, workspace, output, deadline, checkout=ROOT,
        command_factory=command,
        environment_factory=lambda gate: {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                                          "LANG": "C", **gate},
        admission=admission, execute=execute)
    result.update(schema=SCHEMA, simulated_slots_consumed=result.pop("slots_consumed"),
                  model_calls=0, provider_charges_usd=0)
    atomic_write_json(Path(output) / "supervision.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline-worker", action="store_true", required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deadline", type=float, required=True)
    args = parser.parse_args()
    # Only the inherited ephemeral request-gate capability is read. No provider
    # credential discovery/configuration or live-transport path exists here.
    environment = {key: os.environ.get(key, "") for key in ENV_KEYS}
    return scripted_worker(args.inputs, args.workspace, args.output, args.deadline,
        environment=environment, emit=lambda event: print(provider.canonical(event), flush=True))


if __name__ == "__main__":
    raise SystemExit(main())
