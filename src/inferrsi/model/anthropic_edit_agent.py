"""Fixed edit/check protocol for a trusted, externally supervised provider worker.

This is not a general coding agent or an execution backend. The caller supplies
trusted visible-check/benchmark callbacks; they must execute candidate bytes only
through the qualified, network-free artifact sandbox, never by host import/exec.
The worker itself must run under execute_command with the SAME absolute deadline:
in-process deadline checks reject late results but cannot interrupt blocked code.

RequestSlots is an additional in-process guard, NOT a durable spending authority.
The controller must first reserve/claim the complete plan in existing PR/daily
ledgers, bind one immutable campaign/attempt, and authorize every provider send.
There is deliberately no CLI, credential discovery, default transport or fallback.
"""

import hashlib
import json
import math
import os
import re
import stat
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from . import anthropic_agent as provider

KIND = provider.EDIT_KIND
CANDIDATE = "candidate.py"
REASONS = {"none", "check_failed", "candidate_error", "invalid_output", "deadline",
           "sandbox_unavailable", "source_changed", "measurement_incomplete"}
VERDICTS = {"PASS", "FAIL", "INCONCLUSIVE"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(value):
    return digest(provider.canonical(value).encode())


def _sha(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _positive(value, maximum=provider.MAX_RESPONSE):
    return type(value) is int and 0 < value <= maximum


def _path(value):
    if (type(value) is not str or not value or len(value) > 256 or "\\" in value
            or any(ord(c) < 32 for c in value)):
        raise ValueError("Invalid exposed path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) != value or value == ".":
        raise ValueError("Invalid exposed path")
    return value


@dataclass(frozen=True)
class ExposedFile:
    path: str
    bytes: int
    sha256: str

    def __post_init__(self):
        _path(self.path)
        if type(self.bytes) is not int or not 0 <= self.bytes <= provider.MAX_RESPONSE:
            raise ValueError("Invalid exposed file size")
        if not _sha(self.sha256):
            raise ValueError("Invalid exposed file digest")


def _read_regular(path, limit):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise provider.AgentError("workspace_symlink")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
            raise provider.AgentError("invalid_workspace_file")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise provider.AgentError("tool_read_limit")
    return data


def freeze_files(root, paths):
    """Explicit allowlist only. Do not discover/import a checkout or global K."""
    root = Path(root).absolute()
    names = tuple(sorted(_path(p) for p in paths))
    if len(set(names)) != len(names):
        raise ValueError("Duplicate exposed path")
    records = []
    for name in names:
        data = _read_regular(root / name, provider.MAX_RESPONSE)
        data.decode("utf-8")
        records.append(ExposedFile(name, len(data), digest(data)))
    return tuple(records)


@dataclass(frozen=True)
class EditLimits:
    max_source_bytes: int
    max_feedback_bytes: int
    max_writes: int
    max_checks: int
    max_benchmarks: int
    benchmark_repetitions: int
    max_seconds: int

    def __post_init__(self):
        if any(not _positive(value) for value in asdict(self).values()):
            raise ValueError("Explicit positive edit/check limits required")
        if self.max_source_bytes > 65536:
            raise ValueError("Candidate source exceeds artifact adapter capacity")


@dataclass(frozen=True)
class EditPlan:
    files: tuple[ExposedFile, ...]
    limits: EditLimits
    check_ids: tuple[str, ...]
    metric_key: str
    metric_unit: str
    direction: str
    callbacks_sha256: str

    def __post_init__(self):
        if (type(self.files) is not tuple or not self.files
                or any(type(item) is not ExposedFile for item in self.files)
                or type(self.limits) is not EditLimits):
            raise ValueError("Frozen manifest and limits required")
        names = [item.path for item in self.files]
        if names != sorted(set(names)) or not {"task.json", CANDIDATE} <= set(names):
            raise ValueError("Manifest must include task and candidate exactly once")
        if (type(self.check_ids) is not tuple or not self.check_ids
                or len(set(self.check_ids)) != len(self.check_ids)
                or any(type(k) is not str or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", k)
                       for k in self.check_ids)):
            raise ValueError("Frozen public development check identities required")
        if (self.direction not in {"minimize", "maximize"} or not _sha(self.callbacks_sha256)
                or any(type(v) is not str or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", v)
                       for v in (self.metric_key, self.metric_unit))):
            raise ValueError("Frozen benchmark/callback identity required")


def frozen_identity(plan, model, spec, input_token_ceiling):
    """Offline identity: exact code, transport/guard, callbacks, exposure and limits.

    callbacks_sha256 must bind the trusted visible adapters AND their transitive
    sandbox/executor/workload dependencies. The outer campaign freeze also binds
    the immutable implementation revision and qualified environment receipt.
    """
    provider.validate_spec({"name": model, "effort": "not_applicable"}, spec)
    if (type(plan) is not EditPlan or spec["kind"] != KIND
            or not _positive(input_token_ceiling, 2**31)):
        raise ValueError("Explicit edit/check plan and full input bound required")
    source = Path(__file__)
    return {"kind": KIND, "model": model, "spec": json.loads(provider.canonical(spec)),
            "plan": asdict(plan), "input_token_ceiling": input_token_ceiling,
            "sources": {name: digest(source.with_name(name).read_bytes()) for name in
                        (source.name, "anthropic_agent.py", "request_guard.py")},
            "request_policy": {"retries": 0, "tool_choice": "auto",
                               "sampling": "model_default", "thinking": "model_default"}}


class RequestSlots:
    """One nonrenewable allocation shared by the paired arms in this process.

    Burn before authorization; failed/uncertain grants or sends never refund a
    slot. Restart protection and durable charges belong to the outer controller.
    Integer micro-USD values come from the existing full-context reservation; no
    token conversion or new pricing estimate is performed here.
    """

    def __init__(self, plan_sha256, allocations, per_request_microusd, reserved_microusd,
                 *, execution_id):
        if (not _sha(plan_sha256) or type(allocations) is not dict or not allocations
                or type(execution_id) is not str
                or not re.fullmatch(r"[A-Za-z0-9._:-]{1,200}", execution_id)
                or any(type(k) is not str or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", k)
                       or not _positive(v) for k, v in allocations.items())
                or not _positive(per_request_microusd, 10**12)
                or type(reserved_microusd) is not int
                or reserved_microusd != sum(allocations.values()) * per_request_microusd):
            raise ValueError("Exact frozen request allocation/reservation required")
        self.plan_sha256 = plan_sha256
        self.execution_id = execution_id
        self.allocations = MappingProxyType(dict(allocations))
        self.per_request_microusd = per_request_microusd
        self.reserved_microusd = reserved_microusd
        self._used = dict.fromkeys(allocations, 0)
        self._started = set()
        self._stopped = False
        self._lock = threading.Lock()

    def start(self, arm, requests):
        with self._lock:
            if (self._stopped or arm in self._started or arm not in self.allocations
                    or requests != self.allocations[arm]):
                raise provider.AgentError("request_allocation_unavailable")
            self._started.add(arm)

    def consume(self, arm, request_sha256, actor_sha256):
        with self._lock:
            if (self._stopped or arm not in self._started or not _sha(request_sha256)
                    or not _sha(actor_sha256) or self._used[arm] >= self.allocations[arm]):
                raise provider.AgentError("request_limit")
            self._used[arm] += 1
            return {"plan_sha256": self.plan_sha256, "execution_id": self.execution_id,
                    "arm": arm, "slot": self._used[arm],
                    "request_sha256": request_sha256, "actor_sha256": actor_sha256,
                    "reserved_microusd": self.per_request_microusd}

    def stop(self):
        with self._lock:
            self._stopped = True

    def usage(self):
        with self._lock:
            return dict(self._used)


class _Workspace:
    def __init__(self, root, plan, max_read_bytes):
        self.root = Path(root).absolute()
        self.plan = plan
        self.expected = {f.path: (f.bytes, f.sha256) for f in plan.files}
        self.max_read_bytes = max_read_bytes
        self.revision = 0
        self.check_receipt = self.benchmark_receipt = None
        self.verify()

    def verify(self):
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise provider.AgentError("workspace_symlink")
        expected_dirs = {p.as_posix() for name in self.expected
                         for p in PurePosixPath(name).parents if p.as_posix() != "."}
        seen = set()
        for path in self.root.rglob("*"):
            name = path.relative_to(self.root).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISDIR(mode) and name in expected_dirs:
                continue
            if not stat.S_ISREG(mode) or name not in self.expected:
                raise provider.AgentError("protected_workspace_changed")
            data = _read_regular(path, provider.MAX_RESPONSE)
            if (len(data), digest(data)) != self.expected[name]:
                raise provider.AgentError("protected_workspace_changed")
            seen.add(name)
        if seen != set(self.expected):
            raise provider.AgentError("protected_workspace_changed")

    def read(self, name):
        self.verify()
        if type(name) is not str or name not in self.expected:
            raise provider.AgentError("unexposed_path")
        return _read_regular(self.root / name, self.max_read_bytes).decode("utf-8")

    def source(self):
        self.verify()
        data = _read_regular(self.root / CANDIDATE, self.plan.limits.max_source_bytes)
        if not data:
            raise provider.AgentError("invalid_candidate")
        data.decode("utf-8")
        return data

    def write(self, source):
        self.verify()
        if type(source) is not str:
            raise provider.AgentError("invalid_candidate")
        data = source.encode("utf-8")
        if not data or len(data) > self.plan.limits.max_source_bytes:
            raise provider.AgentError("candidate_bytes_limit")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.root, prefix=".candidate-", delete=False,
            ) as f:
                temporary = Path(f.name)
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, self.root / CANDIDATE)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self.expected[CANDIDATE] = (len(data), digest(data))
        self.revision += 1
        self.check_receipt = self.benchmark_receipt = None
        self.verify()
        return {"artifact": CANDIDATE, "revision": self.revision, "sha256": digest(data)}


def _feedback(kind, value, plan):
    """Only fixed public result fields enter model history; never raw logs/paths."""
    if type(value) is not dict:
        raise provider.AgentError("invalid_visible_feedback")
    common = {"verdict", "reason"}
    fields = common | ({"checks"} if kind == "checks" else {
        "baseline_values", "candidate_values", "quality_verdict", "improvement_pct"})
    if (set(value) != fields or value["verdict"] not in VERDICTS
            or value["reason"] not in REASONS):
        raise provider.AgentError("invalid_visible_feedback")
    if kind == "checks":
        checks = value["checks"]
        if (type(checks) is not dict or set(checks) - set(plan.check_ids)
                or any(type(v) is not bool for v in checks.values())
                or (value["verdict"] != "INCONCLUSIVE" and set(checks) != set(plan.check_ids))
                or (value["verdict"] == "PASS" and not all(checks.values()))
                or (value["verdict"] == "FAIL" and all(checks.values()))):
            raise provider.AgentError("invalid_visible_feedback")
    else:
        groups = [value[k] for k in ("baseline_values", "candidate_values")]
        improvement = value["improvement_pct"]
        if (value["quality_verdict"] not in VERDICTS
                or any(type(g) is not list or len(g) > plan.limits.benchmark_repetitions
                       or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0
                              for v in g) for g in groups)
                or (improvement is not None and (type(improvement) not in (int, float)
                                                or not math.isfinite(improvement)))
                or (value["verdict"] != "INCONCLUSIVE"
                    and any(len(g) != plan.limits.benchmark_repetitions for g in groups))
                or (value["verdict"] == "PASS" and value["quality_verdict"] != "PASS")):
            raise provider.AgentError("invalid_visible_feedback")
    raw = provider.canonical(value).encode()
    if len(raw) > plan.limits.max_feedback_bytes:
        raise provider.AgentError("feedback_bytes_limit")
    return json.loads(raw)


def _tools():
    def tool(name, properties, description):
        return {"name": name, "description": description, "input_schema": {
            "type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}}
    return [
        tool("read_file", {"path": {"type": "string"}}, "Read one exposed UTF-8 file."),
        tool("write_candidate", {"source": {"type": "string"}},
             "Replace candidate.py only; invalidates previous checks and measurements."),
        tool("run_visible_checks", {},
             "Check current candidate on frozen public development cases."),
        tool("run_visible_benchmark", {},
             "Measure current candidate versus the visible starter on the fixed public workload."),
        tool("submit_candidate", {},
             "Freeze current candidate with its current check/benchmark receipts.")]


def run_edit_agent(workspace, plan, prompt, model, spec, deadline, emit, *, arm,
                   slots, authorize, send, visible_checks, visible_benchmark,
                   retain_revision, input_token_ceiling, clock=time.monotonic):
    """Run one arm with a non-resetting deadline and no automatic retry.

    authorize(grant, absolute_deadline) must return True only for a fresh, trusted
    pre-send grant. Both callbacks receive (immutable_source_bytes, deadline).
    They are trusted visible-only adapters, never model-selected commands.
    retain_revision(source_bytes, fixed_metadata, deadline) must return True after
    retaining each exact revision outside the exposed workspace. No raw source
    enters the trace. It is trusted storage, never a candidate execution hook.
    The integrating worker must be killed by execute_command at this deadline.
    """
    provider.validate_spec({"name": model, "effort": "not_applicable"}, spec)
    if spec["kind"] != KIND or type(plan) is not EditPlan or type(slots) is not RequestSlots:
        raise ValueError("Separate edit/check plan, protocol and request allocation required")
    if (type(deadline) not in (int, float) or not math.isfinite(deadline)
            or not _positive(input_token_ceiling, 2**31)
            or any(not callable(f) for f in (authorize, send, visible_checks, visible_benchmark,
                                            retain_revision))):
        raise ValueError("Explicit deadline, token bound and trusted callbacks required")
    spec = json.loads(provider.canonical(spec))
    identity = fingerprint(frozen_identity(plan, model, spec, input_token_ceiling))
    binding = {"plan_sha256": slots.plan_sha256, "execution_id": slots.execution_id, "arm": arm}
    totals = {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}
    counts = dict.fromkeys(("write_candidate", "run_visible_checks", "run_visible_benchmark"), 0)
    bounds = dict(zip(counts, (plan.limits.max_writes, plan.limits.max_checks,
                              plan.limits.max_benchmarks)))
    ids, task_read_at, tool_count = set(), None, 0
    unaccounted_request = False

    def remaining():
        left = deadline - clock()
        if left <= 0:
            raise provider.AgentError("timeout")
        return left

    def retain(state):
        source = state.source()
        metadata = {**binding, "artifact": CANDIDATE, "revision": state.revision,
                    "sha256": digest(source), "actor_sha256": identity}
        try:
            if retain_revision(source, dict(metadata), deadline) is not True:
                raise ValueError("not retained")
        except Exception:
            raise provider.AgentError("revision_retention_error") from None
        remaining()
        state.verify()
        emit({"type": "edit.artifact", **metadata, "bytes": len(source)})

    try:
        if deadline - clock() > plan.limits.max_seconds:
            raise provider.AgentError("deadline_exceeds_frozen_limit")
        remaining()
        slots.start(arm, spec["max_requests"])
        state = _Workspace(workspace, plan, spec["max_read_bytes"])
        state.source()
        emit({"type": "edit.protocol", "client_kind": KIND, "actor_sha256": identity,
              **binding,
              "manifest_sha256": fingerprint([asdict(f) for f in plan.files])})
        retain(state)
        messages = [{"role": "user", "content": prompt + "\nRead task.json first. "
                    "Only candidate.py is editable. Use fixed visible checks and measurements; "
                    "finish with submit_candidate. Exposed paths: "
                    + provider.canonical([f.path for f in plan.files])}]
        for number in range(1, spec["max_requests"] + 1):
            remaining()
            state.verify()
            payload = {"model": model, "max_tokens": spec["max_output_tokens"], "stream": False,
                       "tools": _tools(), "tool_choice": {"type": "auto"}, "messages": messages}
            raw = provider.canonical(payload).encode()
            if len(raw) > spec["max_request_bytes"]:
                raise provider.AgentError("request_bytes_limit")
            grant = slots.consume(arm, digest(raw), identity)
            emit({"type": "edit.slot", **grant})
            try:
                if authorize(dict(grant), deadline) is not True:
                    raise ValueError("denied")
            except Exception:
                slots.stop()
                raise provider.AgentError("request_authorization_denied") from None
            remaining()
            emit({"type": "agent.request", "request": number, "request_bytes": len(raw),
                  "request_sha256": digest(raw)})
            unaccounted_request = True
            try:
                response = send(payload, spec, remaining())
            except Exception:
                slots.stop()
                raise provider.AgentError("provider_transport_error") from None
            remaining()
            if (type(response) is not dict or response.get("type") != "message"
                    or response.get("role") != "assistant" or response.get("model") != model
                    or response.get("stop_reason") != "tool_use"
                    or type(response.get("content")) is not list
                    or any(not provider.valid_content_block(c) for c in response["content"])
                    or len(provider.canonical(response).encode()) > provider.MAX_RESPONSE):
                raise provider.AgentError("incompatible_response")
            usage = provider.token_usage(response.get("usage"))
            if usage["input_tokens"] > input_token_ceiling:
                raise provider.AgentError("input_token_limit")
            if usage["output_tokens"] > spec["max_output_tokens"]:
                raise provider.AgentError("output_token_limit")
            unaccounted_request = False
            for key in totals:
                totals[key] += usage[key]
            emit({"type": "agent.response", "request": number, "usage": usage,
                  "provider_model": model, "stop_reason": "tool_use"})
            calls = [c for c in response["content"] if c["type"] == "tool_use"]
            tool_count += len(calls)
            if not calls or tool_count > spec["max_tool_calls"]:
                raise provider.AgentError("tool_call_limit")
            new_ids = [c.get("id") for c in calls]
            if (any(type(i) is not str or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", i)
                    for i in new_ids) or len(set(new_ids)) != len(new_ids)
                    or ids.intersection(new_ids)):
                raise provider.AgentError("invalid_tool_call")
            ids.update(new_ids)
            results = []
            for call in calls:
                remaining()
                name, args = call.get("name"), call.get("input")
                expected = {"path"} if name == "read_file" else (
                    {"source"} if name == "write_candidate" else set())
                if (name not in {t["name"] for t in _tools()} or type(args) is not dict
                        or set(args) != expected):
                    raise provider.AgentError("unsupported_tool")
                if name != "read_file" and (task_read_at is None or task_read_at >= number):
                    raise provider.AgentError("task_not_read")
                if name in counts:
                    counts[name] += 1
                    if counts[name] > bounds[name]:
                        raise provider.AgentError("tool_call_limit")
                state.verify()
                if name == "read_file":
                    value = state.read(args["path"])
                    if args["path"] == "task.json":
                        task_read_at = number
                elif name == "write_candidate":
                    value = state.write(args["source"])
                    retain(state)
                elif name in {"run_visible_checks", "run_visible_benchmark"}:
                    source = state.source()
                    kind = "checks" if name == "run_visible_checks" else "benchmark"
                    callback = visible_checks if kind == "checks" else visible_benchmark
                    try:
                        feedback = callback(source, deadline)
                    except Exception:
                        raise provider.AgentError("visible_callback_error") from None
                    remaining()
                    state.verify()
                    feedback = _feedback(kind, feedback, plan)
                    value = {**binding, "artifact_sha256": digest(source),
                             "revision": state.revision, "kind": kind, "feedback": feedback}
                    value["receipt_sha256"] = fingerprint({**value, "actor_sha256": identity})
                    if kind == "checks":
                        state.check_receipt = value["receipt_sha256"]
                    else:
                        state.benchmark_receipt = value["receipt_sha256"]
                else:
                    if len(calls) != 1 or not state.check_receipt or not state.benchmark_receipt:
                        raise provider.AgentError("stale_or_missing_receipt")
                    source = state.source()
                    remaining()
                    answer = {**binding, "artifact": CANDIDATE, "sha256": digest(source),
                              "revision": state.revision, "actor_sha256": identity,
                              "check_receipt": state.check_receipt,
                              "benchmark_receipt": state.benchmark_receipt}
                    emit({"type": "agent.tool", "request": number, "name": name, **answer})
                    emit({"type": "agent.completed", "usage": totals, "requests": number})
                    # Return the exact checked byte snapshot, not merely a mutable
                    # pathname for a later consumer to reopen. Traces omit source.
                    return {**answer, "artifact_source": source.decode("utf-8")}
                remaining()
                content = value if type(value) is str else provider.canonical(value)
                # Read-file has its separate frozen byte cap; all structured feedback
                # including receipt wrappers is capped before entering the transcript.
                cap = (spec["max_read_bytes"] if name == "read_file"
                       else plan.limits.max_feedback_bytes)
                if len(content.encode()) > cap:
                    raise provider.AgentError("feedback_bytes_limit")
                event = {"type": "agent.tool", "request": number, "name": name,
                         "result_sha256": digest(content.encode()), "bytes": len(content.encode()),
                         "artifact_sha256": state.expected[CANDIDATE][1],
                         "revision": state.revision}
                if name in {"run_visible_checks", "run_visible_benchmark"}:
                    event["receipt"] = value
                emit(event)
                results.append({"type": "tool_result", "tool_use_id": call["id"],
                                "content": content})
            messages += [{"role": "assistant", "content": response["content"]},
                         {"role": "user", "content": results}]
        raise provider.AgentError("request_limit")
    except provider.AgentError as error:
        if unaccounted_request:
            slots.stop()
        emit({"type": "agent.failed", "reason": str(error)})
        raise
    except Exception:
        if unaccounted_request:
            slots.stop()
        emit({"type": "agent.failed", "reason": "edit_agent_error"})
        raise provider.AgentError("edit_agent_error") from None
    except BaseException:
        # A controller that catches cancellation must not continue another arm,
        # especially when a request was sent but its usage was never observed.
        slots.stop()
        emit({"type": "agent.failed", "reason": "interrupted"})
        raise
