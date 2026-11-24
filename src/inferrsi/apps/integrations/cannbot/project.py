"""An opt-in, per-checkout grant for an external cannbot-knowledge checkout.

The upstream corpus is CANN-licensed and stays where it is. This module records
only which checkout, interpreter and default platform this project approved; it
never copies knowledge into the repository, the wheel or an evidence tree.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from .read_worker import OutputLimitError, _finite, capture

_SCHEMA = "inferrsi-cannbot-project/1"
_WORKER = Path(__file__).with_name("read_worker.py")
MAX_BYTES = 2 * 1024 * 1024
_BACKEND = re.compile(r"[a-z][a-z0-9]{0,31}")
# Upstream platform values this adapter will pass through. An unlisted value is
# refused rather than forwarded: the upstream CLI is fail-closed about platform
# and a typo there would silently change which cards answer.
PLATFORMS = ("a2", "a3", "950", "310p", "910", "kirin_x90", "kirin_9030", "agnostic")


class ChannelFailure(ValueError):
    """A channel-level failure carrying the state the caller should report."""

    def __init__(self, message, *, state="rejected", fix="", exit_code=None):
        super().__init__(message)
        self.state = state
        self.fix = fix
        self.exit_code = exit_code


def project_root(start: Path | None = None) -> Path:
    directory = (Path.cwd() if start is None else start).resolve()
    for folder in (directory, *directory.parents):
        if (folder / ".git").exists():
            return folder
    raise ChannelFailure(
        "Open a Git project to use project-scoped cannbot knowledge",
        state="not_enabled", fix="Open a Git project, then enable cannbot knowledge",
    )


def _grant_path(root: Path) -> Path:
    project_id = hashlib.sha256(os.fsencode(root)).hexdigest()
    return Path.home() / ".config" / "inferrsi" / "cannbot-projects" / (project_id + ".json")


def checkout_identity(root: Path) -> dict:
    marker = root / ".git"
    info = marker.stat()
    identity = {"device": info.st_dev, "inode": info.st_ino}
    if hasattr(info, "st_birthtime"):
        identity["created"] = info.st_birthtime
    return identity


def _json(value) -> bytes:
    return (json.dumps(value, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def _parse(raw: bytes) -> dict:
    def _object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("cannbot response contains duplicate JSON keys")
            value[key] = item
        return value

    def _invalid(_):
        raise ValueError("cannbot response contains a non-finite JSON value")

    try:
        value = json.loads(raw, object_pairs_hook=_object, parse_constant=_invalid,
                           parse_float=_finite)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("cannbot did not return a JSON object") from exc
    if not isinstance(value, dict):
        raise ValueError("cannbot did not return a JSON object")
    return value


def load_grant(root: Path | None = None) -> dict:
    root = project_root() if root is None else root
    path = _grant_path(root)
    try:
        info = path.stat()
        if (path.is_symlink() or not path.is_file()
                or os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077)):
            raise ValueError("The cannbot project grant must be a private local file")
        with path.open("rb") as source:
            raw = source.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("The cannbot project grant exceeds 2 MiB")
        grant = _parse(raw)
        checkout = checkout_identity(root)
    except FileNotFoundError:
        raise ChannelFailure(
            "cannbot knowledge is not enabled for this project", state="not_enabled",
            fix="inferrsi cannbot enable --checkout <path> --python <interpreter>",
        ) from None
    except OSError:
        raise ChannelFailure("The cannbot project grant could not be read", state="not_enabled") \
            from None
    if (grant.get("schema") != _SCHEMA or grant.get("project_root") != str(root)
            or grant.get("checkout_identity") != checkout
            or not isinstance(grant.get("upstream"), str)
            or not Path(grant["upstream"]).is_absolute()
            or not isinstance(grant.get("python"), str)
            or not Path(grant["python"]).is_absolute()
            or not isinstance(grant.get("backend"), str)
            or not _BACKEND.fullmatch(grant["backend"])):
        raise ChannelFailure("The cannbot grant does not match this project", state="rejected")
    platforms = grant.get("platforms", [])
    if not isinstance(platforms, list) or any(item not in PLATFORMS for item in platforms):
        raise ChannelFailure("The cannbot grant has an invalid platform list", state="rejected")
    return grant


def _run(grant: dict, action: str, arguments: dict, *, timeout: float, request=None) -> dict:
    environment = os.environ.copy()
    for key in ("CANNBOT_MCP_TOKENS", "CANNBOT_KNOWLEDGE_PLATFORM"):
        environment.pop(key, None)
    try:
        with tempfile.TemporaryDirectory(prefix="inferrsi-cannbot-read-") as temporary:
            cwd = Path(temporary) / "reader"
            cwd.mkdir(mode=0o700)
            result = capture(
                [grant["python"], "-I", "-B", str(_WORKER),
                 grant["upstream"], action, json.dumps(arguments), str(timeout)],
                cwd=cwd, environment=environment, timeout=timeout, request=request,
                own_group=True,
            )
    except subprocess.TimeoutExpired:
        raise ChannelFailure(
            f"cannbot did not answer within {timeout:g}s", state="timeout"
        ) from None
    except OutputLimitError:
        raise ChannelFailure("cannbot output exceeded 2 MiB", state="rejected") from None
    except OSError:
        raise ChannelFailure(
            "The approved cannbot reader could not be started", state="unreachable"
        ) from None
    if len(result.stdout) > MAX_BYTES:
        raise ChannelFailure("cannbot returned more than 2 MiB", state="rejected")
    try:
        payload = _parse(result.stdout)
    except ValueError:
        raise ChannelFailure("cannbot returned invalid JSON", state="rejected") from None
    if result.returncode or payload.get("isError"):
        raise ChannelFailure(
            str(payload.get("error") or "The approved cannbot reader failed"),
            state=str(payload.get("state") or "rejected"),
            fix=str(payload.get("fix") or ""),
            exit_code=result.returncode,
        )
    return payload


def describe(root: Path | None = None, *, timeout: float = 15.0, request=None) -> dict:
    try:
        grant = load_grant(root)
    except ChannelFailure as exc:
        return {"state": exc.state, "detail": str(exc), "fix": exc.fix}
    try:
        payload = _run(grant, "discover", {}, timeout=timeout, request=request)
    except ChannelFailure as exc:
        return {"state": exc.state, "detail": str(exc), "fix": exc.fix}
    return {
        "state": "ok",
        "revision": payload.get("revision"),
        "cards": payload.get("cards"),
        "index": payload.get("index", {}),
        "platforms": list(grant.get("platforms", [])),
    }


def search(
    query: str, *, platform: str | None = None, limit: int = 100,
    root: Path | None = None, timeout: float = 8.0, request=None,
) -> dict:
    if not isinstance(query, str) or not query.strip():
        raise ChannelFailure("cannbot search needs a non-empty query")
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ChannelFailure("cannbot limit must be an integer from 1 through 200")
    grant = load_grant(root)
    platforms = list(grant.get("platforms", []))
    if platform is None:
        if not platforms:
            raise ChannelFailure(
                "cannbot search needs a platform", state="rejected",
                fix="inferrsi find <query> --backend ascend --platform <platform>",
            )
        platform = platforms[0]
    if platform not in PLATFORMS:
        raise ChannelFailure(f"cannbot does not know platform {platform!r}", state="rejected")
    return _run(grant, "search", {
        "query": query, "platform": platform, "limit": limit,
    }, timeout=timeout, request=request)


def read(locator: str, *, page: int = 1, expected_sha256: str | None = None,
         expected_revision: str | None = None,
         root: Path | None = None, timeout: float = 15.0) -> dict:
    if not isinstance(locator, str) or not locator.strip():
        raise ChannelFailure("cannbot read needs a locator from a search result")
    if type(page) is not int or page < 1:
        raise ChannelFailure("cannbot page must be a positive integer")
    if expected_sha256 is not None and (
        not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
    ):
        raise ChannelFailure("cannbot expected_sha256 must be a lowercase 64-hex digest")
    if expected_revision is not None and (
        not isinstance(expected_revision, str)
        or not re.fullmatch(r"[0-9a-f]{40}", expected_revision)
    ):
        raise ChannelFailure("cannbot expected_revision must be a full lowercase Git revision")
    arguments = {"locator": locator, "page": page}
    if expected_sha256:
        arguments["expected_sha256"] = expected_sha256
    if expected_revision:
        arguments["expected_revision"] = expected_revision
    return _run(load_grant(root), "read", arguments, timeout=timeout)


def enable(*, upstream: Path, python: Path, backend: str = "ascend",
           platforms: list[str] | None = None) -> dict:
    """Approve one checkout for this project after proving it answers.

    The probe is deliberate: a grant that records a checkout which cannot answer
    would turn every later search into a failure the user has to debug.
    """
    root = project_root()
    upstream = Path(upstream).expanduser()
    if not (upstream / ".git").exists():
        raise ValueError("--checkout must be a Git checkout of cannbot-knowledge")
    if not (upstream / "knowledge").is_dir():
        raise ValueError("--checkout must contain the knowledge/ bundle root")
    if not (upstream / ".agents/skills/knowledge-query/scripts/knowledge_query.py").is_file():
        raise ValueError("--checkout is missing the knowledge-query scripts")
    interpreter = Path(python).expanduser()
    if not interpreter.is_file() or not os.access(interpreter, os.X_OK):
        raise ValueError("--python must be an executable interpreter with pyyaml installed")
    if not _BACKEND.fullmatch(backend):
        raise ValueError("--backend must be a lowercase backend name")
    chosen = list(platforms or [])
    if any(item not in PLATFORMS for item in chosen):
        raise ValueError("--platform takes one of " + ", ".join(PLATFORMS))
    grant = {
        "schema": _SCHEMA, "project_root": str(root),
        "checkout_identity": checkout_identity(root),
        "upstream": str(upstream.resolve()),
        # Record the interpreter path as given. Resolving the symlink in a venv
        # bin/ lands on the base interpreter, which loses every installed
        # dependency -- the probe would pass and every later search would fail.
        "python": str(interpreter.absolute()),
        "backend": backend, "platforms": chosen,
    }
    info = _run(grant, "discover", {}, timeout=30.0)
    path = _grant_path(root)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
        pending = Path(output.name)
        try:
            output.write(_json(grant))
            output.close()
            pending.replace(path)
        finally:
            pending.unlink(missing_ok=True)
    return {"enabled": True, "revision": info.get("revision"), "cards": info.get("cards")}


def disable() -> dict:
    _grant_path(project_root()).unlink(missing_ok=True)
    return {"enabled": False, "reason": "cannbot knowledge is not enabled for this project"}
