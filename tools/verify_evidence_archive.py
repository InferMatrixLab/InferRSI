"""Inspect metadata offline, or explicitly verify a local/downloaded archive."""

import argparse
import json
import tempfile
from pathlib import Path

if __package__:
    from .evidence_archives import (
        VerificationError,
        compare_results,
        download_archive,
        normalize_manifest,
        read_json,
        verify_archive,
    )
else:
    from evidence_archives import (
        VerificationError,
        compare_results,
        download_archive,
        normalize_manifest,
        read_json,
        verify_archive,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Authoritative results/artifacts.json")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--archive", type=Path, help="Already retrieved archive; no network access")
    source.add_argument("--download", action="store_true", help="Explicitly fetch a public Release")
    parser.add_argument(
        "--recomputed", type=Path, help="Outputs from the reviewed v2 replay command"
    )
    parser.add_argument(
        "--bundle", type=Path, help="Retained bundle; default: manifest's parent/.."
    )
    args = parser.parse_args(argv)
    if args.recomputed and not (args.archive or args.download):
        parser.error("--recomputed requires --archive or --download")
    try:
        manifest = normalize_manifest(read_json(args.manifest))
        result = {
            "metadata": "valid",
            "content": "not_checked",
            "recomputation": "not_checked",
            "campaign_verdict": "unchanged",
        }
        if args.archive or args.download:
            with tempfile.TemporaryDirectory(prefix="evidence-verify-") as scratch:
                path = args.archive
                if args.download:
                    path = Path(scratch) / manifest["archive"]["file"]
                    download_archive(manifest, path)
                result.update(verify_archive(path, manifest))
                if args.recomputed:
                    result.update(
                        compare_results(
                            manifest,
                            args.bundle or args.manifest.resolve().parents[1],
                            args.recomputed,
                        )
                    )
        else:
            result["normalized_manifest"] = manifest
        print(json.dumps(result, indent=2))
        return 0
    except VerificationError as exc:
        result = {
            "verification": "failed",
            "failure": exc.code,
            "error": str(exc),
            "campaign_verdict": "unchanged",
        }
    except OSError:
        result = {
            "verification": "failed",
            "failure": "local_io",
            "error": "Local file access failed",
            "campaign_verdict": "unchanged",
        }
    print(json.dumps(result, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
