"""Bounded Messages read/submit agent for offline contract validation.

The comparison controller may freeze this opt-in identity. Live execution stays
unavailable until verified pricing/cap controls and credential wiring are reviewed.
No credentials are discovered here; transport receives an explicit runtime key.
"""

import hashlib
import json
import math
import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError

KIND = "anthropic-messages-agent-v1"
ENDPOINT = "https://yibuapi.com/v1/messages"
SOURCE = "src/inferrsi/model/anthropic_agent.py"
MAX_RESPONSE = 1024 * 1024
LIVE_BLOCKER = ("Live provider execution requires reviewed pricing/cap controls "
                "and credential wiring")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def validate_spec(model, spec):
    fields = {"kind", "provider", "endpoint", "api_version", "max_requests",
              "max_output_tokens", "max_request_bytes", "max_read_bytes", "max_tool_calls"}
    if not isinstance(spec, dict) or set(spec) != fields:
        raise ValueError("Unknown or missing agent setting")
    if (spec["kind"] != KIND or spec["provider"] != "yibuapi" or spec["endpoint"] != ENDPOINT
            or spec["api_version"] != "2023-06-01"):
        raise ValueError("Unsupported provider protocol identity")
    if (not isinstance(model, dict) or not isinstance(model.get("name"), str)
            or model.get("effort") != "not_applicable"
            or not re.fullmatch(r"claude-[a-zA-Z0-9._-]{1,100}", model.get("name", ""))):
        raise ValueError("An explicit Claude model and no Codex effort mapping are required")
    for field in ("max_requests", "max_output_tokens", "max_request_bytes",
                  "max_read_bytes", "max_tool_calls"):
        if type(spec[field]) is not int or not 0 < spec[field] <= MAX_RESPONSE:
            raise ValueError("Agent limits must be bounded positive integers")
    if spec["max_requests"] < 2:
        raise ValueError("A task-read/tool-result round trip is required")


def validate_schema(schema):
    # This small vocabulary covers the existing audit/extract output contract.
    allowed = {"type", "properties", "required", "additionalProperties", "items",
               "enum", "description", "title"}
    if not isinstance(schema, dict) or set(schema) - allowed or "type" not in schema:
        raise ValueError("Unsupported output-schema vocabulary")
    types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
    if not types or any(t not in ("object", "array", "string", "number", "integer",
                                  "boolean", "null") for t in types):
        raise ValueError("Unsupported output-schema type")
    properties = schema.get("properties", {})
    if not isinstance(properties, dict) or any(not isinstance(k, str) for k in properties):
        raise ValueError("Invalid output-schema properties")
    for child in properties.values():
        validate_schema(child)
    if "items" in schema:
        validate_schema(schema["items"])
    required = schema.get("required", [])
    if (not isinstance(required, list) or any(not isinstance(k, str) for k in required)
            or len(set(required)) != len(required) or set(required) - properties.keys()):
        raise ValueError("Invalid required output fields")
    if "additionalProperties" in schema and type(schema["additionalProperties"]) is not bool:
        raise ValueError("Unsupported additional-properties schema")
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        raise ValueError("Invalid output enum")
    canonical(schema)


def matches_schema(value, schema):
    kinds = {"object": type(value) is dict, "array": type(value) is list,
             "string": type(value) is str, "number": type(value) in (int, float),
             "integer": type(value) is int, "boolean": type(value) is bool,
             "null": value is None}
    types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
    if not any(kinds[t] for t in types):
        return False
    if type(value) is float and not math.isfinite(value):
        return False
    if "enum" in schema and canonical(value) not in [canonical(v) for v in schema["enum"]]:
        return False
    if type(value) is dict:
        properties = schema.get("properties", {})
        if set(schema.get("required", [])) - value.keys():
            return False
        if schema.get("additionalProperties") is False and value.keys() - properties.keys():
            return False
        return all(k not in properties or matches_schema(v, properties[k])
                   for k, v in value.items())
    return (type(value) is not list or "items" not in schema
            or all(matches_schema(v, schema["items"]) for v in value))


@dataclass(frozen=True)
class AnthropicAgentClient:
    model: str
    spec: dict
    timeout_seconds: float

    def frozen_identity(self):
        validate_spec({"name": self.model, "effort": "not_applicable"}, self.spec)
        return {"settings": json.loads(canonical(self.spec)),
                "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "runtime_state": "offline_only"}

    @staticmethod
    def require_live_readiness():
        # No environment variable or self-declared quota can authorize unknown spend.
        raise ValueError(LIVE_BLOCKER)

    def command(self, workspace, final, schema, prompt):
        self.require_live_readiness()

    @staticmethod
    def trace_metrics(path):
        return trace_metrics(path)


class AgentError(Exception):
    """Only fixed reason codes cross the evidence boundary."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def send_message(payload, spec, key, timeout):
    """One non-streaming request. Callers must supply approved runtime credentials."""
    validate_spec({"name": payload.get("model"), "effort": "not_applicable"}, spec)
    if not isinstance(key, str) or not key or not key.isascii() or any(c.isspace() for c in key):
        raise AgentError("invalid_credential_shape")
    raw = canonical(payload).encode()
    if len(raw) > spec["max_request_bytes"]:
        raise AgentError("request_bytes_limit")
    if key in raw.decode():
        raise AgentError("credential_in_payload")
    request = urllib.request.Request(spec["endpoint"], data=raw, method="POST", headers={
        "x-api-key": key, "anthropic-version": spec["api_version"],
        "Content-Type": "application/json", "Accept": "application/json",
        "User-Agent": "inferrsi-anthropic-agent/1"})
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=timeout) as response:
            data = response.read(MAX_RESPONSE + 1)
    except HTTPError as error:
        code = error.code if type(error.code) is int else 0
        error.close()
        raise AgentError("http_" + str(code)) from None
    except Exception:
        raise AgentError("transport_error") from None
    if len(data) > MAX_RESPONSE:
        raise AgentError("response_bytes_limit")
    try:
        result = json.loads(data, object_pairs_hook=unique_object,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if key in canonical(result):
            raise AgentError("credential_echo")
        return result
    except AgentError:
        raise
    except Exception:
        raise AgentError("invalid_response_json") from None


def token_usage(value):
    keys = ("input_tokens", "output_tokens", "cache_read_input_tokens",
            "cache_creation_input_tokens")
    if not isinstance(value, dict) or any(
            type(value.get(k)) is not int or value[k] < 0 for k in keys):
        raise AgentError("unknown_usage")
    return {"input_tokens": value["input_tokens"] + value["cache_read_input_tokens"]
            + value["cache_creation_input_tokens"], "output_tokens": value["output_tokens"],
            "cached_input_tokens": value["cache_read_input_tokens"]}


def exposed_files(workspace):
    root = workspace.resolve()
    paths = {}
    for path in workspace.rglob("*"):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise AgentError("workspace_symlink")
        if path.is_file():
            paths[path.relative_to(workspace).as_posix()] = path
    if "task.json" not in paths:
        raise AgentError("missing_task")
    return paths


def run_agent(workspace, schema, prompt, model, spec, timeout, emit, *, send):
    """Run only the read/submit contract. Tests inject transport; no implicit live path."""
    validate_spec({"name": model, "effort": "not_applicable"}, spec)
    validate_schema(schema)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("A finite positive trial timeout is required")
    files = exposed_files(workspace)
    tools = [
        {"name": "read_file",
         "description": "Read one complete exposed UTF-8 file by relative path.",
         "input_schema": {"type": "object", "properties": {"path": {"type": "string"}},
                          "required": ["path"], "additionalProperties": False}},
        {"name": "submit_answer",
         "description": "Submit a structured answer after reading task.json.",
         "input_schema": schema}]
    messages = [{"role": "user", "content": prompt + "\nExposed paths: "
                 + canonical(sorted(files))}]
    deadline, task_read_at, tool_count = time.monotonic() + timeout, None, 0
    totals = {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}
    try:
        for number in range(1, spec["max_requests"] + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AgentError("timeout")
            payload = {"model": model, "max_tokens": spec["max_output_tokens"], "stream": False,
                       "tools": tools, "messages": messages}
            raw = canonical(payload).encode()
            if len(raw) > spec["max_request_bytes"]:
                raise AgentError("request_bytes_limit")
            emit({"type": "agent.request", "request": number, "request_bytes": len(raw),
                  "request_sha256": hashlib.sha256(raw).hexdigest()})
            response = send(payload, spec, remaining)
            if time.monotonic() >= deadline:
                raise AgentError("timeout")
            if (not isinstance(response, dict) or response.get("type") != "message"
                    or response.get("role") != "assistant" or response.get("model") != model
                    or response.get("stop_reason") != "tool_use"
                    or not isinstance(response.get("content"), list)
                    or any(not isinstance(c, dict) or c.get("type") not in ("text", "tool_use")
                           for c in response["content"])):
                raise AgentError("incompatible_response")
            usage = token_usage(response.get("usage"))
            if usage["output_tokens"] > spec["max_output_tokens"]:
                raise AgentError("output_token_limit")
            for name in totals:
                totals[name] += usage[name]
            emit({"type": "agent.response", "request": number, "usage": usage,
                  "provider_model": model, "stop_reason": "tool_use"})
            calls = [c for c in response["content"] if c["type"] == "tool_use"]
            if not calls:
                raise AgentError("missing_agent_tool_call")
            tool_count += len(calls)
            if tool_count > spec["max_tool_calls"]:
                raise AgentError("tool_call_limit")
            ids = [c.get("id") for c in calls]
            if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
                raise AgentError("invalid_tool_call")
            if any(c.get("name") == "submit_answer" for c in calls):
                if (len(calls) != 1 or task_read_at is None or task_read_at >= number
                        or not matches_schema(calls[0].get("input"), schema)):
                    raise AgentError("invalid_or_premature_answer")
                emit({"type": "agent.tool", "request": number, "name": "submit_answer"})
                emit({"type": "agent.completed", "usage": totals, "requests": number})
                return calls[0]["input"]
            results = []
            for call in calls:
                args = call.get("input")
                if (call.get("name") != "read_file" or not isinstance(args, dict)
                        or set(args) != {"path"} or not isinstance(args["path"], str)):
                    raise AgentError("unsupported_tool")
                path = args["path"]
                relative = PurePosixPath(path)
                if (path not in files or relative.is_absolute() or ".." in relative.parts
                        or "\\" in path or files[path].is_symlink()
                        or not files[path].resolve().is_relative_to(workspace.resolve())):
                    raise AgentError("unexposed_path")
                with files[path].open("rb") as handle:
                    data = handle.read(spec["max_read_bytes"] + 1)
                if len(data) > spec["max_read_bytes"]:
                    raise AgentError("tool_read_limit")
                try:
                    content = data.decode("utf-8")
                except UnicodeError:
                    raise AgentError("invalid_tool_utf8") from None
                emit({"type": "agent.tool", "request": number, "name": "read_file",
                      "path": path, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
                if path == "task.json":
                    task_read_at = number
                results.append({"type": "tool_result", "tool_use_id": call["id"],
                                "content": content})
            messages += [{"role": "assistant", "content": response["content"]},
                         {"role": "user", "content": results}]
        raise AgentError("request_limit")
    except AgentError as error:
        emit({"type": "agent.failed", "reason": str(error)})
        raise
    except Exception:
        emit({"type": "agent.failed", "reason": "agent_error"})
        raise AgentError("agent_error") from None


def trace_metrics(path):
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    complete = [e for e in events if e.get("type") == "agent.completed"]
    errors = [e for e in events if e.get("type") == "agent.failed"]
    requests = [e for e in events if e.get("type") == "agent.request"]
    responses = [e for e in events if e.get("type") == "agent.response"]
    tools = [e for e in events if e.get("type") == "agent.tool"]
    observed = {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}
    for response in responses:
        value = response["usage"]
        for key in observed:
            if type(value.get(key)) is not int or value[key] < 0:
                raise ValueError("Invalid normalized usage trace")
            observed[key] += value[key]
    sequence = list(range(1, len(requests) + 1))
    reads = [e["request"] for e in tools if e.get("name") == "read_file"
             and e.get("path") == "task.json"]
    submits = [e["request"] for e in tools if e.get("name") == "submit_answer"]
    valid = (len(complete) == 1 and not errors and len(requests) >= 2
             and [e["request"] for e in requests] == sequence
             and [e["request"] for e in responses] == sequence
             and complete[0].get("requests") == len(requests)
             and submits == [len(requests)] and any(r < submits[0] for r in reads))
    if valid and complete[0].get("usage") != observed:
        raise ValueError("Completed usage disagrees with response observations")
    return {"usage": observed if valid else None, "observed_usage": observed,
            "usage_complete": valid, "commands": tools, "errors": errors,
            "completed_turns": 1 if valid else 0, "api_requests": len(requests),
            "client_kind": KIND, "provider_model": responses[-1]["provider_model"] if responses
            else None}
