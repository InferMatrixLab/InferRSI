"""Call the approved cannbot-knowledge checkout with its own interpreter.

Run this worker with the interpreter recorded in the project grant: upstream
requires the MCP SDK constraints and PyYAML from its own environment, and this
program must not import the upstream package into the InferRSI process. Nothing
here writes to the upstream tree; the query CLI is read-only except for an
optional receipt, which is not requested.
"""

import hashlib
import json
import math
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

_SCRIPT = ".agents/skills/knowledge-query/scripts/knowledge_query.py"
_INDEX = ".agents/skills/knowledge-query/scripts/knowledge_index.py"
_STALE_MARKERS = ("stale", "missing", "rebuild", "index build", "inconsistent")
_FIX_BUILD = (
    "cd <checkout> && python3 " + _INDEX + " build"
)
# Upstream output is untrusted input. Bound it while reading, not after the
# whole stream is already in memory.
_MAX_UPSTREAM = 2 * 1024 * 1024


def _fail(message, *, state="rejected", fix=""):
    print(json.dumps({"isError": True, "error": message, "state": state, "fix": fix}))
    raise SystemExit(1)


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("cannbot source JSON has duplicate keys")
        value[key] = item
    return value


def _invalid(_):
    raise ValueError("cannbot source JSON has a non-finite number")


def _finite(value):
    number = float(value)
    if not math.isfinite(number):
        _invalid(value)
    return number


def _strict(raw):
    """Reject duplicate keys and non-finite numbers at the source boundary.

    `json.loads` collapses a duplicate key before any caller can see it, so a
    later re-serialisation cannot repair a document that was ambiguous on
    arrival. The check has to run on the upstream bytes themselves.
    """
    try:
        value = json.loads(
            raw, object_pairs_hook=_object, parse_constant=_invalid, parse_float=_finite,
        )
    except (ValueError, UnicodeError, RecursionError):
        _fail("cannbot returned malformed JSON", state="rejected")
    if not isinstance(value, dict):
        _fail("cannbot did not return a JSON object", state="rejected")
    return value


class OutputLimitError(ValueError):
    """A pipe exceeded the bounded capture size."""


_PROCESS_WAIT_SECONDS = 2.0
_WORKER_CLEANUP_SECONDS = _PROCESS_WAIT_SECONDS * (2 if os.name == "nt" else 1)


def _stop(process, *, own_group):
    if own_group and os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif own_group and os.name == "nt" and process.poll() is None:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=_PROCESS_WAIT_SECONDS,
            check=False,
        )
    if process.poll() is None:
        process.kill()
    process.wait(timeout=_PROCESS_WAIT_SECONDS)


def capture(argv, *, cwd, timeout, environment=None, request=None, own_group=False):
    """Capture at most 2 MiB + 1 per pipe, with no unbounded communicate().

    The outer worker owns a process group; upstream queries inherit it. Both
    the caller's cancellation and this function's finally block reap that group.
    Each pipe is drained concurrently so a full stderr cannot deadlock stdout.
    """
    deadline = time.monotonic() + timeout

    def start():
        return subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=cwd, env=environment, start_new_session=own_group and os.name == "posix",
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP
                           if own_group and os.name == "nt" else 0),
        )

    def stop(process):
        _stop(process, own_group=own_group)

    process = request.start(start, stop) if request else start()
    received = queue.Queue(maxsize=2)

    def drain(name, stream):
        try:
            with stream:
                received.put((name, stream.read(_MAX_UPSTREAM + 1)))
        except OSError:
            received.put((name, b""))

    for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
        threading.Thread(target=drain, args=(name, stream), daemon=True).start()
    try:
        output = {}
        for _ in range(2):
            try:
                name, raw = received.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty:
                raise subprocess.TimeoutExpired(argv, timeout) from None
            if len(raw) > _MAX_UPSTREAM:
                raise OutputLimitError("cannbot output exceeded 2 MiB")
            output[name] = raw
        code = process.wait(timeout=max(0, deadline - time.monotonic()))
        return subprocess.CompletedProcess(argv, code, output["stdout"], output["stderr"])
    finally:
        if request:
            request.finish(process)
        else:
            stop(process)


def _run(upstream, script, argv, *, timeout):
    try:
        # The JSON pipe needs UTF-8 even when -I ignores PYTHONUTF8.
        result = capture(
            [sys.executable, "-I", "-B", "-X", "utf8", str(upstream / script), *argv],
            cwd=str(upstream), timeout=timeout,
        )
    except OutputLimitError:
        _fail("cannbot output exceeded 2 MiB")
    if result.returncode:
        lowered = result.stderr.decode("utf-8", "replace").casefold()
        state = "index_stale" if any(m in lowered for m in _STALE_MARKERS) else "rejected"
        # Never relay arbitrary upstream stderr: it may contain private paths.
        _fail("cannbot index needs rebuilding" if state == "index_stale"
              else "cannbot query failed", state=state,
              fix=_FIX_BUILD if state == "index_stale" else "")
    return _strict(result.stdout)


def _index(payload):
    index = payload.get("index")
    if not isinstance(index, dict):
        _fail("cannbot response needs an index object")
    state = index.get("built_repository_state")
    if not isinstance(state, dict) or not isinstance(state.get("commit"), str):
        _fail("cannbot response needs an index revision")
    if not re.fullmatch(r"[0-9a-f]{40}", state["commit"]):
        _fail("cannbot response has an invalid index revision")
    return index, state


def discover(upstream, *, timeout=30):
    payload = _run(upstream, _SCRIPT, ["discover", "--json"], timeout=timeout)
    if payload.get("schema_version") != "knowledge-discovery.v1":
        _fail("Unsupported cannbot discovery schema", state="version_mismatch")
    if type(payload.get("cards")) is not int or payload["cards"] < 0:
        _fail("cannbot discovery needs a non-negative card count")
    index, state = _index(payload)
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


def _card_bytes(upstream, locator):
    root = (upstream / "knowledge").resolve()
    card = (root / (locator + ".md")).resolve()
    if not card.is_relative_to(root) or not card.is_file():
        _fail("No such card in the approved checkout")
    with card.open("rb") as source:
        raw = source.read(_MAX_UPSTREAM + 1)
    if len(raw) > _MAX_UPSTREAM:
        _fail("cannbot card exceeded 2 MiB")
    return raw


def _source_fingerprint(upstream):
    # The query index hashes parsed metadata + body, unlike MCP read_card's
    # raw-byte digest. Use the approved source's own implementation; never copy
    # its parser or fingerprint algorithm into this package.
    sys.path.insert(0, str((upstream / _SCRIPT).parent))
    try:
        from retrieval.index import card_fingerprint, load_contract

        _, split_frontmatter = load_contract(upstream)
    except (ImportError, AttributeError):
        _fail("Unsupported cannbot card identity API", state="version_mismatch")
    return card_fingerprint, split_frontmatter


def search(upstream, arguments, *, timeout=60):
    payload = _run(upstream, _SCRIPT, [
        "search", "--json", "--query", arguments["query"],
        "--platform", arguments["platform"], "--limit", str(arguments["limit"]),
    ], timeout=timeout)
    if payload.get("schema_version") != "knowledge-search.v5":
        _fail("Unsupported cannbot search schema", state="version_mismatch")
    rows = payload.get("results")
    if not isinstance(rows, list):
        _fail("cannbot search needs a results list")
    # Bound card verification too, rather than trimming only the final output.
    rows = rows[:arguments["limit"]]
    hits = []
    if rows:
        fingerprint, split_frontmatter = _source_fingerprint(upstream)
    for row in rows:
        if not isinstance(row, dict):
            _fail("cannbot search result must be an object")
        locator, digest = row.get("path"), row.get("card_sha256")
        if (not isinstance(locator, str) or not locator or locator.startswith("/")
                or "\\" in locator or any(p in ("", ".", "..") for p in locator.split("/"))):
            _fail("cannbot search result has an invalid locator")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            _fail("cannbot search result needs a card digest")
        score = row.get("score")
        if type(score) not in (int, float) or not math.isfinite(score):
            _fail("cannbot search result needs a finite score")
        if any(row.get(key) is not None and not isinstance(row[key], str)
               for key in ("title", "description", "status")):
            _fail("cannbot search result has invalid text fields")
        platforms = row.get("platforms")
        if platforms is not None and (not isinstance(platforms, list)
                                     or any(not isinstance(p, str) for p in platforms)):
            _fail("cannbot search result has an invalid platform list")
        raw = _card_bytes(upstream, locator)
        metadata, body = split_frontmatter(raw.decode("utf-8"))
        if fingerprint(metadata, body) != digest:
            _fail("cannbot card differs from its search index", state="index_stale",
                  fix=_FIX_BUILD)
        hits.append({
            "locator": row.get("path"),
            "title": row.get("title") or (row.get("path") or "").rsplit("/", 1)[-1],
            "summary": row.get("description") or "",
            "score": row.get("score") or 0,
            "status": row.get("status") or "",
            "platforms": row.get("platforms") or [],
            "source_card_sha256": digest,
            "card_sha256": hashlib.sha256(raw).hexdigest(),
        })
    index, state = _index(payload)
    # The pin lives on the index provenance, not at the top level: that is the
    # revision the index was built from, which is what a citation must name.
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


def _revision(upstream, *, timeout):
    # Inherited repository-selection variables must not redirect this check.
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("GIT_")}
    try:
        result = capture(
            ["git", "-C", str(upstream), "rev-parse", "--verify", "HEAD"],
            cwd=str(upstream), timeout=timeout, environment=environment,
        )
    except OutputLimitError:
        _fail("cannbot revision output exceeded 2 MiB")
    revision = result.stdout.decode("ascii", "replace").strip()
    if result.returncode or not re.fullmatch(r"[0-9a-f]{40}", revision):
        _fail("Cannot determine the approved cannbot checkout revision",
              state="version_mismatch")
    return revision


def read(upstream, arguments, *, timeout=15):
    deadline = time.monotonic() + timeout
    revision = _revision(upstream, timeout=max(0, deadline - time.monotonic()))
    expected_revision = arguments.get("expected_revision")
    if expected_revision and revision != expected_revision:
        _fail("The cannbot revision changed since the search; search again",
              state="version_mismatch")
    locator = arguments["locator"]
    body = _card_bytes(upstream, locator)
    if _revision(upstream, timeout=max(0, deadline - time.monotonic())) != revision:
        _fail("The cannbot revision changed during the read; search again",
              state="version_mismatch")
    digest = hashlib.sha256(body).hexdigest()
    # Search reports what it matched; read reports what it actually returned.
    # Without both, a card edited between the two is served under the old
    # locator and a citation names bytes nobody verified. A caller that passed
    # an expected digest gets a refusal instead of silent drift.
    expected = arguments.get("expected_sha256")
    if expected and expected != digest:
        _fail(
            "The card changed since the search that found it "
            f"(expected {expected[:12]}…, read {digest[:12]}…); search again",
            state="rejected",
        )
    lines = body.decode("utf-8").splitlines()
    size, page = 200, arguments.get("page", 1)
    start = (page - 1) * size
    chunk = lines[start:start + size]
    return {
        "state": "ok",
        "locator": locator,
        "revision": revision,
        "page": page,
        "pages": max(1, (len(lines) + size - 1) // size),
        "line_count": len(lines),
        "card_sha256": digest,
        "text": "\n".join(chunk),
        "has_more": start + size < len(lines),
    }


if __name__ == "__main__":
    try:
        upstream = Path(sys.argv[1]).resolve()
        action, raw = sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "{}"
        arguments = _strict(raw or "{}")
        timeout = float(sys.argv[4]) if len(sys.argv) > 4 else 30.0
        if action == "discover":
            result = discover(upstream, timeout=timeout)
        elif action == "search":
            result = search(upstream, arguments, timeout=timeout)
        elif action == "read":
            result = read(upstream, arguments, timeout=timeout)
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
