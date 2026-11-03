#!/usr/bin/env python3
"""Report path-free torch identity; no installation, subprocess or device allocation.

Adapted narrow alternative to upstream torch/utils/collect_env.py; provenance and
upstream notices are retained in ../references/notices.md and ../LICENSE.
"""
import argparse
import importlib.metadata
import json
import platform


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-backend", choices=("cpu", "cuda", "rocm", "mps", "xpu"))
    args = parser.parse_args()
    try:
        import torch
    except (ImportError, OSError) as exc:
        print(json.dumps({"status": "MISSING_PACKAGE", "exception": type(exc).__name__,
                          "action": "Select a compatible installed torch environment."}))
        return 2
    available = {"cpu": True, "cuda": torch.cuda.is_available() and torch.version.hip is None,
                 "rocm": torch.cuda.is_available() and torch.version.hip is not None,
                 "mps": hasattr(torch.backends, "mps") and torch.backends.mps.is_available(),
                 "xpu": hasattr(torch, "xpu") and torch.xpu.is_available()}
    blocked = args.require_backend is not None and not available[args.require_backend]
    print(json.dumps({"status": "BLOCKED_REQUIRED_BACKEND" if blocked else "INSPECTED",
                      "python": platform.python_version(), "os": platform.system(),
                      "machine": platform.machine(), "torch": importlib.metadata.version("torch"),
                      "torch_git_version": torch.version.git_version,
                      "cuda_build": torch.version.cuda, "hip_build": torch.version.hip,
                      "backend_available": available,
                      "scope": "Identity/availability only; no device operation or efficacy claim."
                      }, indent=2))
    return 3 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
