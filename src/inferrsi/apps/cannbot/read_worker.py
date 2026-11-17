"""Call the approved cannbot-knowledge checkout with its own interpreter.

Run this worker with the interpreter recorded in the project grant: upstream
requires the MCP SDK constraints and PyYAML from its own environment, and this
program must not import the upstream package into the InferRSI process. Nothing
here writes to the upstream tree; the query CLI is read-only except for an
optional receipt, which is not requested.
"""

import json
import subprocess
import sys
from pathlib import Path

_SCRIPT = ".agents/skills/knowledge-query/scripts/knowledge_query.py"
_INDEX = ".agents/skills/knowledge-query/scripts/knowledge_index.py"
_STALE_MARKERS = ("stale", "missing", "rebuild", "index build", "inconsistent")
_FIX_BUILD = (
    "cd <checkout> && python3 " + _INDEX + " build"
)


def _fail(message, *, state="rejected", fix=""):
    print(json.dumps({"isError": True, "error": message, "state": state, "fix": fix}))
    raise SystemExit(1)


def _run(upstream, script, argv, *, timeout):
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(upstream / script), *argv],
        capture_output=True, cwd=str(upstream), timeout=timeout, check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        lowered = detail.casefold()
        state = "index_stale" if any(m in lowered for m in _STALE_MARKERS) else "rejected"
        _fail(detail[-400:] or "cannbot query failed", state=state,
              fix=_FIX_BUILD if state == "index_stale" else "")
    return json.loads(result.stdout)


def discover(upstream):
    payload = _run(upstream, _SCRIPT, ["discover", "--json"], timeout=30)
    index = payload.get("index") or {}
    state = index.get("built_repository_state") or {}
    return {
        "state": "ok",
        "revision": state.get("commit"),
        "cards": payload.get("cards"),
        "domains": payload.get("domains", {}),
        "index": {
            "schema": index.get("schema_version"),
            "version": index.get("version") or index.get("index_version"),
            "content_fingerprint": index.get("content_fingerprint"),
        },
    }


def search(upstream, arguments):
    payload = _run(upstream, _SCRIPT, [
        "search", "--json", "--query", arguments["query"],
        "--platform", arguments["platform"], "--limit", str(arguments["limit"]),
    ], timeout=60)
    hits = []
    for row in payload.get("results") or []:
        hits.append({
            "locator": row.get("path"),
            "title": row.get("title") or (row.get("path") or "").rsplit("/", 1)[-1],
            "summary": row.get("description") or "",
            "score": row.get("score") or 0,
            "status": row.get("status") or "",
            "platforms": row.get("platforms") or [],
            "card_sha256": row.get("card_sha256") or "",
        })
    index = payload.get("index") or {}
    # The pin lives on the index provenance, not at the top level: that is the
    # revision the index was built from, which is what a citation must name.
    state = index.get("built_repository_state") or {}
    return {
        "state": "ok",
        "revision": state.get("commit"),
        "index": {
            "schema": index.get("schema_version"),
            "version": index.get("index_version"),
            "content_fingerprint": index.get("content_fingerprint"),
        },
        "score_scale": payload.get("schema_version") or "cannbot",
        "items": hits,
    }


def read(upstream, arguments):
    locator = arguments["locator"]
    card = (upstream / "knowledge" / (locator + ".md")).resolve()
    root = (upstream / "knowledge").resolve()
    # A locator is a Concept ID, not a path. Refuse anything that leaves the
    # bundle rather than trusting the caller to have passed a search result.
    if not card.is_relative_to(root) or not card.is_file():
        _fail("No such card in the approved checkout", state="rejected")
    lines = card.read_text(encoding="utf-8").splitlines()
    size, page = 200, arguments.get("page", 1)
    start = (page - 1) * size
    chunk = lines[start:start + size]
    return {
        "state": "ok",
        "locator": locator,
        "page": page,
        "pages": max(1, (len(lines) + size - 1) // size),
        "line_count": len(lines),
        "text": "\n".join(chunk),
        "has_more": start + size < len(lines),
    }


if __name__ == "__main__":
    try:
        upstream = Path(sys.argv[1]).resolve()
        action, raw = sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "{}"
        arguments = json.loads(raw or "{}")
        if action == "discover":
            result = discover(upstream)
        elif action == "search":
            result = search(upstream, arguments)
        elif action == "read":
            result = read(upstream, arguments)
        else:
            _fail("Unknown cannbot read action")
    except SystemExit:
        raise
    except subprocess.TimeoutExpired:
        _fail("cannbot query timed out", state="timeout")
    except (OSError, ValueError, KeyError, TypeError):
        # Paths and upstream internals must not reach the caller.
        _fail("The local cannbot checkout is unavailable", state="unreachable")
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
