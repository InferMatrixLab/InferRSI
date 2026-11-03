from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# R6 Byte Budgets (Refs #273, F5/R6)
# Per-file budget: 512 KiB for files tracked in evidence/
PER_FILE_MAX_BYTES = 512 * 1024
# Per-PR net evidence addition budget: 2.0 MiB
PER_PR_EVIDENCE_MAX_BYTES = 2 * 1024 * 1024

ADVICE = (
    "Evidence byte budget exceeded. Large raw artifacts must be stored outside "
    "Git as GitHub Release assets, recording their URL, SHA-256, byte count, "
    "and retention owner in tools/evidence_inventory.json. See working rule 3 "
    "in docs/agent-collaboration.md and Issue #273."
)


def get_changed_files(
    base_ref: str | None = None,
    repo_root: Path | None = None,
) -> list[tuple[str, int]]:
    """Return list of (relative_path, file_size_bytes) for added or modified files."""
    root = repo_root or ROOT
    files: list[tuple[str, int]] = []

    if base_ref:
        try:
            # Get added (A), copied (C), or modified (M) files relative to base_ref
            res = subprocess.run(
                ["git", "diff", "--name-only", "--diff-filter=ACM", f"{base_ref}...HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            )
            rel_paths = [p.strip() for p in res.stdout.splitlines() if p.strip()]
        except (subprocess.SubprocessError, FileNotFoundError):
            rel_paths = get_local_git_changed_files(root)
    else:
        rel_paths = get_local_git_changed_files(root)

    for rel_path in rel_paths:
        full_path = root / rel_path
        if full_path.is_file():
            files.append((rel_path.replace("\\", "/"), full_path.stat().st_size))

    return files


def get_local_git_changed_files(root: Path) -> list[str]:
    """Inspect local git status for untracked, added, or modified files."""
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        paths = []
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                status, p = parts
                if "D" not in status:
                    paths.append(p.strip('"'))
        return paths
    except (subprocess.SubprocessError, FileNotFoundError):
        return []


def check_file_budgets(
    changed_files: list[tuple[str, int]],
    per_file_limit: int = PER_FILE_MAX_BYTES,
    per_pr_limit: int = PER_PR_EVIDENCE_MAX_BYTES,
    allowlist: set[str] | None = None,
) -> tuple[list[str], int]:
    """Check changed files against per-file and per-PR evidence budgets."""
    violations: list[str] = []
    total_evidence_bytes = 0
    allowed = allowlist or set()

    for rel_path, size in changed_files:
        norm_path = rel_path.replace("\\", "/")
        if norm_path in allowed:
            continue

        if norm_path.startswith("evidence/"):
            total_evidence_bytes += size
            if size > per_file_limit:
                violations.append(
                    f"file {norm_path}: {size:,} bytes exceeds limit of {per_file_limit:,} bytes"
                )

    if total_evidence_bytes > per_pr_limit:
        violations.append(
            f"evidence net addition: {total_evidence_bytes:,} bytes "
            f"exceeds per-PR limit of {per_pr_limit:,} bytes"
        )

    return violations, total_evidence_bytes


def validate_external_asset_manifest(manifest_path: Path) -> list[str]:
    """Verify that external asset entries record url, sha256, bytes, and retention_owner."""
    errors: list[str] = []
    if not manifest_path.exists():
        return errors

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"manifest error: failed to parse {manifest_path.name}: {exc}"]

    bundles = data.get("bundles", {})
    if not isinstance(bundles, dict):
        return errors

    sha_re = re.compile(r"^[0-9a-f]{64}$")

    for bundle_name, bundle in bundles.items():
        if not isinstance(bundle, dict):
            continue
        external_assets = bundle.get("external_assets", [])
        if not isinstance(external_assets, list):
            continue

        for idx, asset in enumerate(external_assets):
            prefix = f"bundle {bundle_name} external_assets[{idx}]"
            if not isinstance(asset, dict):
                errors.append(f"{prefix}: expected JSON object")
                continue

            for field in ("url", "sha256", "bytes", "retention_owner"):
                if field not in asset:
                    errors.append(f"{prefix}: missing required field '{field}'")

            url = asset.get("url", "")
            if not isinstance(url, str) or not url.startswith("https://"):
                errors.append(f"{prefix}: url must be a valid https URL")

            sha = asset.get("sha256", "")
            if not isinstance(sha, str) or not sha_re.match(sha):
                errors.append(f"{prefix}: invalid sha256 hex digest")

            byte_count = asset.get("bytes", -1)
            if not isinstance(byte_count, int) or byte_count <= 0:
                errors.append(f"{prefix}: bytes must be a positive integer")

            owner = asset.get("retention_owner", "")
            if not isinstance(owner, str) or not owner.strip():
                errors.append(f"{prefix}: retention_owner must be non-empty")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check evidence byte budgets and external asset metadata."
    )
    parser.add_argument("--base", help="Base git reference/SHA (e.g. origin/main or $BASE_SHA)")
    parser.add_argument("--files", nargs="*", help="Explicit list of files to check")
    parser.add_argument(
        "--inventory", default="tools/evidence_inventory.json", help="Path to evidence inventory"
    )
    parser.add_argument(
        "--max-file-bytes", type=int, default=PER_FILE_MAX_BYTES, help="Per-file max byte budget"
    )
    parser.add_argument(
        "--max-pr-bytes",
        type=int,
        default=PER_PR_EVIDENCE_MAX_BYTES,
        help="Per-PR max byte budget",
    )
    args = parser.parse_args()

    violations: list[str] = []

    if args.files is not None:
        file_list: list[tuple[str, int]] = []
        for p_str in args.files:
            p = Path(p_str)
            if p.is_file():
                rel = str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p).replace("\\", "/")
                file_list.append((rel, p.stat().st_size))
        diff_violations, _ = check_file_budgets(file_list, args.max_file_bytes, args.max_pr_bytes)
        violations.extend(diff_violations)
    else:
        changed_files = get_changed_files(args.base)
        diff_violations, _ = check_file_budgets(
            changed_files, args.max_file_bytes, args.max_pr_bytes
        )
        violations.extend(diff_violations)

    inv_path = ROOT / args.inventory
    if inv_path.exists():
        violations.extend(validate_external_asset_manifest(inv_path))

    for item in violations:
        print(item)

    if violations:
        print(ADVICE)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
