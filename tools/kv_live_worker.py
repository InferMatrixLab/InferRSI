"""Trusted fixed KV live worker. Not a candidate executor or scripted-CLI switch.

Only a reviewed main controller may supply its frozen inputs and runtime key.
The worker has no GitHub authority; submitted source executes only via kv.invoke.
"""

import argparse
import os
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))

from inferrsi.harness import kv_edit_workbench as workbench  # noqa: E402
from inferrsi.harness import kv_reclamation as kv  # noqa: E402
from inferrsi.infra.artifacts import atomic_write_json  # noqa: E402
from inferrsi.infra.executors.local import execute_command  # noqa: E402
from inferrsi.model import anthropic_agent as provider  # noqa: E402
from inferrsi.model import anthropic_edit_agent as edit  # noqa: E402
from inferrsi.model.request_guard import ENV_KEYS, authorize_request, gate_environment  # noqa: E402
from tools import kv_edit_pilot as scripted  # noqa: E402
from tools.kv_worker_supervisor import supervise  # noqa: E402

SCHEMA = "kv-live-worker-v1"
FIELDS = {"schema", "arm", "model", "client", "edit_plan", "input_token_ceiling",
          "suite_sha256", "baseline_sha256", "actor_sha256", "dependencies", "prompt"}


def dependencies():
    return {**scripted.dependencies(),
            "tools/kv_live_worker.py": edit.digest(Path(__file__).read_bytes())}


def configuration(workspace, plan, suite, baseline, *, arm, model, spec, prompt):
    """Offline freeze constructor; no root-plan digest cycle or credential access."""
    if (arm not in {"A2", "A3"} or type(prompt) is not str
            or edit.freeze_files(workspace, [f.path for f in plan.files]) != plan.files
            or kv.source_bytes(Path(workspace) / "candidate.py") != baseline):
        raise ValueError("Wrong frozen live actor inputs")
    deps = dependencies()
    binding = {"dependencies": deps, "suite_sha256": edit.digest(suite.serialized),
               "baseline_sha256": edit.digest(baseline), "prompt": prompt}
    plan = replace(plan, callbacks_sha256=edit.fingerprint(binding))
    identity = edit.frozen_identity(plan, model, spec, 1000000)
    return {"schema": SCHEMA, "arm": arm, "model": model, "client": spec,
            "edit_plan": asdict(plan), "input_token_ceiling": 1000000,
            "suite_sha256": binding["suite_sha256"], "baseline_sha256": binding["baseline_sha256"],
            "actor_sha256": edit.fingerprint(identity), "dependencies": deps, "prompt": prompt}


def checked_inputs(inputs):
    inputs = Path(inputs)
    config = scripted._read_json(inputs / "worker.json", 2 * 1024 * 1024)
    if (type(config) is not dict or set(config) != FIELDS or config["schema"] != SCHEMA
            or config["arm"] not in {"A2", "A3"} or config["dependencies"] != dependencies()
            or config["model"] != "claude-opus-5-5" or config["input_token_ceiling"] != 1000000
            or config["client"].get("max_requests") != 8
            or config["client"].get("max_output_tokens") != 4096):
        raise ValueError("Live worker identity or limits changed")
    plan = scripted._plan(config["edit_plan"])
    binding = {k: config[k] for k in ("dependencies", "suite_sha256", "baseline_sha256", "prompt")}
    if (plan.callbacks_sha256 != edit.fingerprint(binding)
            or edit.fingerprint(edit.frozen_identity(plan, config["model"], config["client"],
                config["input_token_ceiling"])) != config["actor_sha256"]):
        raise ValueError("Live actor callback/protocol identity changed")
    suite = kv.read_regular(inputs / "suite.json", 16 * 1024 * 1024)
    baseline = kv.source_bytes(inputs / "baseline.py")
    if (edit.digest(suite) != config["suite_sha256"]
            or edit.digest(baseline) != config["baseline_sha256"]):
        raise ValueError("Live visible suite/baseline changed")
    run = scripted._read_json(inputs / "binding.json", 8192)
    if (type(run) is not dict or set(run) != {"plan_sha256", "execution_id"}
            or not edit._sha(run["plan_sha256"]) or type(run["execution_id"]) is not str):
        raise ValueError("Invalid outer binding")
    return {**config, **run}, plan, workbench.VisibleSuite(suite), baseline


class GrantedSender:
    """One IPC authorization and one exact HTTP attempt per consumed grant."""

    def __init__(self, config, bridge, deadline, *, key, gate,
                 transport=provider.send_message, authorize_ipc=authorize_request):
        self.config, self.bridge, self.deadline = config, Path(bridge), deadline
        self.key, self.gate = key, gate_environment(gate)
        self.transport, self.authorize_ipc = transport, authorize_ipc
        self.grant, self.ready, self.sent, self.attempts = None, False, False, 0

    def authorize(self, grant, deadline):
        if (deadline != self.deadline or time.monotonic() >= deadline
                or (self.grant is not None and not self.sent)):
            return False
        self.grant, self.ready, self.sent = dict(grant), False, False
        atomic_write_json(self.bridge / "pending.json", self.grant)
        self.authorize_ipc(provider.canonical(grant).encode(), environment=self.gate,
                           timeout=max(0.001, deadline - time.monotonic()))
        self.ready = True
        return True

    def send(self, payload, spec, remaining):
        left = self.deadline - time.monotonic()
        if (not self.ready or self.sent or self.grant is None or left <= 0
                or spec != self.config["client"]
                or edit.digest(provider.canonical(payload).encode()) != self.grant["request_sha256"]
                or self.attempts >= self.config["client"]["max_requests"]):
            raise provider.AgentError("request_without_exact_grant")
        self.sent = True  # Burn BEFORE transport; exceptions never permit resend.
        self.attempts += 1
        try:
            # authorize() already consumed the sole gate. Explicit empty runtime
            # prevents send_message's implicit environment gate from double-counting.
            value = self.transport(payload, spec, self.key, min(remaining, left),
                                   environment={}, require_authorization=False)
        except Exception:
            atomic_write_json(self.bridge / "complete.json", {"grant": self.grant, "usage": None})
            raise provider.AgentError("provider_transport_error") from None
        atomic_write_json(self.bridge / "complete.json", {"grant": self.grant,
            "usage": scripted._known_usage(value, self.config, self.deadline)})
        return value


def live_worker(inputs, workspace, output, deadline, *, environment, emit,
                transport=provider.send_message):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    result = {"schema": SCHEMA, "status": "failed", "provider_attempts": 0,
              "scope": "one synthetic editing feasibility arm; no efficacy claim"}
    sender = None
    try:
        config, plan, suite, baseline = checked_inputs(inputs)
        safe = provider.execution_environment(environment)
        bridge = output.parent / "bridge"
        result["isolation"] = kv.probe_isolation(output / "isolation", deadline,
            [str(Path(inputs).resolve()), str(bridge.resolve()), str(ROOT),
             f"/proc/{os.getppid()}/environ"])
        bench = workbench.VisibleWorkbench(plan, suite, baseline, output / "workbench")
        sender = GrantedSender(config, bridge, deadline, key=safe[provider.KEY_ENV],
                               gate=safe, transport=transport)
        slots = edit.RequestSlots(config["plan_sha256"], {config["arm"]: 8},
            10170000, 81360000, execution_id=config["execution_id"])
        (output / "feedback").mkdir()
        feedback_count = 0

        def retain_feedback(event):
            nonlocal feedback_count
            if event.get("name") in {"run_visible_checks", "run_visible_benchmark"}:
                receipt = event["receipt"]
                feedback_count += 1
                if (feedback_count > plan.limits.max_checks + plan.limits.max_benchmarks
                        or len(provider.canonical(receipt).encode())
                        > plan.limits.max_feedback_bytes):
                    raise provider.AgentError("feedback_retention_limit")
                atomic_write_json(output / "feedback" / f"{feedback_count:04d}.json", receipt)
            emit(event)

        answer = edit.run_edit_agent(workspace, plan, config["prompt"], config["model"],
            config["client"], deadline, retain_feedback, arm=config["arm"], slots=slots,
            authorize=sender.authorize, send=sender.send, visible_checks=bench.visible_checks,
            visible_benchmark=bench.visible_benchmark, retain_revision=bench.retain_revision,
            input_token_ceiling=1000000)
        source = answer.pop("artifact_source").encode("utf-8")
        final = output / "final"
        final.mkdir()
        with (final / "candidate.py").open("xb") as stream:
            stream.write(source)
            stream.flush()
            os.fsync(stream.fileno())
        atomic_write_json(final / "receipt.json", answer)
        if time.monotonic() >= deadline:
            raise provider.AgentError("timeout")
        result.update(status="completed", artifact=answer)
    except kv.SandboxUnavailable:
        result.update(status="inconclusive", reason="sandbox_unavailable")
    except provider.AgentError as error:
        result["reason"] = str(error)
    except Exception:
        result["reason"] = "live_worker_error"
    result["provider_attempts"] = sender.attempts if sender else 0
    atomic_write_json(output / "result.json", result)
    return 0 if result["status"] == "completed" else 1


def run_supervised(inputs, workspace, output, deadline, *, admission, key,
                   execute=execute_command):
    if admission is None:
        raise ValueError("Live worker requires parent-owned durable admission")
    config, plan, _, _ = checked_inputs(inputs)
    safe = provider.execution_environment({provider.KEY_ENV: key, "PATH": os.defpath, "LANG": "C"})

    def command(inputs, workspace, worker_output, inherited):
        return (sys.executable, "-I", str(Path(__file__).resolve()),
                "--inputs", str(inputs.resolve()), "--workspace", str(workspace.resolve()),
                "--output", str(worker_output), "--deadline", repr(inherited))

    return supervise(config, plan, inputs, workspace, output, deadline, checkout=ROOT,
        command_factory=command, environment_factory=lambda gate: {
            k: v for k, v in {**safe, **gate}.items() if k != "PYTHONUTF8"},
        admission=admission, execute=execute)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deadline", type=float, required=True)
    args = parser.parse_args()
    environment = {k: os.environ.get(k, "") for k in (*ENV_KEYS, provider.KEY_ENV)}
    return live_worker(args.inputs, args.workspace, args.output, args.deadline,
        environment=environment, emit=lambda e: print(provider.canonical(e), flush=True))


if __name__ == "__main__":
    raise SystemExit(main())
