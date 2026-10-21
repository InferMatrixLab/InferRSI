"""Authenticate an existing supported snapshot against an immutable public HF revision.

No model files are downloaded or modified. Run the byte-intensive operation in
an allocated CPU job; the resulting manifest is input to the GPU reference trial.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

if __package__:
    from .profiles import MODEL_IDS, precision, validate_config
    from .trial import HEX40, HEX64, METADATA, MODEL_ID, REQUIRED, model_file
else:
    from profiles import MODEL_IDS, precision, validate_config
    from trial import HEX40, HEX64, METADATA, MODEL_ID, REQUIRED, model_file

MAX_METADATA_BYTES = 8 * 1024 * 1024
CHUNK_BYTES = 8 * 1024 * 1024


def fetch_metadata(revision: str, model_id: str = MODEL_ID) -> tuple[dict, dict]:
    if not isinstance(revision, str) or not HEX40.fullmatch(revision):
        raise ValueError("Require an immutable lowercase 40-character model revision")
    precision(model_id)
    url = f"https://huggingface.co/api/models/{model_id}/revision/{revision}?blobs=true"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        location = urlsplit(response.geturl())
        if location.scheme != "https" or location.netloc != "huggingface.co":
            raise ValueError("Unexpected model metadata origin")
        body = response.read(MAX_METADATA_BYTES + 1)
    if len(body) > MAX_METADATA_BYTES:
        raise ValueError("Model metadata response exceeds limit")
    metadata = json.loads(body)
    if metadata.get("sha") != revision or metadata.get("id") != model_id:
        raise ValueError("Public model metadata identity does not match request")
    return metadata, {
        "source": url,
        "response_sha256": hashlib.sha256(body).hexdigest(),
        "verification": "HF revision; Git blob SHA-1 or LFS SHA-256; local SHA-256",
    }


def authenticate_file(root: Path, name: str, sibling: dict, *, retain=False):
    """Compute the local SHA-256 and authoritative digest in one streaming pass."""
    path = model_file(root, name)
    size = sibling.get("size")
    if type(size) is not int or size < 0:
        raise ValueError("Public file metadata omits size")
    if retain and size > MAX_METADATA_BYTES:
        raise ValueError("Configuration or index exceeds parsing limit")
    digest = hashlib.sha256()
    lfs = sibling.get("lfs")
    if lfs is not None:
        expected = lfs.get("sha256")
        if (
            not isinstance(expected, str)
            or not HEX64.fullmatch(expected)
            or lfs.get("size") != size
        ):
            raise ValueError("Invalid LFS digest or size")
        authoritative = digest
    else:
        expected = sibling.get("blobId")
        if not isinstance(expected, str) or not HEX40.fullmatch(expected):
            raise ValueError("Missing public Git blob SHA-1")
        authoritative = hashlib.sha1()
        authoritative.update(f"blob {size}\0".encode("ascii"))
    total = 0
    retained = []
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_BYTES), b""):
            total += len(chunk)
            if total > size:
                raise ValueError("Local file exceeds public size")
            if authoritative is not digest:
                authoritative.update(chunk)
            digest.update(chunk)
            if retain:
                retained.append(chunk)
    if total != size or authoritative.hexdigest() != expected:
        raise ValueError("Local file differs from immutable public source")
    return {"path": name, "size": total, "sha256": digest.hexdigest()}, b"".join(retained)


def create_manifest(root: Path, revision: str, output: Path, model_id: str = MODEL_ID) -> dict:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Model path must be a directory")
    # Resolve the existing parent before writing. An output alias into the model
    # tree is rejected just like a direct destination there.
    parent = output.parent.resolve(strict=True)
    target = parent / output.name
    if target.is_relative_to(root) or target.exists() or target.is_symlink():
        raise ValueError("Output must be a new file outside the model directory")
    metadata, provenance = fetch_metadata(revision, model_id)
    # Also check here so injected/test transports cannot bypass source identity.
    if metadata.get("sha") != revision or metadata.get("id") != model_id:
        raise ValueError("Public model metadata identity does not match request")
    siblings = metadata.get("siblings")
    if not isinstance(siblings, list) or not siblings:
        raise ValueError("Public metadata omits repository file list")
    by_name = {}
    for sibling in siblings:
        name = sibling.get("rfilename")
        if not isinstance(name, str) or name in by_name:
            raise ValueError("Invalid or duplicate public file metadata")
        by_name[name] = sibling
    selected = REQUIRED | (METADATA & by_name.keys())
    # Existing tokenizer metadata must be authenticated even if absent upstream.
    selected |= {name for name in METADATA if (root / name).exists()}
    if not selected <= by_name.keys():
        raise ValueError("Public metadata omits required local model files")
    records = {}
    documents = {}
    for name in sorted(selected):
        record, content = authenticate_file(
            root,
            name,
            by_name[name],
            retain=name in {"config.json", "model.safetensors.index.json"},
        )
        records[name] = record
        if content:
            documents[name] = json.loads(content)
    config = documents["config.json"]
    validate_config(config, model_id)
    weight_map = documents["model.safetensors.index.json"].get("weight_map")
    if not isinstance(weight_map, dict) or not weight_map:
        raise ValueError("Weight index must contain a nonempty weight map")
    for name in sorted(set(weight_map.values())):
        if not isinstance(name, str) or not name.endswith(".safetensors") or name not in by_name:
            raise ValueError("Indexed shard is missing from public file metadata")
        record, _content = authenticate_file(root, name, by_name[name])
        records[name] = record
    manifest = {
        "model_id": model_id,
        "precision": precision(model_id),
        "revision": revision,
        "files": [records[name] for name in sorted(records)],
        "provenance": provenance,
    }
    with target.open("x") as stream:
        json.dump(manifest, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--model-id", choices=MODEL_IDS, default=MODEL_ID)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        create_manifest(args.model_path, args.model_revision, args.output, args.model_id)
    except Exception as error:
        print(f"Intake incomplete ({type(error).__name__}); no manifest accepted", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
