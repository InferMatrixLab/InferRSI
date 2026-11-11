"""Stdio MCP for the two local MindIE reads approved for this project."""

import json
import re
import sys

from . import __version__
from .mindie_context import MAX_BYTES, _parse
from .mindie_project import call, describe

_PROTOCOL = "2025-11-25"
_SUPPORTED = {"2024-11-05", "2025-03-26", "2025-06-18", _PROTOCOL}
_NATIVE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}")
_REFS = {"type": "array", "maxItems": 20, "items": {"type": "string"}}
_COMMON = {
    "conditions": {"type": "object", "description": "Observed device, dtype, shape and software."},
    "token_budget": {"type": "integer", "minimum": 1, "maximum": 64000},
}
_TOOLS = {
    "knowledge_query": (
        "Search the approved local MindIE domain for relevant versioned knowledge cards. "
        "Choose search terms from the task's concrete knowledge gap.",
        "query",
        {
            "query": {"type": "string", "minLength": 1, "maxLength": 4096},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            "include_unknown": {
                "type": "boolean", "description": "Include cards with unknown applicability.",
            },
        },
    ),
    "knowledge_explain": (
        "Read the complete bodies and prerequisites for selected exact MindIE refs from the query.",
        "refs",
        {"refs": {**_REFS, "minItems": 1}, "known_refs": _REFS},
    ),
}


def _catalog():
    return [
        {
            "name": name, "description": description,
            "inputSchema": {
                "type": "object", "properties": {**_COMMON, **properties},
                "required": [required], "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        }
        for name, (description, required, properties) in _TOOLS.items()
    ]


def _thread_id(params):
    meta = params.get("_meta")
    if isinstance(meta, dict):
        turn = meta.get("x-codex-turn-metadata")
        thread = meta.get("threadId")
        if (isinstance(turn, dict) and isinstance(thread, str) and _NATIVE_ID.fullmatch(thread)
                and thread == turn.get("thread_id")):
            return thread
    return None


def _reply(method, params):
    if method == "initialize":
        requested = params.get("protocolVersion")
        return {
            "protocolVersion": requested if requested in _SUPPORTED else _PROTOCOL,
            "serverInfo": {"name": "inferrsi-mindie", "version": __version__},
            "capabilities": {"tools": {}},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": _catalog() if describe()["available"] else []}
    if method == "tools/call":
        name = params.get("name")
        try:
            if not isinstance(name, str) or name not in _TOOLS:
                raise ValueError("Unknown MindIE read tool")
            result = call(name.removeprefix("knowledge_"), params.get("arguments", {}),
                          session=_thread_id(params))
        except (OSError, ValueError) as exc:
            return {"isError": True, "content": [{"type": "text", "text": str(exc)}]}
        return {
            "isError": False, "structuredContent": result,
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=True)}],
        }
    raise LookupError(method)


def serve():
    while line := sys.stdin.buffer.readline(MAX_BYTES + 1):
        identifier = None
        try:
            if len(line) > MAX_BYTES:
                raise ValueError("MCP message exceeds 2 MiB")
            message = _parse(line)
            if "id" not in message:
                continue
            identifier = message["id"]
            method, params = message.get("method"), message.get("params", {})
            if (message.get("jsonrpc") != "2.0" or not isinstance(method, str)
                    or not isinstance(params, dict)):
                raise ValueError("Invalid MCP request")
            payload = {"result": _reply(method, params)}
        except LookupError:
            payload = {"error": {"code": -32601, "message": "Unknown MCP method"}}
        except (ValueError, TypeError):
            payload = {"error": {"code": -32600, "message": "Invalid MCP request"}}
        print(json.dumps({"jsonrpc": "2.0", "id": identifier, **payload}), flush=True)
