"""Run the release's bundled core without installing or modifying the target environment."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path


def main(*, launcher_path: Path | None = None) -> int:
    if sys.version_info < (3, 10):
        print("InferRSI requires Python 3.10 or newer; select a compatible interpreter.",
              file=sys.stderr)
        return 2
    script = Path(__file__).resolve()
    root = script.parents[3]
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
            "Install the built distribution for your host; developers can run the "
            "matching tools/build_<host>_plugin.py from the source checkout.",
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
    # No PyYAML precheck here. The runtime raises its own install hint, exit 2,
    # from the one call that parses skill frontmatter; guessing from argument
    # names refused operations that never parse any -- reading a case under
    # --skill-root, which is exactly the reference `find` hands back.

    # Commands the CLI prints for a reader to run next must start the way this
    # process was started. A plugin host has no `inferrsi` on PATH, so a
    # printed `inferrsi read ...` fails where this launcher would succeed. The
    # argv is passed as JSON so the CLI can quote it for the host's shell.
    launcher = launcher_path.resolve() if launcher_path is not None else script
    os.environ["INFERRSI_LAUNCHER"] = json.dumps([sys.executable, "-X", "utf8", str(launcher)])

    from inferrsi.apps.cli import main as cli_main

    return cli_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
