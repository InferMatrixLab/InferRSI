from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Candidate R6 Byte Budgets (Refs #273, F5/R6 - proposed defaults under owner discussion)
# Per-file budget: 512 KiB for files tracked in evidence/
PER_FILE_MAX_BYTES = 512 * 1024
# Per-PR net evidence addition budget: 2.0 MiB
PER_PR_EVIDENCE_MAX_BYTES = 2 * 1024 * 1024

RELEASE_ASSET_URL_PATTERN = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/releases/download/[^/]+/[^/]+$"
)

ADVICE = (
    "Candidate evidence byte budget exceeded. Large raw artifacts should be stored outside "
    "Git as GitHub Release assets, recording their downloadable asset URL, "
    "SHA-256 digest, byte count, and retention owner in tools/evidence_inventory.json. "
    "See discussion in Issue #273 (Remedy R6)."
)


def get_git_object_size(root: Path, obj_ref: str) -> int:
    """Return byte size of a git blob object using git cat-file -s.

    Raises ValueError if git cat-file fails.
    """
    if not obj_ref or set(obj_ref) == {"0"}:
        return 0
    res = subprocess.run(
        ["git", "cat-file", "-s", obj_ref],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        raise ValueError(
            f"Failed to read size for git object '{obj_ref}': {res.stderr.strip()}"
        )
    try:
        return int(res.stdout.strip())
    except ValueError as exc:
        raise ValueError(
            f"Invalid size output for git object '{obj_ref}': {res.stdout.strip()}"
        ) from exc


def get_changed_files_with_net_sizes(
    base_ref: str | None = None,
    repo_root: Path | None = None,
) -> list[tuple[str, int, int]]:
    """Return list of (rel_path, current_size_bytes, net_addition_bytes).

    If base_ref is supplied, uses git diff --raw -z against base_ref.
    Sizes are obtained from git blob objects directly (preventing symlink
    following, empty blob confusion, and worktree path confusion).
    If base_ref fails or is missing, raises ValueError (no silent fallback in CI).
    If base_ref is None, inspects local git status with -z and --untracked-files=all.
    """
    root = repo_root or ROOT
    results: list[tuple[str, int, int]] = []

    if base_ref:
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
            ["git", "diff", "--raw", "-z", f"{base_ref}...HEAD"],
            cwd=root,
            capture_output=True,
            check=True,
        )

        tokens = res.stdout.split(b"\0")
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if not tok:
                i += 1
                continue
            if not tok.startswith(b":"):
                i += 1
                continue

            header_str = tok.decode("utf-8", errors="replace")
            parts = header_str.split()
            if len(parts) < 5:
                i += 1
                continue

            sha_src, sha_dst, status = parts[2], parts[3], parts[4]

            is_rename_or_copy = status.startswith(("R", "C"))
            if is_rename_or_copy:
                if i + 2 >= len(tokens):
                    break
                src_path = tokens[i + 1].decode("utf-8", errors="replace")
                dst_path = tokens[i + 2].decode("utf-8", errors="replace")
                i += 3

                src_is_ev = src_path.startswith("evidence/")
                dst_is_ev = dst_path.startswith("evidence/")

                src_size = get_git_object_size(root, sha_src)
                dst_size = get_git_object_size(root, sha_dst)

                if status.startswith("R"):
                    # Rename: src replaced by dst
                    if src_is_ev and dst_is_ev:
                        delta = dst_size - src_size
                        results.append((dst_path, dst_size, delta))
                    elif not src_is_ev and dst_is_ev:
                        # Moved into evidence
                        results.append((dst_path, dst_size, dst_size))
                    elif src_is_ev and not dst_is_ev:
                        # Moved out of evidence
                        results.append((src_path, 0, -src_size))
                    else:
                        results.append((dst_path, dst_size, 0))
                else:
                    # Copy: src still exists, dst is added
                    delta = dst_size if dst_is_ev else 0
                    results.append((dst_path, dst_size, delta))

            else:
                if i + 1 >= len(tokens):
                    break
                path = tokens[i + 1].decode("utf-8", errors="replace")
                i += 2

                is_ev = path.startswith("evidence/")

                if status.startswith("D"):
                    src_size = get_git_object_size(root, sha_src)
                    delta = -src_size if is_ev else 0
                    results.append((path, 0, delta))
                elif status.startswith("A"):
                    cur_size = get_git_object_size(root, sha_dst)
                    delta = cur_size if is_ev else 0
                    results.append((path, cur_size, delta))
                elif status.startswith("M") or status.startswith("T"):
                    src_size = get_git_object_size(root, sha_src)
                    cur_size = get_git_object_size(root, sha_dst)
                    delta = (cur_size - src_size) if is_ev else 0
                    results.append((path, cur_size, delta))
                else:
                    cur_size = get_git_object_size(root, sha_dst)
                    delta = cur_size if is_ev else 0
                    results.append((path, cur_size, delta))

    else:
        # Local development fallback inspecting uncommitted changes with -z -uall
        local_paths = get_local_git_changed_files(root)
        for rel_path in local_paths:
            full_path = root / rel_path
            if full_path.is_file() or full_path.is_symlink():
                sz = full_path.lstat().st_size
                results.append((rel_path, sz, sz))

    return results


def get_local_git_changed_files(root: Path) -> list[str]:
    """Inspect local git status with -z and --untracked-files=all."""
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain", "-z", "--untracked-files=all"],
            cwd=root,
            capture_output=True,
            check=True,
        )
        tokens = res.stdout.split(b"\0")
        paths: list[str] = []
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if not tok:
                i += 1
                continue
            status_code = tok[:2].decode("latin-1", errors="replace")
            path = tok[3:].decode("utf-8", errors="replace")
            if "R" in status_code:
                # In git status -z for rename: new path is first, old path is second token
                paths.append(path)
                i += 2
            else:
                if "D" not in status_code:
                    paths.append(path)
                i += 1
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
        norm_path = rel_path
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
        sign = "+" if total_net_evidence_bytes >= 0 else "-"
        violations.append(
            f"evidence net addition: {sign}{abs(total_net_evidence_bytes):,} bytes "
            f"exceeds per-PR net limit of {per_pr_limit:,} bytes"
        )

    return violations, total_net_evidence_bytes


def validate_external_asset_manifest(manifest_path: Path) -> list[str]:
    """Verify external asset manifest syntax and fields conform to the schema.

    Validates schema structure, types, and GitHub Release download URL syntax.
    Does not probe remote HTTP endpoints or verify remote payload bytes over the network.
    """
    errors: list[str] = []
    if not manifest_path.exists():
        return errors

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"manifest error: failed to parse {manifest_path.name}: {exc}"]

    if not isinstance(data, dict):
        return ["manifest error: root of manifest must be a JSON object"]

    if "bundles" not in data:
        return ["manifest error: missing required key 'bundles'"]

    bundles = data.get("bundles")
    if not isinstance(bundles, dict):
        return ["manifest error: 'bundles' must be a JSON object"]

    sha_re = re.compile(r"^[0-9a-f]{64}$")

    for bundle_name, bundle in bundles.items():
        if not isinstance(bundle, dict):
            errors.append(f"bundle {bundle_name}: expected JSON object")
            continue

        if "external_assets" not in bundle:
            continue

        external_assets = bundle["external_assets"]
        if not isinstance(external_assets, list):
            errors.append(
                f"bundle {bundle_name}: 'external_assets' must be a list of asset objects"
            )
            continue

        for idx, asset in enumerate(external_assets):
            prefix = f"bundle {bundle_name} external_assets[{idx}]"
            if not isinstance(asset, dict):
                errors.append(f"{prefix}: expected JSON object")
                continue

            # url check
            url = asset.get("url")
            if url is None:
                errors.append(f"{prefix}: missing or null required field 'url'")
            elif not isinstance(url, str) or not RELEASE_ASSET_URL_PATTERN.match(url):
                errors.append(
                    f"{prefix}: url must point to a downloadable GitHub Release asset "
                    f"(https://github.com/<owner>/<repo>/releases/download/<tag>/<filename>)"
                )

            # sha256 check
            sha = asset.get("sha256")
            if sha is None:
                errors.append(f"{prefix}: missing or null required field 'sha256'")
            elif not isinstance(sha, str) or not sha_re.match(sha):
                errors.append(f"{prefix}: invalid sha256 hex digest")

            # bytes check
            byte_count = asset.get("bytes")
            if byte_count is None:
                errors.append(f"{prefix}: missing or null required field 'bytes'")
            elif (
                not isinstance(byte_count, int)
                or isinstance(byte_count, bool)
                or byte_count <= 0
            ):
                errors.append(f"{prefix}: bytes must be a positive integer")

            # retention_owner check
            owner = asset.get("retention_owner")
            if owner is None:
                errors.append(f"{prefix}: missing or null required field 'retention_owner'")
            elif not isinstance(owner, str) or not owner.strip():
                errors.append(f"{prefix}: retention_owner must be non-empty string")

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
                if p.is_file() or p.is_symlink():
                    rel = str(
                        p.relative_to(ROOT) if p.is_relative_to(ROOT) else p
                    )
                    sz = p.lstat().st_size
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
