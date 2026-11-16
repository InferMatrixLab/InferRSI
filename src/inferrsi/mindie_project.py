"""An opt-in, per-checkout grant for the local MindIE knowledge reader."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from .mindie_context import MAX_BYTES, _parse

_SCHEMA = "inferrsi-mindie-project/1"
_DOMAIN = re.compile(r"[a-z][a-z0-9-]{0,63}")
_WORKER = Path(__file__).with_name("_mindie_read_worker.py")
_REF_ID = r"[A-Za-z0-9_.-]+@[1-9][0-9]*"
_SEARCH_FIELDS = {"query", "conditions", "limit", "token_budget", "include_unknown"}
_EXPLAIN_FIELDS = {"refs", "conditions", "known_refs", "token_budget"}


class ReadFailure(ValueError):
    def __init__(self, message, *, exit_code=None, response=None):
        super().__init__(message)
        self.exit_code = exit_code
        self.response = response


def project_root() -> Path:
    cwd = Path.cwd().resolve()
    for folder in (cwd, *cwd.parents):
        if (folder / ".git").exists():
            return folder
    raise ValueError("Open a Git project to use project-scoped MindIE knowledge")


def _grant_path(root: Path) -> Path:
    project_id = hashlib.sha256(os.fsencode(root)).hexdigest()
    return Path.home() / ".config" / "inferrsi" / "mindie-projects" / (project_id + ".json")


def _checkout_identity(root: Path) -> dict:
    marker = root / ".git"
    info = marker.stat()
    identity = {"device": info.st_dev, "inode": info.st_ino}
    if hasattr(info, "st_birthtime"):
        identity["created"] = info.st_birthtime
    if marker.is_file():
        with marker.open("rb") as pointer:
            raw = pointer.read(4097)
        if len(raw) > 4096 or not raw.startswith(b"gitdir: "):
            raise ValueError("The checkout has an invalid Git worktree pointer")
        identity["worktree_pointer"] = hashlib.sha256(raw).hexdigest()
        gitdir = (root / os.fsdecode(raw[8:].rstrip(b"\r\n"))).stat()
        identity["worktree_gitdir"] = [gitdir.st_dev, gitdir.st_ino]
    return identity


def _json(value) -> bytes:
    return (json.dumps(value, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def _read_object(path: Path) -> dict:
    with path.open("rb") as source:
        raw = source.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("MindIE JSON exceeds 2 MiB")
    return _parse(raw)


def _load_grant(root: Path) -> dict:
    path = _grant_path(root)
    try:
        info = path.stat()
        if (path.is_symlink() or not path.is_file()
                or os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077)):
            raise ValueError("The MindIE project grant must be a private local file")
        grant = _read_object(path)
        checkout = _checkout_identity(root)
    except FileNotFoundError:
        raise ValueError("MindIE is not enabled for this project") from None
    except OSError:
        raise ValueError("The MindIE project grant could not be read") from None
    if (grant.get("schema") != _SCHEMA or grant.get("project_root") != str(root)
            or grant.get("checkout") != checkout
            or not isinstance(grant.get("domain"), str) or not _DOMAIN.fullmatch(grant["domain"])
            or any(not isinstance(grant.get(key), str) or not Path(grant[key]).is_absolute()
                   for key in ("python", "engine"))):
        raise ValueError("The MindIE grant does not match this project")
    return grant


def _worker(grant: dict, action: str, arguments: bytes) -> bytes:
    environment = os.environ.copy()
    environment.pop("MINDIE_BENCH_WORKSPACE", None)
    try:
        with tempfile.TemporaryDirectory(prefix="inferrsi-mindie-read-") as temporary:
            # Upstream also probes cwd.parent/workspace and cwd.parent/work.
            # Keep that parent private and empty, not the shared temp directory.
            cwd = Path(temporary) / "reader"
            cwd.mkdir(mode=0o700)
            result = subprocess.run(
                [grant["python"], "-I", "-B", str(_WORKER),
                 grant["engine"], grant["domain"], action],
                input=arguments, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                cwd=cwd, env=environment, timeout=20, check=False,
            )
    except (OSError, subprocess.TimeoutExpired):
        raise ReadFailure("The approved MindIE reader could not be reached") from None
    if len(result.stdout) > MAX_BYTES:
        raise ReadFailure("MindIE returned more than 2 MiB", exit_code=result.returncode)
    try:
        payload = _parse(result.stdout)
    except ValueError:
        raise ReadFailure(
            "MindIE did not return a JSON object", exit_code=result.returncode,
        ) from None
    if result.returncode or payload.get("isError"):
        raise ReadFailure(payload.get("error", "The approved MindIE reader failed"),
                          exit_code=result.returncode, response=result.stdout)
    return result.stdout


def enable(adapter: Path, domain: str) -> dict:
    """Approve this checkout for one installed, already synced MindIE domain."""
    root = project_root()
    if not _DOMAIN.fullmatch(domain):
        raise ValueError("Invalid MindIE domain")
    config = _read_object(adapter.expanduser())
    domains = config.get("domain_configs", {})
    engine = domains.get(domain) if isinstance(domains, dict) else None
    engine = engine or config.get("engine_config")
    python = config.get("python")
    if any(not isinstance(value, str) or not Path(value).is_absolute()
           for value in (python, engine)):
        raise ValueError("The MindIE adapter has no installed runtime or engine for this domain")
    grant = dict(
        schema=_SCHEMA, project_root=str(root), checkout=_checkout_identity(root),
        python=python, engine=str(Path(engine).resolve(strict=True)), domain=domain,
    )
    info = _parse(_worker(grant, "describe", b"{}"))
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
    return {"available": True, **info}


def disable() -> dict:
    _grant_path(project_root()).unlink(missing_ok=True)
    return {"available": False, "reason": "MindIE is not enabled for this project"}


def describe() -> dict:
    try:
        grant = _load_grant(project_root())
        info = _parse(_worker(grant, "describe", b"{}"))
    except ValueError as exc:
        return {"available": False, "reason": str(exc)}
    return {"available": True, "tools": ["knowledge_query", "knowledge_explain"], **info}


def _check_arguments(action: str, arguments: dict, domain: str) -> None:
    fields = {"query": _SEARCH_FIELDS, "explain": _EXPLAIN_FIELDS}.get(action)
    if fields is None or not isinstance(arguments, dict) or set(arguments) - fields:
        raise ValueError("Use the public query or explain arguments")
    if not isinstance(arguments.get("conditions", {}), dict):
        raise ValueError("MindIE conditions must be a JSON object")
    budget = arguments.get("token_budget", 16000)
    if type(budget) is not int or not 1 <= budget <= 64000:
        raise ValueError("MindIE token_budget must be an integer from 1 through 64000")
    if action == "query":
        query, limit = arguments.get("query"), arguments.get("limit", 5)
        if not isinstance(query, str) or not query.strip() or len(query) > 4096:
            raise ValueError("MindIE query needs a search string of 1 through 4096 characters")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("MindIE limit must be an integer from 1 through 20")
        if type(arguments.get("include_unknown", False)) is not bool:
            raise ValueError("MindIE include_unknown must be a boolean")
        return
    pattern = re.compile(rf"mindie://{re.escape(domain)}/units/{_REF_ID}")
    for key in ("refs", "known_refs"):
        refs = arguments.get(key, [])
        if (not isinstance(refs, list) or len(refs) > 20 or key == "refs" and not refs
                or any(not isinstance(ref, str) or not pattern.fullmatch(ref) for ref in refs)):
            raise ValueError("Explain requires exact revision-bound refs in the approved domain")


def _record_read(root, action, domain, request, response, session, *, exit_code, error=None):
    folder = _grant_path(root)
    reads = folder.parent / "reads" / folder.stem
    reads.mkdir(mode=0o700, parents=True, exist_ok=True)
    receipt = Path(tempfile.mkdtemp(prefix=action + "-", dir=reads))
    files = {"input.json": request}
    if response is not None:
        files["result.json"] = response
    for name, content in files.items():
        (receipt / name).write_bytes(content)
    record = {
        "authorization": "project", "operation": "knowledge_" + action, "exit_code": exit_code,
        "domain": domain,
        "session_sha256": hashlib.sha256(session.encode()).hexdigest() if session else None,
        "sha256": {name: hashlib.sha256(content).hexdigest() for name, content in files.items()},
    }
    if error is not None:
        record["error"] = error
    (receipt / "receipt.json").write_bytes(_json(record))
    return receipt


def call(action: str, arguments: dict, *, session: str | None = None) -> dict:
    root = project_root()
    grant = _load_grant(root)
    domain = grant["domain"]
    _check_arguments(action, arguments, domain)
    request = _json(arguments)
    if len(request) > MAX_BYTES:
        raise ValueError("MindIE JSON exceeds 2 MiB")
    try:
        response = _worker(grant, action, request)
    except ReadFailure as exc:
        receipt = _record_read(root, action, domain, request, exc.response, session,
                               exit_code=exc.exit_code, error=str(exc))
        raise ValueError(f"{exc}. Local attempt receipt is in {receipt}") from None
    receipt = _record_read(root, action, domain, request, response, session, exit_code=0)
    return {"receipt_directory": str(receipt), "result": _parse(response)}


def dispatch(args) -> dict | None:
    if args.mindie_action == "enable":
        return enable(args.adapter_config, args.domain)
    if args.mindie_action == "disable":
        return disable()
    if args.mindie_action == "describe":
        return describe()
    if args.mindie_action == "serve":
        from .mindie_mcp import serve

        serve()
        return None
    return call(args.mindie_action, _read_object(args.input),
                session=os.environ.get("CODEX_THREAD_ID"))
