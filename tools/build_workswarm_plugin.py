"""Build a standalone WorkSwarm plugin archive from the canonical runtime bytes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__:
    from .plugin_bundle import PROJECT, build_bundle
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from plugin_bundle import PROJECT, build_bundle


def build_plugin(
    output: Path, *, project: Path = PROJECT, release_version: str | None = None,
) -> dict:
    return build_bundle(
        output, project=project, release_version=release_version,
        template_path="plugins/workswarm/inferrsi", metadata_file="manifest.json",
        readme="docs/workswarm-plugin.md", nested=True, compact_runtime=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT / "dist" / "workswarm-plugin")
    parser.add_argument("--release-version",
                        help="Require the built runtime version and stamp the ZIP")
    args = parser.parse_args()
    try:
        result = build_plugin(args.output, release_version=args.release_version)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
