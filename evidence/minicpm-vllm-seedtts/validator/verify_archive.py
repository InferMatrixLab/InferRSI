"""Explicit, bounded download and verification for the MiniCPM archive pilot.

Offline inventory checks never download. This entry point separately checks
metadata, availability, archive bytes, extraction, frozen files and recomputation.
"""

import argparse
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

from build_core import SNAPSHOT, generate, require, same

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 64 * 1024 * 1024
MAX_FILES = 1024
MAX_TAR_BYTES = MAX_BYTES + MAX_FILES * 1024 + 10240
TIMEOUT = 60


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def metadata(path):
    data = json.loads(path.read_text())
    artifact = data["archive"]
    require(
        re.fullmatch(
            r"https://github\.com/[\w.-]+/[\w.-]+/releases/download/[\w.-]+/[\w.-]+",
            artifact["url"],
        )
        is not None,
        "invalid Release asset URL",
    )
    require(re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"]) is not None, "invalid SHA256")
    require(
        re.fullmatch(r"[\w.-]+\.tar\.gz", artifact["file"]) is not None
        and artifact["url"].endswith("/" + artifact["file"]),
        "invalid archive filename",
    )
    require(artifact["snapshot_revision"] == SNAPSHOT, "unexpected source snapshot")
    require(
        re.fullmatch(r"[0-9a-f]{64}", artifact["publication_integrity_sha256"]) is not None,
        "invalid snapshot integrity SHA256",
    )
    for name, limit in (
        ("bytes", MAX_BYTES),
        ("uncompressed_bytes", MAX_BYTES),
        ("files", MAX_FILES),
    ):
        require(type(artifact[name]) is int and 0 < artifact[name] <= limit, f"invalid {name}")
    require(artifact["format"] == "tar.gz", "unsupported archive format")
    require(
        isinstance(artifact["retention_owner"], str) and artifact["retention_owner"].strip(),
        "missing retention owner",
    )
    require(artifact["root"] == "minicpm-vllm-seedtts", "unexpected archive root")
    return data


def allowed_download(url):
    parsed = urllib.parse.urlparse(url)
    return (
        parsed.scheme == "https"
        and not parsed.username
        and not parsed.password
        and parsed.port in (None, 443)
        and (
            parsed.hostname == "github.com"
            or parsed.hostname == "release-assets.githubusercontent.com"
            or parsed.hostname == "objects.githubusercontent.com"
        )
    )


class ReleaseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        require(allowed_download(newurl), "unsafe download redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(artifact, target):
    deadline = time.monotonic() + TIMEOUT
    opener = urllib.request.build_opener(ReleaseRedirect())
    with opener.open(artifact["url"], timeout=10) as response, target.open("xb") as output:
        require(allowed_download(response.url), "unsafe download location")
        size = 0
        while True:
            require(time.monotonic() <= deadline, "download time limit exceeded")
            block = response.read(1024 * 1024)
            if not block:
                break
            size += len(block)
            require(size <= artifact["bytes"], "download exceeds declared byte count")
            output.write(block)


def verify_bytes(path, artifact):
    require(path.stat().st_size == artifact["bytes"], "archive byte count mismatch")
    require(sha(path) == artifact["sha256"], "archive SHA256 mismatch")


def extract(path, destination, artifact):
    """No extractall: reject links, special files, duplicate/traversing paths."""
    require(not destination.exists(), "extraction destination already exists")
    destination.mkdir()
    files, size, names = 0, 0, set()
    deadline = time.monotonic() + TIMEOUT
    with (
        gzip.open(path, "rb") as compressed,
        tarfile.open(fileobj=BoundedTarStream(compressed, deadline), mode="r|") as archive,
    ):
        for member in archive:
            require(time.monotonic() <= deadline, "extraction time limit exceeded")
            name = member.name
            parts = name.split("/")
            require(member.isfile() and not member.issparse(), "non-regular archive member")
            require(
                not PurePosixPath(name).is_absolute()
                and "\\" not in name
                and ":" not in name
                and all(p not in ("", ".", "..") for p in parts)
                and parts[0] == artifact["root"],
                "unsafe archive path",
            )
            require(name not in names, "duplicate archive path")
            names.add(name)
            files += 1
            size += member.size
            require(
                member.size >= 0
                and files <= min(artifact["files"], MAX_FILES)
                and size <= min(artifact["uncompressed_bytes"], MAX_BYTES),
                "extraction limit exceeded",
            )
            target = destination.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, target.open("xb") as output:
                remaining = member.size
                while remaining:
                    require(time.monotonic() <= deadline, "extraction time limit exceeded")
                    block = source.read(min(remaining, 1024 * 1024))
                    require(bool(block), "truncated archive member")
                    output.write(block)
                    remaining -= len(block)
    require(
        files == artifact["files"] and size == artifact["uncompressed_bytes"],
        "archive member count/bytes mismatch",
    )
    return destination / artifact["root"]


class BoundedTarStream:
    """Also count tar headers/padding/PAX data, before tarfile allocates for them."""

    def __init__(self, source, deadline):
        self.source = source
        self.deadline = deadline
        self.size = 0

    def read(self, size):
        require(time.monotonic() <= self.deadline, "extraction time limit exceeded")
        data = self.source.read(min(size, MAX_TAR_BYTES - self.size + 1))
        self.size += len(data)
        require(self.size <= MAX_TAR_BYTES, "expanded archive limit exceeded")
        require(time.monotonic() <= self.deadline, "extraction time limit exceeded")
        return data


def verify_snapshot(root, artifact):
    integrity = root / "results/publication-integrity.json"
    require(
        sha(integrity) == artifact["publication_integrity_sha256"],
        "snapshot integrity identity mismatch",
    )
    hashes = json.loads(integrity.read_text())
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    require(
        actual == set(hashes) | {"results/publication-integrity.json"}, "snapshot file set mismatch"
    )
    for name, expected in hashes.items():
        require(
            name in actual and sha(root / name) == expected, f"snapshot SHA256 mismatch: {name}"
        )


def recompute(root, core):
    summary, trials = generate(root)
    same(json.loads((core / "results/summary.json").read_text()), summary, "summary")
    retained = [
        json.loads(line) for line in (core / "results/trials.jsonl").read_text().splitlines()
    ]
    same(retained, trials, "trials")
    # This exact script was reviewed and executed before publication; the frozen
    # integrity map above verifies its bytes before this bounded CPU subprocess.
    result = subprocess.run(
        [sys.executable, str(root / "validator/check_service_archive.py")],
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        env={**os.environ, "CUDA_VISIBLE_DEVICES": ""},
    )
    require(result.returncode == 0, "frozen CPU archive checker failed")
    return {"coverage": summary["coverage"], "frozen_checker": json.loads(result.stdout)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--download", action="store_true", help="Explicitly fetch the pinned public asset"
    )
    source.add_argument("--archive", type=Path, help="Verify an already downloaded asset offline")
    args = parser.parse_args()
    stage = "metadata"
    start = time.monotonic()
    try:
        record = metadata(ROOT / "results/artifacts.json")
        artifact = record["archive"]
        with tempfile.TemporaryDirectory(prefix="minicpm-evidence-") as temp:
            temp = Path(temp)
            path = args.archive
            if args.download:
                stage = "download"
                path = temp / artifact["file"]
                download(artifact, path)
            stage = "archive_bytes"
            verify_bytes(path, artifact)
            stage = "extraction"
            snapshot = extract(path, temp / "extracted", artifact)
            stage = "snapshot_integrity"
            verify_snapshot(snapshot, artifact)
            stage = "recomputation"
            checks = recompute(snapshot, ROOT)
        print(
            json.dumps(
                {
                    "verification": "passed",
                    "archive_sha256": artifact["sha256"],
                    "seconds": round(time.monotonic() - start, 3),
                    **checks,
                    "campaign_verdict": "INCONCLUSIVE",
                },
                indent=2,
            )
        )
        return 0
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        tarfile.TarError,
        subprocess.TimeoutExpired,
    ) as exc:
        print(
            json.dumps(
                {
                    "verification": "failed",
                    "stage": stage,
                    "error": str(exc),
                    "campaign_verdict": "unchanged",
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
