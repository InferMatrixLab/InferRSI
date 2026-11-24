"""Explicit, project-authorized MindIE navigation for standalone Find."""

from __future__ import annotations

import os
import queue
import re
import signal
import subprocess
import threading
from contextlib import ExitStack, suppress
from pathlib import Path

from ....knowledge.channels import ChannelHit, ChannelRequest, ChannelResult, ChannelStatus
from ..project_binding import checkout_identity, matches_checkout
from . import project
from .context import MAX_BYTES, _parse

_TOKEN_BUDGET = 8000
_NATIVE_LIMIT = 20
_REF = re.compile(
    r"mindie://(?P<domain>[a-z][a-z0-9-]{0,63})/units/"
    r"(?P<id>[A-Za-z0-9][A-Za-z0-9_.-]{0,127})@(?P<revision>[1-9][0-9]*)"
)
_NOT_ENABLED = ChannelStatus(
    "not_enabled", detail="No active MindIE grant matches the captured project checkout.",
    fix="Enable MindIE knowledge for the current project.",
)
_WORKER_ERRORS = {
    "The project reader supports mindie-knowledge 0.13.13": ChannelStatus(
        "version_mismatch", detail="MindIE navigation requires mindie-knowledge 0.13.13.",
    ),
    "The installed MindIE domain differs from the project grant": ChannelStatus(
        "rejected", detail="The installed MindIE domain differs from the project grant.",
    ),
    "The approved MindIE domain has no synced graded catalog": ChannelStatus(
        "unreachable", detail="The approved MindIE domain has no synced graded catalog.",
    ),
}
_UNREACHABLE = ChannelStatus("unreachable", detail="The approved MindIE reader is unavailable.")
_BAD_RESPONSE = ChannelStatus("rejected", detail="MindIE returned invalid navigation data.")


class _NavigationFailure(ValueError):
    def __init__(self, status: ChannelStatus):
        super().__init__(status.detail)
        self.status = status


def _stop(process: subprocess.Popen) -> None:
    try:
        if os.name == "posix":
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        elif os.name == "nt" and process.poll() is None:
            # A Windows venv interpreter can launch the actual worker as its child.
            taskkill = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/taskkill.exe"
            subprocess.run(
                [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3, check=False,
            )
    finally:
        if process.poll() is None:
            with suppress(ProcessLookupError):
                process.kill()
        process.wait(timeout=2)


def _exchange(start, stop, arguments: bytes, request: ChannelRequest) -> tuple[int, bytes]:
    """Read a bounded pipe and reap the worker on deadline or excess output."""
    process = request.start(start, stop)
    output: queue.Queue[bytes] = queue.Queue(maxsize=1)

    def write_input():
        with suppress(OSError), process.stdin as stream:
            stream.write(arguments)

    def read_output():
        try:
            with process.stdout as stream:
                raw = stream.read(MAX_BYTES + 1)
        except OSError:
            raw = b""
        output.put(raw)

    try:
        threading.Thread(target=write_input, daemon=True).start()
        threading.Thread(target=read_output, daemon=True).start()
        raw = output.get(timeout=request.remaining())
        if len(raw) > MAX_BYTES:
            raise _NavigationFailure(
                ChannelStatus("rejected", detail="MindIE navigation output exceeded 2 MiB.")
            )
        return process.wait(timeout=request.remaining()), raw
    except (queue.Empty, subprocess.TimeoutExpired):
        raise TimeoutError from None
    finally:
        request.finish(process)


def _navigation_hits(payload: dict, *, domain: str, limit: int) -> tuple[ChannelHit, ...]:
    # `results` is the native compatibility list and carries the native order.
    # Its references may also be represented in other navigation lists.
    rows = payload.get("results")
    if not isinstance(rows, list):
        raise _NavigationFailure(_BAD_RESPONSE)
    hits = {}
    valid = False
    for row in rows:
        ref = row.get("ref") if isinstance(row, dict) else None
        match = _REF.fullmatch(ref) if isinstance(ref, str) and len(ref) <= 256 else None
        if match is None or match["domain"] != domain:
            continue
        revision = row.get("revision")
        if ("revision" in row and (type(revision) is not int or str(revision) != match["revision"])
                or "id" in row and row["id"] != match["id"]):
            continue
        status = row.get("match_status", "")
        if status not in ("", "matched", "mismatched", "condition_unknown"):
            continue
        valid = True
        if status in ("mismatched", "condition_unknown") or ref in hits:
            continue
        hits[ref] = ChannelHit(ref, match["id"], score=None, score_scale="", status=status)
        if len(hits) == limit:
            break
    if rows and not valid:
        raise _NavigationFailure(_BAD_RESPONSE)
    return tuple(hits.values())


class MindieNavigationChannel:
    name = "mindie-agent"
    backend = "ascend"
    navigation_only = True

    def __init__(self, *, root: Path | None = None, expected_checkout: dict | None = None):
        self._root = None
        self._checkout = None
        self._grant = None
        try:
            self._root = project.project_root(root)
            self._checkout = (
                expected_checkout.copy() if expected_checkout is not None
                else checkout_identity(self._root)
            )
            self._grant = project._load_grant(self._root)
        except (OSError, ValueError, RuntimeError):
            pass

    def _approved(self) -> dict:
        if self._root is None or self._checkout is None or self._grant is None:
            raise _NavigationFailure(_NOT_ENABLED)
        try:
            current = project._load_grant(self._root)
        except (OSError, ValueError, RuntimeError):
            raise _NavigationFailure(_NOT_ENABLED) from None
        if current != self._grant or not matches_checkout(self._root, self._checkout):
            raise _NavigationFailure(_NOT_ENABLED)
        return self._grant

    def _run(self, action: str, arguments: dict, request: ChannelRequest) -> dict:
        request.remaining()
        grant = self._approved()
        try:
            with ExitStack() as workspace:
                def start():
                    argv, cwd, environment = workspace.enter_context(
                        project._worker_context(grant, action),
                    )
                    self._approved()
                    request.remaining()
                    return subprocess.Popen(
                        argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, cwd=cwd, env=environment,
                        start_new_session=os.name == "posix",
                        creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP
                                       if os.name == "nt" else 0),
                    )

                def stop(process):
                    try:
                        _stop(process)
                    finally:
                        workspace.close()

                code, raw = _exchange(start, stop, project._json(arguments), request)
        except TimeoutError:
            raise
        except (OSError, subprocess.SubprocessError):
            raise _NavigationFailure(_UNREACHABLE) from None
        request.remaining()
        try:
            payload = _parse(raw)
        except ValueError:
            raise _NavigationFailure(_BAD_RESPONSE) from None
        if (code or payload.get("isError") or payload.get("error")
                or payload.get("status") in ("error", "failed", "inactive", "denied")):
            error = payload.get("error")
            status = _WORKER_ERRORS.get(error) if isinstance(error, str) else None
            raise _NavigationFailure(status or _UNREACHABLE)
        return payload

    def describe(self, *, request: ChannelRequest) -> ChannelStatus:
        try:
            payload = self._run("describe", {}, request)
            if payload.get("domain") != self._approved()["domain"]:
                return _BAD_RESPONSE
        except _NavigationFailure as exc:
            return exc.status
        return ChannelStatus("ok")

    def search(
        self, query: str, *, platform: str | None, limit: int, request: ChannelRequest,
    ) -> ChannelResult:
        try:
            domain = self._approved()["domain"]
            limit = min(limit, _NATIVE_LIMIT)
            arguments = {
                "query": query, "limit": limit, "token_budget": _TOKEN_BUDGET,
                "conditions": {}, "include_unknown": False,
            }
            project._check_arguments("query", arguments, domain)
            payload = self._run("query", {**arguments, "include_archived": False}, request)
            self._approved()
            hits = _navigation_hits(payload, domain=domain, limit=limit)
        except _NavigationFailure as exc:
            return ChannelResult(self.name, exc.status)
        return ChannelResult(self.name, ChannelStatus("ok"), hits)

    def read(self, locator: str, *, expected_sha256: str | None = None,
             expected_revision: str | None = None) -> str:
        raise ValueError("Standalone Find provides MindIE navigation only")
