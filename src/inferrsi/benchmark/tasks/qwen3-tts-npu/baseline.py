# SPDX-License-Identifier: Apache-2.0
"""Run the bundled real-model Qwen3-TTS reference without inference engines."""

import argparse
import hashlib
import importlib.abc
import importlib.util
import json
import os
import sys
from pathlib import Path

BLOCKED = {"vllm", "vllm_omni", "sglang", "sglang_omni", "qwen3_tts_engine"}


class EngineImportGuard(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".", 1)[0] in BLOCKED:
            return importlib.util.spec_from_loader(fullname, self)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        raise ImportError(f"The standalone TTS task blocks engine import {module.__name__}")


def verify_assets(root, manifest):
    """Verify the actual checkpoint and tokenizer bytes before loading."""
    result = []
    for entry in manifest["files"]:
        path = root / entry["path"]
        if not path.is_file() or path.stat().st_size != entry["bytes"]:
            raise ValueError(f"Missing or wrong-size model asset {entry['path']}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != entry["sha256"]:
            raise ValueError(f"Model asset hash mismatch {entry['path']}")
        result.append(
            {"path": entry["path"], "bytes": entry["bytes"], "sha256": digest.hexdigest()}
        )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--identity-output", type=Path, required=True)
    parser.add_argument("--queue-size", type=int, default=128)
    parser.add_argument("--request-timeout-seconds", type=float, default=600)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535 or args.queue_size < 1 or args.request_timeout_seconds <= 0:
        parser.error("Invalid port, queue capacity or request timeout")
    allocated = os.environ.get("ASCEND_RT_VISIBLE_DEVICES", "").split(",")
    if len(allocated) != 1 or not allocated[0].strip().isdigit():
        parser.error("Run inside one caller-managed NPU allocation")
    if args.identity_output.exists():
        parser.error("identity-output must be new")
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "model-assets.json").read_text(encoding="utf-8"))
    assets = verify_assets(args.model_path.resolve(), manifest)
    args.task_identity = {
        "task_sha256": hashlib.sha256((root / "task.json").read_bytes()).hexdigest(),
        "source_sha256": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in ("baseline.py", "inference.py", "service.py")
        },
    }
    if any(name.split(".", 1)[0] in BLOCKED for name in sys.modules):
        raise RuntimeError("Start the standalone reference in a fresh process")
    sys.meta_path.insert(0, EngineImportGuard())
    from inference import SynthesisModel
    from service import serve

    serve(args, SynthesisModel, assets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
