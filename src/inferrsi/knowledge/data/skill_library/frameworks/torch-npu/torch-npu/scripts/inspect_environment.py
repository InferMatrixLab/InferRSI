"""Report package facts without paths; device execution requires --device."""

import argparse
import json
import platform
from importlib import metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--device",
        action="store_true",
        help="Import TorchNPU and run a tiny synchronized NPU operation",
    )
    args = parser.parse_args()
    report = {"python": platform.python_version(), "platform": platform.system(), "packages": {}}
    for package in ("torch", "torch-npu"):
        try:
            report["packages"][package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            report["packages"][package] = None
    if not args.device:
        report["device_check"] = "NOT_RUN"
        print(json.dumps(report, indent=2))
        return 0
    try:
        import torch
        import torch_npu  # noqa: F401
    except (ImportError, OSError, RuntimeError) as error:
        # Avoid propagating exception text that may contain private paths.
        report["device_check"] = "BLOCKED_REQUIRED_BACKEND"
        report["failure_phase"] = "import"
        report["error_type"] = type(error).__name__
        print(json.dumps(report, indent=2))
        return 2
    try:
        if not torch.npu.is_available():
            report["device_check"] = "BLOCKED_REQUIRED_BACKEND"
            print(json.dumps(report, indent=2))
            return 2
        x = torch.ones((2, 2), device="npu")
        y = x @ x
        torch.npu.synchronize()
        torch.testing.assert_close(y.cpu(), torch.full((2, 2), 2.0))
        report["device_check"] = "PASS"
        report["scope"] = "tiny device operation only"
    except Exception as error:
        report["device_check"] = "NATIVE_FAIL"
        report["error_type"] = type(error).__name__
        print(json.dumps(report, indent=2))
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
