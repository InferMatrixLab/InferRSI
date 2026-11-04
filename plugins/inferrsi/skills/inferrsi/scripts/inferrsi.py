"""Run the release's bundled core without installing or modifying the target environment."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path


def main() -> int:
    if sys.version_info < (3, 10):
        print("InferRSI requires Python 3.10 or newer; select a compatible interpreter.",
              file=sys.stderr)
        return 2
    root = Path(__file__).resolve().parents[3]
    runtime = root / "runtime"
    if os.name == "nt" and not str(runtime).startswith("\\\\?\\"):
        runtime = Path("\\\\?\\UNC\\" + str(runtime)[2:]
                       if str(runtime).startswith("\\\\") else "\\\\?\\" + str(runtime))
    try:
        manifest = json.loads((runtime / "manifest.json").read_text(encoding="utf-8"))
        if not (runtime / "inferrsi" / "__init__.py").is_file():
            raise ValueError("bundled runtime is missing")
    except (OSError, ValueError) as exc:
        print(
            f"InferRSI plugin bundle is incomplete: {exc}. "
            "Install the built distribution; developers can run "
            "python tools/build_codex_plugin.py from the source checkout.",
            file=sys.stderr,
        )
        return 2

    # Preserve the target cwd and interpreter environment. Only this process's
    # import path changes, and the installed plugin is never written to.
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(runtime))
    from inferrsi import __version__

    if __version__ != manifest["runtime_version"]:
        print("InferRSI bundle version mismatch; rebuild or reinstall the plugin.", file=sys.stderr)
        return 2
    args = sys.argv[1:]
    has_yaml = importlib.util.find_spec("yaml") is not None
    if args == ["--plugin-info"]:
        print(json.dumps({
            "plugin_version": manifest["plugin_version"],
            "runtime_version": __version__,
            "runtime": "bundled",
            "python_version": ".".join(map(str, sys.version_info[:3])),
            "content_sha256": manifest["content_sha256"],
            "optional_skills_dependency": has_yaml,
        }, indent=2))
        return 0
    needs_yaml = args[:1] == ["skills"] or any(
        arg == "--skill-root" or arg.startswith("--skill-root=") for arg in args
    )
    if needs_yaml and not has_yaml and not any(arg in ("--help", "-h") for arg in args):
        print(
            "This operation needs the optional skills dependency: install PyYAML in the "
            "selected interpreter, or use packaged knowledge/collect/read without --skill-root.",
            file=sys.stderr,
        )
        return 2

    from inferrsi.cli import main as cli_main

    return cli_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
