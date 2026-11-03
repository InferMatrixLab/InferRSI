from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Proposed R6 Byte Budgets (Refs #273, F5/R6 - under discussion)
# Per-file budget: 512 KiB for files tracked in evidence/
PER_FILE_MAX_BYTES = 512 * 1024
# Per-PR net evidence addition budget: 2.0 MiB
PER_PR_EVIDENCE_MAX_BYTES = 2 * 1024 * 1024

RELEASE_ASSET_URL_PATTERN = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/releases/download/[^/]+/[^/]+$"
)

ADVICE = (
    "Evidence byte budget exceeded. Large raw artifacts should be stored outside "
    "Git as GitHub Release assets, recording their downloadable asset URL, "
    "SHA-256 digest, byte count, and retention owner in tools/evidence_inventory.json. "
    "See discussion in Issue #273 (Remedy R6)."
)


def get_git_object_size(root: Path, obj_ref: str) -> int:
    """Return byte size of a git blob object using git cat-file -s."""
    try:
        res = subprocess.run(
            ["git", "cat-file", "-s", obj_ref],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        return int(res.stdout.strip())
    except (subprocess.SubprocessError, ValueError):
        return 0


def get_changed_files_with_net_sizes(
    base_ref: str | None = None,
    repo_root: Path | None = None,
) -> list[tuple[str, int, int]]:
    """Return list of (rel_path, current_size_bytes, net_addition_bytes).

    If base_ref is supplied, uses git diff --raw against base_ref.
    If base_ref fails or is missing, raises ValueError (no silent fallback in CI).
    If base_ref is None, falls back to inspecting local git status.
    """
    root = repo_root or ROOT
    results: list[tuple[str, int, int]] = []

    if base_ref:
        # Validate base_ref exists before diffing
        rev_check = subprocess.run(
            ["git", "rev-parse", "--verify", base_ref],
            cwd=root,
            capture_output=True,
            text=True,
        )
        if rev_check.returncode != 0:
            raise ValueError(
                f"Base ref '{base_ref}' cannot be resolved. "
                "Ensure target base ref is fetched before checking diff."
            )

        res = subprocess.run(
            ["git", "diff", "--raw", f"{base_ref}...HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )

        for line in res.stdout.splitlines():
            line = line.strip()
            if not line.startswith(":"):
                continue
            # Format: :mode_src mode_dst sha_src sha_dst status\tpath (or path1\tpath2 for rename)
            header, _, path_part = line.partition("\t")
            parts = header.split()
            if len(parts) < 5:
                continue
            sha_src, status = parts[2], parts[4]
            rel_path = path_part.split("\t")[0].strip('"').replace("\\", "/")

            full_path = root / rel_path
            current_size = full_path.stat().st_size if full_path.is_file() else 0

            # Calculate true net delta
            if status.startswith("A"):
                net_addition = current_size
            elif status.startswith("M"):
                src_size = get_git_object_size(root, sha_src)
                net_addition = max(0, current_size - src_size)
            elif status.startswith("D"):
                net_addition = 0
            else:
                net_addition = current_size

            results.append((rel_path, current_size, net_addition))

    else:
        # Local development fallback without base ref
        local_paths = get_local_git_changed_files(root)
        for rel_path in local_paths:
            full_path = root / rel_path
            if full_path.is_file():
                sz = full_path.stat().st_size
                results.append((rel_path.replace("\\", "/"), sz, sz))

    return results


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
    file_records: list[tuple[str, int, int]],
    per_file_limit: int = PER_FILE_MAX_BYTES,
    per_pr_limit: int = PER_PR_EVIDENCE_MAX_BYTES,
    allowlist: set[str] | None = None,
) -> tuple[list[str], int]:
    """Check file records (rel_path, current_size, net_addition) against budgets."""
    violations: list[str] = []
    total_net_evidence_bytes = 0
    allowed = allowlist or set()

    for rel_path, current_size, net_addition in file_records:
        norm_path = rel_path.replace("\\", "/")
        if norm_path in allowed:
            continue

        if norm_path.startswith("evidence/"):
            total_net_evidence_bytes += net_addition
            if current_size > per_file_limit:
                violations.append(
                    f"file {norm_path}: {current_size:,} bytes exceeds per-file limit "
                    f"of {per_file_limit:,} bytes"
                )

    if total_net_evidence_bytes > per_pr_limit:
        violations.append(
            f"evidence net addition: +{total_net_evidence_bytes:,} bytes "
            f"exceeds per-PR net limit of {per_pr_limit:,} bytes"
        )

    return violations, total_net_evidence_bytes


def validate_external_asset_manifest(manifest_path: Path) -> list[str]:
    """Verify external asset entries record downloadable URL, sha256, bytes, and owner."""
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
            if not isinstance(url, str) or not RELEASE_ASSET_URL_PATTERN.match(url):
                errors.append(
                    f"{prefix}: url must point to a downloadable GitHub Release asset "
                    f"(https://github.com/<owner>/<repo>/releases/download/<tag>/<filename>)"
                )

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

    try:
        if args.files is not None:
            file_list: list[tuple[str, int, int]] = []
            for p_str in args.files:
                p = Path(p_str)
                if p.is_file():
                    rel = str(
                        p.relative_to(ROOT) if p.is_relative_to(ROOT) else p
                    ).replace("\\", "/")
                    sz = p.stat().st_size
                    file_list.append((rel, sz, sz))
            diff_violations, _ = check_file_budgets(
                file_list, args.max_file_bytes, args.max_pr_bytes
            )
            violations.extend(diff_violations)
        else:
            changed_records = get_changed_files_with_net_sizes(args.base)
            diff_violations, _ = check_file_budgets(
                changed_records, args.max_file_bytes, args.max_pr_bytes
            )
            violations.extend(diff_violations)
    except Exception as exc:
        print(f"evidence-budget error: {exc}", file=sys.stderr)
        return 1

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
