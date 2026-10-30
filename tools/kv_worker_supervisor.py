"""Private trusted worker supervision, shared by scripted and fixed live launchers.

Factories are reviewed Python callbacks, never CLI/config/model command inputs.
No credential discovery, provider transport, ledger bootstrap or execution CLI.
"""

import json
import math
import time
from pathlib import Path

from inferrsi.harness import kv_reclamation as kv
from inferrsi.infra.artifacts import atomic_write_json
from inferrsi.infra.executors.local import execute_command
from inferrsi.model import anthropic_agent as provider
from inferrsi.model import anthropic_edit_agent as edit
from inferrsi.model.request_guard import ENV_KEYS, authorization_broker


def _read_json(path, limit):
    return json.loads(kv.read_regular(Path(path), limit), object_pairs_hook=provider.unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def supervise(config, plan, inputs, workspace, output, deadline, *, checkout,
              command_factory, environment_factory, admission=None, execute=execute_command):
    """One exact inherited deadline and parent-owned grant/completion latch."""
    if (not math.isfinite(deadline)
            or not 0 < deadline - time.monotonic() <= plan.limits.max_seconds):
        raise ValueError("Invalid inherited absolute deadline")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    bridge = output / "bridge"
    bridge.mkdir(mode=0o700)
    pending, consumed, failed = None, 0, False
    completions = []

    def complete():
        nonlocal pending, failed
        if pending is None:
            return
        try:
            value = _read_json(bridge / "complete.json", 8192)
            if (type(value) is not dict or set(value) != {"grant", "usage"}
                    or value["grant"] != pending):
                raise ValueError("Wrong usage receipt")
            if admission is not None:
                admission.complete(pending, value["usage"])
            elif value["usage"] is None:
                raise ValueError("Unknown simulated usage")
            else:
                usage = provider.token_usage(value["usage"])
                if (usage["input_tokens"] > config["input_token_ceiling"]
                        or usage["output_tokens"] > config["client"]["max_output_tokens"]):
                    raise ValueError("Out-of-bound simulated usage")
            completions[-1].update(status="known",
                usage={k: value["usage"][k] for k in ("input_tokens", "output_tokens",
                       "cache_read_input_tokens", "cache_creation_input_tokens")})
            pending = None
            (bridge / "complete.json").unlink()
        except Exception:
            failed = True
            if admission is not None:
                # Unknown, lost and malformed completion is never a refund.
                try:
                    admission.complete(pending, None)
                except Exception:
                    pass
            raise ValueError("Unresolved request completion") from None

    def check():
        nonlocal pending, consumed, failed
        try:
            complete()
            value = _read_json(bridge / "pending.json", 8192)
            expected = {"plan_sha256", "execution_id", "arm", "slot", "request_sha256",
                        "actor_sha256", "reserved_microusd"}
            if (failed or time.monotonic() >= deadline or type(value) is not dict
                    or set(value) != expected or value["plan_sha256"] != config["plan_sha256"]
                    or value["execution_id"] != config["execution_id"]
                    or value["arm"] != config["arm"]
                    or value["actor_sha256"] != config["actor_sha256"]
                    or value["slot"] != consumed + 1 or not edit._sha(value["request_sha256"])
                    or value["reserved_microusd"] != 10170000
                    or consumed >= config["client"]["max_requests"]):
                raise ValueError("Wrong bounded grant")
            consumed += 1  # Burn before any uncertain live admission check.
            pending = value
            completions.append({"grant": dict(value), "status": "unresolved", "usage": None})
            if admission is not None and admission.authorize(value, deadline) is not True:
                raise ValueError("Admission denied")
            return True
        except Exception:
            failed = True
            raise ValueError("Scripted request authorization denied") from None

    try:
        if admission is not None:
            admission.start_arm(config["arm"], deadline)
        context = f"{config['plan_sha256']}:{config['execution_id']}:{config['arm']}"
        with authorization_broker(check, config["client"]["max_requests"], context=context) as gate:
            environment = environment_factory(gate)
            allowed = {"PATH", "LANG", provider.KEY_ENV, *ENV_KEYS}
            if (type(environment) is not dict or set(environment) - allowed
                    or any(environment.get(k) != v for k, v in gate.items())):
                raise ValueError("Worker environment exceeds fixed allowlist")
            command = command_factory(Path(inputs), Path(workspace), output / "worker", deadline)
            record = execute(command, checkout, output / "executor", deadline,
                             environment=environment)
            try:
                complete()
            except ValueError:
                pass
        # The executor returns cancellation/timeout records instead of raising.
        # A missing response/cleanup outcome cannot authorize the following arm.
        try:
            worker = _read_json(output / "worker/result.json", 1024 * 1024)
        except (ValueError, OSError):
            worker = {"status": "missing", "reason": "worker_result_unavailable"}
        returncode = record.get("returncode")
        if (record.get("status") in {"cancelled", "timeout", "error"}
                or (type(returncode) is int and returncode < 0)
                or type(worker) is not dict or worker.get("status") not in {
                    "completed", "failed", "inconclusive"}):
            failed = True
            if admission is not None:
                admission.close()
        if admission is not None and not failed:
            admission.finish_arm(config["arm"])
    except BaseException:
        if admission is not None:
            admission.close()
        raise
    result = {"schema": "kv-worker-supervision-v1", "execution": record, "worker": worker,
              "request_completion_known": not failed and pending is None,
              "slots_consumed": consumed, "completions": completions}
    atomic_write_json(output / "supervision.json", result)
    return result

