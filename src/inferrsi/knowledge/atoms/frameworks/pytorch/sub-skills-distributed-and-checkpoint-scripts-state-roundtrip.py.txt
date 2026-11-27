#!/usr/bin/env python3
"""Roundtrip only a self-created tiny state_dict using weights_only and mmap.

Adapted from serialization documentation/test patterns; accepts no input artifact.
"""
import argparse
import json
import tempfile
from pathlib import Path


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        import torch
    except (ImportError, OSError):
        print("MISSING_PACKAGE: select an installed torch environment.")
        return 2
    torch.manual_seed(0)
    source = torch.nn.Linear(2, 1)
    target = torch.nn.Linear(2, 1)
    with tempfile.TemporaryDirectory(prefix="torch-state-contract-") as directory:
        path = Path(directory) / "own_state.pt"
        torch.save(source.state_dict(), path)
        state = torch.load(path, map_location="cpu", weights_only=True, mmap=True)
        target.load_state_dict(state)
        x = torch.ones(2, 2)
        torch.testing.assert_close(source(x), target(x))
        # Release mapped state before temporary-directory removal on Windows.
        del state
    print(json.dumps({"scope": "self_created_state_roundtrip", "weights_only": True,
                      "mmap": True, "dcp_or_untrusted_artifacts_qualified": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
