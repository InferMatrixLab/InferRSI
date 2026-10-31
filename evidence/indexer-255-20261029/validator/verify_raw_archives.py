"""Verify lossless compressed evidence; optionally restore outside the repository.

python evidence/indexer-255-20261029/validator/verify_raw_archives.py
python .../verify_raw_archives.py --restore /tmp/indexer-255-raw
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


def safe(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Evidence path escapes root")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restore", type=Path)
    args = parser.parse_args()
    bundle = Path(__file__).resolve().parents[1]
    entries = json.loads((bundle / "results/raw-archives.json").read_text())["files"]
    for entry in entries:
        compressed = safe(bundle, entry["archive"]).read_bytes()
        assert len(compressed) == entry["archive_bytes"]
        assert hashlib.sha256(compressed).hexdigest() == entry["archive_sha256"]
        raw = gzip.decompress(compressed)
        assert len(raw) == entry["original_bytes"]
        assert hashlib.sha256(raw).hexdigest() == entry["original_sha256"]
        json.loads(raw)
        if args.restore:
            target = safe(args.restore, entry["original_path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.read_bytes() != raw:
                raise ValueError("Refusing to overwrite different evidence: " + str(target))
            target.write_bytes(raw)
    print(f"Verified {len(entries)} original JSON artifacts")


if __name__ == "__main__":
    main()
