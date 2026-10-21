"""Bind native smoke imports to explicitly snapshotted source checkouts."""

import hashlib
import importlib
import sys
from pathlib import Path

CONTROL_REPO = Path(__file__).resolve().parents[2]


def import_records(prefix, root):
    root = Path(root).resolve()
    records = {}
    for name, module in list(sys.modules.items()):
        if name != prefix and not name.startswith(prefix + "."):
            continue
        for package_path in getattr(module, "__path__", ()):
            if not Path(package_path).resolve().is_relative_to(root):
                raise ValueError("Imported package search path escaped its source checkout")
        origin = getattr(module, "__file__", None)
        if origin is None:
            continue  # Namespace packages contain no executable source file.
        path = Path(origin).resolve(strict=True)
        if not path.is_relative_to(root):
            raise ValueError("Imported module escaped its requested source checkout")
        records[name] = {"path": path.relative_to(root).as_posix(),
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return records


def capture_sources(engine_repo=None, excluded_run_dir=None):
    import_records("inferrsi", CONTROL_REPO)
    sys.path.insert(0, str(CONTROL_REPO / "src"))
    importlib.invalidate_caches()
    from inferrsi.infra.targets import repository_identity

    roots = {"control": (CONTROL_REPO, "inferrsi")}
    if engine_repo is not None:
        roots["engine"] = (Path(engine_repo).resolve(), "nanovllm")
    sources = {}
    for label, (root, prefix) in roots.items():
        identity = repository_identity(root, excluded_run_dir)
        if not identity.get("available"):
            raise ValueError("Source checkout identity unavailable")
        sources[label] = {"head": identity["head"], "snapshot_hash": identity["snapshot_hash"],
                          "imports": import_records(prefix, root)}
    return sources


def import_native(engine_repo):
    root = Path(engine_repo).resolve(strict=True)
    if not (root / "nanovllm/qwen38/loader.py").is_file():
        raise ValueError("Requested engine checkout has no native checkpoint loader")
    import_records("nanovllm", root)  # Reject any already imported foreign package.
    sys.path.insert(0, str(root))
    importlib.invalidate_caches()
    loader = importlib.import_module("nanovllm.qwen38.loader")
    runner = importlib.import_module("nanovllm.qwen38.runner")
    records = import_records("nanovllm", root)
    for name in (loader.__name__, runner.__name__):
        if name not in records:
            raise ValueError("Native entrypoint source origin unavailable")
    return loader.load_checkpoint, runner.RequestRunner
