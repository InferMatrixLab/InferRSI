"""Inventory only the production sandbox runtime; probe sensitive files fail-closed.

This is a trusted software-control check, not a candidate execution alternative.
No environment values or raw absolute inventory paths are retained.
"""

import hashlib
import importlib.metadata
import importlib.util
import os
import stat
import time
from pathlib import Path

from inferrsi.harness import kv_reclamation as kv
from inferrsi.harness.skill_eval_engineering import sandbox_command
from inferrsi.model import anthropic_edit_agent as edit

FORBIDDEN_NAMES = {"inferrsi", "skill_library", "kv_reclamation", "oracle.py", "fixtures.json"}
MAX_NODES = 200000
MAX_ESCAPES = 8192
MAX_SENSITIVE = 20000
MAX_DISTRIBUTIONS = 2000
MAX_HASH_BYTES = 128 * 1024 * 1024
MAX_SENSITIVE_BYTES = 32 * 1024 * 1024


def runtime_mounts(work):
    command = sandbox_command(work)
    mounts = []
    for index, value in enumerate(command):
        if value == "--ro-bind" and command[index + 2] != "/work":
            mounts.append((Path(command[index + 1]), Path(command[index + 2])))
    if not mounts:
        raise ValueError("No frozen runtime mounts")
    return mounts


def sensitive_files(root, independent, fixtures, knowledge_root, deadline):
    """Actual regular package, K, oracle and optimized-reference paths, not directories."""
    paths = [
        root / "src/inferrsi/__init__.py",
        fixtures / "reference.py",
        independent / "oracle.py",
        independent / "fixtures.json",
        knowledge_root / "SKILL.md",
        knowledge_root / "metadata.json",
        knowledge_root / "references/source-notes.md",
    ]
    if any(not p.is_file() or p.is_symlink() for p in paths):
        raise ValueError("Required sensitive-file anchor missing")

    def add_tree(directory):
        stack = [directory]
        while stack:
            if time.monotonic() >= deadline or len(paths) + len(stack) >= MAX_SENSITIVE:
                raise ValueError("Sensitive-file inventory limit")
            parent = stack.pop()
            with os.scandir(parent) as children:
                for item in children:
                    if item.is_symlink():
                        raise ValueError("Sensitive inventory symlink")
                    if item.is_dir(follow_symlinks=False):
                        if item.name != "__pycache__":
                            stack.append(Path(item.path))
                    elif item.is_file(follow_symlinks=False):
                        paths.append(Path(item.path))
                    else:
                        raise ValueError("Sensitive inventory special node")
                    if len(paths) + len(stack) >= MAX_SENSITIVE:
                        raise ValueError("Sensitive-file inventory limit")

    add_tree(independent)
    add_tree(knowledge_root)
    spec = importlib.util.find_spec("inferrsi")
    if spec is None or spec.origin is None:
        raise ValueError("Cannot locate actual imported package")
    paths.append(Path(spec.origin))
    for directory in spec.submodule_search_locations or ():
        add_tree(Path(directory) / "data")
    # Discover installed copies independently of the source checkout import path.
    for index, distribution in enumerate(importlib.metadata.distributions()):
        if index >= MAX_DISTRIBUTIONS or time.monotonic() >= deadline:
            raise ValueError("Installed distribution inventory limit")
        if distribution.metadata.get("Name", "").lower().replace("_", "-") == "inferrsi":
            for entry in distribution.files or ():
                if len(paths) >= MAX_SENSITIVE or time.monotonic() >= deadline:
                    raise ValueError("Installed package inventory limit")
                if "inferrsi" in entry.parts:
                    path = Path(distribution.locate_file(entry))
                    if not path.is_file() or path.is_symlink():
                        raise ValueError("Installed package inventory incomplete")
                    paths.append(path)
    result = sorted({p.resolve(strict=True) for p in paths})
    if not result:
        raise ValueError("No sensitive package/data inventory")
    return result


def inventory(mounts, sensitive, deadline):
    """Enumerate without following symlink directories; detect copies and escapes.

    Matching-size regular runtime files are compared to sensitive file hashes,
    including the complete large hidden corpus, so renaming a complete file does
    not evade the path-name check. Hash work is bounded and fails closed.
    This attests this trusted host layout, not arbitrary hostile host integrity.
    """
    roots = [source.resolve(strict=True) for source, _ in mounts]
    sensitive = [p.resolve(strict=True) for p in sensitive]
    sensitive_ancestors = {parent for p in sensitive for parent in (p, *p.parents)}
    sensitive_hashes, sizes, hashed_bytes = set(), set(), 0

    def bounded_hash(path, size):
        nonlocal hashed_bytes
        if size > MAX_SENSITIVE_BYTES or hashed_bytes + size > MAX_HASH_BYTES:
            raise ValueError("Runtime hash byte limit")
        hashed_bytes += size
        data = kv.read_regular(path, MAX_SENSITIVE_BYTES)
        if len(data) != size or time.monotonic() >= deadline:
            raise ValueError("Runtime hash inventory incomplete")
        return edit.digest(data)

    for path in sensitive:
        if time.monotonic() >= deadline or len(sensitive) > MAX_SENSITIVE + 2:
            raise ValueError("Sensitive hash inventory limit")
        size = path.stat().st_size
        if size:
            sizes.add(size)
            sensitive_hashes.add(bounded_hash(path, size))
    rows, escaped, rejected = [], [], False
    for index, (source, destination) in enumerate(mounts):
        # A bind source is resolved by the mount operation. Its target is the
        # mounted tree, not an escaped descendant alias: enumerate its contents
        # even when the source pathname itself is a symlink.
        stack = [(source.resolve(strict=True), Path("."))]
        while stack:
            if time.monotonic() >= deadline or len(rows) >= MAX_NODES:
                raise ValueError("Runtime inventory limit")
            path, relative = stack.pop()
            info = path.lstat()
            row = {
                "mount": index,
                "relative": relative.as_posix(),
                "mode": stat.S_IFMT(info.st_mode),
            }
            resolved = path.resolve(strict=False)
            if (
                any(name.lower() in FORBIDDEN_NAMES for name in path.parts)
                or resolved in sensitive_ancestors
            ):
                rejected = True
            if stat.S_ISLNK(info.st_mode):
                # Never traverse an escaped target. Test its in-sandbox alias for denial.
                row["target_sha256"] = hashlib.sha256(os.readlink(path).encode()).hexdigest()
                if not any(resolved == root or root in resolved.parents for root in roots):
                    escaped.append(str(destination / relative))
                    if len(escaped) > MAX_ESCAPES:
                        raise ValueError("Runtime symlink limit")
                    row["escaped"] = True
            elif stat.S_ISDIR(info.st_mode):
                with os.scandir(path) as children:
                    stack.extend((Path(p.path), relative / p.name) for p in children)
            elif stat.S_ISREG(info.st_mode):
                row["bytes"] = info.st_size
                if info.st_size in sizes:
                    row["sha256"] = bounded_hash(path, info.st_size)
                    if row["sha256"] in sensitive_hashes:
                        rejected = True
            else:
                raise ValueError("Special node in runtime mount")
            rows.append(row)
    rows.sort(key=lambda r: (r["mount"], r["relative"]))
    return {
        "verdict": "FAIL" if rejected else "PASS",
        "nodes": len(rows),
        "mount_count": len(mounts),
        "inventory_sha256": edit.fingerprint({"nodes": rows}),
        "escaped_symlinks": len(escaped),
        "sensitive_files": len(sensitive),
    }, escaped


def qualify(output, deadline, *, root, independent, fixtures, knowledge_root):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    result = {"verdict": "INCONCLUSIVE", "scope": "actual production candidate runtime mounts"}
    try:
        sensitive = sensitive_files(root, independent, fixtures, knowledge_root, deadline)
        for name in ("knowledge-canary.txt", "oracle-canary.txt"):
            path = output / name
            path.write_text("synthetic sensitive-path isolation canary\n", encoding="utf-8")
            sensitive.append(path)
        result, escaped = inventory(runtime_mounts(output), sensitive, deadline)
        if result["verdict"] == "PASS":
            result["probe"] = kv.probe_isolation(
                output / "probe", deadline, [str(p) for p in sensitive] + escaped
            )
    except kv.SandboxUnavailable:
        result.update(verdict="INCONCLUSIVE", reason="sandbox_unavailable")
    except Exception:
        result.update(verdict="INCONCLUSIVE", reason="runtime_inventory_incomplete")
    return result
