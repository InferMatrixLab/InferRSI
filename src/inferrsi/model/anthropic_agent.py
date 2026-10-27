"""Bounded direct Messages agent with frozen per-call cost reservations."""

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.request
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError

KIND = "anthropic-messages-agent-v1"
ENDPOINT = "https://yibuapi.com/v1/messages"
SOURCE = "src/inferrsi/model/anthropic_agent.py"
MAX_RESPONSE = 1024 * 1024
# Full context bound from https://platform.claude.com/docs/en/models/opus-5-5/overview
MODEL_CONTEXT = {"claude-opus-5-5": 1000000}
KEY_ENV = "SKILL_EVAL_YIBUAPI_KEY"


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


def money(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,9}(?:[.][0-9]{1,8})?", value):
        raise ValueError("Money and rates must be explicit finite nonnegative decimal strings")
    return Decimal(value)


def evidence_reference(value):
    return isinstance(value, str) and re.fullmatch(
        r"https://github[.]com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/issues/[0-9]+"
        r"#issuecomment-[0-9]+", value) is not None


def reservation(model, spec, pricing, spend_limit, trials, *, now=None):
    validate_spec({"name": model, "effort": "not_applicable"}, spec)
    required = {"currency", "unit", "model", "group", "rates", "request_fee",
                "max_input_tokens", "rate_evidence", "expires_at"}
    if not isinstance(pricing, dict) or set(pricing) != required:
        raise ValueError("Live provider pricing/cap settings are incomplete")
    if (pricing["currency"] not in ("CNY", "USD") or pricing["unit"] != "per_million_tokens"
            or pricing["model"] != model or not isinstance(pricing["group"], str)
            or not pricing["group"] or len(pricing["group"]) > 100
            or any(ord(c) < 32 for c in pricing["group"])):
        raise ValueError("Pricing must bind currency, units, exact model and effective group")
    if not evidence_reference(pricing["rate_evidence"]):
        raise ValueError("A reviewed effective-rate/group evidence reference is required")
    rates = pricing["rates"]
    if not isinstance(rates, dict) or set(rates) != {
            "input", "output", "cache_read", "cache_write"}:
        raise ValueError("Every input/output/cache rate must be explicit")
    amounts = {name: money(rate) for name, rate in rates.items()}
    fee = money(pricing["request_fee"])
    if (model not in MODEL_CONTEXT or type(pricing["max_input_tokens"]) is not int
            or pricing["max_input_tokens"] < MODEL_CONTEXT[model]
            or pricing["max_input_tokens"] > 2 ** 31):
        raise ValueError("A verified full model-context input-token ceiling is required")
    if (type(pricing["expires_at"]) is not int
            or pricing["expires_at"] <= (time.time() if now is None else now)):
        raise ValueError("Verified pricing/input-bound record expired")
    if (not isinstance(spend_limit, dict) or set(spend_limit) != {"currency", "amount"}
            or spend_limit["currency"] != pricing["currency"]
            or money(spend_limit["amount"]) <= 0
            or type(trials) is not int or trials <= 0):
        raise ValueError("A finite same-currency total limit and trial count are required")
    # Charge all possible input as the most expensive cache/input class. No cache discount
    # or successful completion is assumed; uncertain/error requests consume their allowance.
    per_request = ((pricing["max_input_tokens"] * max(amounts["input"], amounts["cache_read"],
                                                     amounts["cache_write"])
                    + spec["max_output_tokens"] * amounts["output"]) / Decimal(1000000) + fee)
    per_request = per_request.quantize(Decimal("0.00000001"), rounding=ROUND_CEILING)
    total_requests = trials * spec["max_requests"]
    total = (per_request * total_requests).quantize(Decimal("0.01"), rounding=ROUND_CEILING)
    if total > money(spend_limit["amount"]):
        raise ValueError("Worst-case cost reservation exceeds approved total limit")
    return {"currency": pricing["currency"], "amount": str(total), "limit": spend_limit["amount"],
            "requests": total_requests, "per_request": str(per_request),
            "pricing_sha256": hashlib.sha256(canonical(pricing).encode()).hexdigest(),
            "group": pricing["group"]}


def execution_environment(environment, *, with_key=True):
    # Called only at runtime. Neither plan/authorize nor tests discover existing credentials.
    safe = {k: environment[k] for k in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP", "LANG")
            if k in environment}
    safe["PYTHONUTF8"] = "1"
    if with_key:
        key = environment.get(KEY_ENV)
        if (not isinstance(key, str) or not key or not key.isascii()
                or any(c.isspace() for c in key)):
            raise ValueError("Provider credential is missing or malformed")
        safe[KEY_ENV] = key
    return safe


@dataclass(frozen=True)
class AnthropicAgentClient:
    model: str
    spec: dict
    timeout_seconds: float
    pricing: dict | None = None
    spend_limit: dict | None = None

    def frozen_identity(self):
        validate_spec({"name": self.model, "effort": "not_applicable"}, self.spec)
        value = {"settings": json.loads(canonical(self.spec)),
                 "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 "runtime_state": "unconfigured",
                 "request_policy": {"tool_choice": "auto", "thinking": "model_default",
                                    "sampling": "model_default", "retries": 0}}
        if self.pricing is not None or self.spend_limit is not None:
            self.require_live_readiness(now=0)
            value.update(pricing=json.loads(canonical(self.pricing)),
                         spend_limit=json.loads(canonical(self.spend_limit)),
                         runtime_state="configured")
        return value

    def require_live_readiness(self, trials=1, *, now=None):
        return reservation(self.model, self.spec, self.pricing, self.spend_limit, trials, now=now)

    def environment(self):
        return execution_environment(os.environ)

    def verifier_environment(self):
        return execution_environment(os.environ, with_key=False)

    def command(self, workspace, final, schema, prompt):
        self.require_live_readiness()
        settings = {"model": self.model, "client": self.spec, "pricing": self.pricing,
                    "spend_limit": self.spend_limit}
        return (sys.executable, "-I", str(Path(__file__).resolve()),
                "--workspace", str(workspace), "--final", str(final), "--schema", str(schema),
                "--settings", canonical(settings), "--prompt", prompt,
                "--timeout", str(self.timeout_seconds))

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


def valid_content_block(block):
    if not isinstance(block, dict):
        return False
    kind = block.get("type")
    if kind == "tool_use":
        return True  # The read/submit dispatcher validates identity and input below.
    if kind == "text":
        return isinstance(block.get("text"), str)
    if kind == "thinking":
        return isinstance(block.get("thinking"), str) and isinstance(block.get("signature"), str)
    if kind == "redacted_thinking":
        return isinstance(block.get("data"), str)
    return False


def run_agent(workspace, schema, prompt, model, spec, timeout, emit, *, send,
              input_token_ceiling=None):
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
    messages = [{"role": "user", "content": prompt
                 + "\nUse read_file to read task.json; finish with submit_answer. "
                 "Plain text is not a submission. Exposed paths: " + canonical(sorted(files))}]
    deadline, task_read_at, tool_count = time.monotonic() + timeout, None, 0
    totals = {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}
    try:
        for number in range(1, spec["max_requests"] + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AgentError("timeout")
            payload = {"model": model, "max_tokens": spec["max_output_tokens"], "stream": False,
                       "tools": tools, "tool_choice": {"type": "auto"}, "messages": messages}
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
                    or any(not valid_content_block(c) for c in response["content"])):
                raise AgentError("incompatible_response")
            usage = token_usage(response.get("usage"))
            if input_token_ceiling is not None and usage["input_tokens"] > input_token_ceiling:
                raise AgentError("input_token_limit")
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


def main(argv=None, *, environment=None, transport=None, emit=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("workspace", "final", "schema", "settings", "prompt"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--timeout", type=float, required=True)
    args = parser.parse_args(argv)
    emit = emit or (lambda event: print(canonical(event), flush=True))
    try:
        settings = json.loads(args.settings, object_pairs_hook=unique_object)
        if set(settings) != {"model", "client", "pricing", "spend_limit"}:
            raise ValueError("Unknown worker setting")
        client = AnthropicAgentClient(settings["model"], settings["client"], args.timeout,
                                      settings["pricing"], settings["spend_limit"])
        reserved = client.require_live_readiness()
        runtime = execution_environment(os.environ if environment is None else environment)
        key = runtime[KEY_ENV]
        sender = transport or send_message

        def send(payload, spec, timeout):
            return sender(payload, spec, key, timeout)

        schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
        emit({"type": "agent.reservation", **reserved})
        answer = run_agent(Path(args.workspace), schema, args.prompt, client.model,
                           client.spec, args.timeout, emit, send=send,
                           input_token_ceiling=client.pricing["max_input_tokens"])
        Path(args.final).write_text(canonical(answer) + "\n", encoding="utf-8")
        return 0
    except AgentError:
        return 1  # run_agent already retained a fixed failure code.
    except Exception:
        emit({"type": "agent.failed", "reason": "readiness_or_worker_error"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
