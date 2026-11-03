"""Replay native v0.2.7 lifecycle in a prepared host Python, without model calls.

Run outside the checkout with --host-source and --archive. All host writes use
a fresh temporary data root; existing profiles and configuration are not read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def extended_path(path: Path) -> Path:
    path = path.resolve()
    if os.name == "nt" and not str(path).startswith("\\\\?\\"):
        return Path("\\\\?\\UNC\\" + str(path)[2:] if str(path).startswith("\\\\")
                    else "\\\\?\\" + str(path))
    return path


def check(archive: Path, host_source: Path) -> dict:
    archive = archive.resolve()
    host_source = host_source.resolve()
    # Resolve explicit inputs before changing cwd. Host imports can create logs.
    with tempfile.TemporaryDirectory(
        prefix="irsi-host-", dir=extended_path(Path(tempfile.gettempdir())),
    ) as scratch:
        previous_cwd = Path.cwd()
        os.chdir(scratch)
        data = extended_path(Path(scratch) / "host-data")
        os.environ["JIUWENSWARM_DATA_DIR"] = str(data)
        sys.path.insert(0, str(host_source))
        sys.dont_write_bytecode = True
        try:
            from jiuwenswarm.server.runtime import extension_package_manager as manager
            from jiuwenswarm.server.runtime.session.session_metadata import (
                get_session_equipment,
                save_session_equipment,
            )

            # Assert isolation before any native lifecycle mutation.
            assert manager.get_user_workspace_dir() == data
            assert manager._local_root("plugin_packages").resolve().is_relative_to(data)
            manager.upsert_plugin_marketplace_entry(
                "fixture-unrelated", installed=True, source="local",
            )
            sentinel = manager.read_plugin_marketplace_entries()
            workspace = Path(scratch) / "target with spaces"
            workspace.mkdir()
            evidence = workspace / "existing-evidence.txt"
            evidence.write_bytes(b"preserve existing evidence")
            (workspace / "inferrsi.py").write_text(
                "raise RuntimeError('target must not supply the runtime')\n", encoding="utf-8",
            )
            info = {}
            for cycle in range(2):
                assert manager.import_plugin_package({"path": str(archive)})["id"] == "inferrsi"
                card = next(c for c in manager.list_plugin_packages() if c["id"] == "inferrsi")
                assert not card["installed"] and not manager.is_plugin_allowed("inferrsi")
                manager.install_plugin_package({"id": "inferrsi"})
                assert manager.is_plugin_allowed("inferrsi")
                installed = manager.resolve_plugin_dir("inferrsi")
                assert installed.resolve().is_relative_to(data)
                detail = manager.show_plugin_package("inferrsi")
                assert any(s["id"] == "inferrsi" for s in detail["skills"])
                save_session_equipment("fixture-empty", plugin_names=[])
                save_session_equipment("fixture-selected", plugin_names=["inferrsi"])
                assert get_session_equipment("fixture-empty", cache_bust=True)["plugin_names"] == []
                assert get_session_equipment(
                    "fixture-selected", cache_bust=True,
                )["plugin_names"] == ["inferrsi"]

                runtime = installed / "runtime"
                manifest = json.loads((runtime / "manifest.json").read_text(encoding="utf-8"))
                for name, digest in manifest["files"].items():
                    assert hashlib.sha256((runtime / name).read_bytes()).hexdigest() == digest
                launcher = installed / "skills/inferrsi/scripts/inferrsi.py"

                def invoke(*args: str, expected: int = 0):
                    result = subprocess.run(
                        [sys.executable, "-I", "-S", "-X", "utf8", str(launcher), *args],
                        cwd=workspace, capture_output=True, text=True, encoding="utf-8", timeout=45,
                    )
                    assert result.returncode == expected, (
                        "Installed CLI returned an unexpected code"
                    )
                    return json.loads(result.stdout) if expected == 0 else None

                info = invoke("--plugin-info")
                assert info["runtime"] == "bundled"
                assert info["content_sha256"] == manifest["content_sha256"]
                items = invoke("collect", "--relevance", "inference memory", "--limit", "1",
                               "--json")["items"]
                assert items
                item = items[0]
                material = invoke("read", item["ref"], "--revision", item["revision"], "--material")
                assert material["revision"] == item["revision"]
                invoke("read", item["ref"], "--revision", "sha256:" + "0" * 64, expected=2)
                manager.uninstall_plugin_package({"id": "inferrsi"})
                assert not installed.exists() and not manager.is_plugin_allowed("inferrsi")
                assert manager.read_plugin_marketplace_entries() == sentinel
                assert evidence.read_bytes() == b"preserve existing evidence"
            return {
                "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "runtime_version": info["runtime_version"],
                "content_sha256": info["content_sha256"],
                "completed_cycles": cycle + 1,
                "checks": ["import", "install", "card discovery", "selection metadata",
                           "installed file hashes", "isolated launcher", "exact revision read",
                           "stale revision rejection", "uninstall", "reinstall",
                           "unrelated registry and evidence preserved"],
                "not_exercised": ["desktop UI", "LLM dispatch", "cancellation/reconnect"],
            }
        finally:
            # This is a disposable CLI process. Host imports open log files;
            # close them before TemporaryDirectory removes its Windows tree.
            logging.shutdown()
            os.chdir(previous_cwd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-source", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.archive, args.host_source), indent=2))
