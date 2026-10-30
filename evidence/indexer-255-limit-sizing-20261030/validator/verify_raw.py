"""Verify saved archive members without extracting or executing them."""
import hashlib
import json
import tarfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "results/raw-files.json").read_text())
    path = root / "results/raw-study.tar.gz"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest["archive_sha256"]
    seen = set()
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            assert member.isfile() and member.name in manifest["files"]
            assert member.name not in seen
            seen.add(member.name)
            data = archive.extractfile(member).read()
            expected = manifest["files"][member.name]
            assert len(data) == expected["bytes"]
            assert hashlib.sha256(data).hexdigest() == expected["sha256"]
    assert seen == set(manifest["files"])
    print(f"Verified {len(seen)} original raw files")


if __name__ == "__main__":
    main()
