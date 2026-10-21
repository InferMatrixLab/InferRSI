"""Harness-only one-shot runtime fault; never installed into the production server.

Run in its own owned server process. The designated request must complete one
real model call before its next call raises. Later requests use the original
forward function. Evidence explicitly labels this as fault injection.
"""

import hashlib
import sys
from pathlib import Path


def install_fault(engine):
    model = engine.runner.model
    original = model.forward
    provenance = engine.provenance
    marker = {
        "kind": "harness_injected_runtime_error",
        "request_id": "injected-fault",
        "successful_target_calls": 0,
        "triggered": False,
        "source": "examples/qwen38_text/service_fault.py",
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }

    def forward(*args, **kwargs):
        request = engine.runner._requests.get(marker["request_id"])
        target = request is not None and request.state is kwargs.get("state")
        if target and marker["successful_target_calls"] == 1 and not marker["triggered"]:
            marker["triggered"] = True
            raise RuntimeError("Harness-injected generation failure")
        output = original(*args, **kwargs)
        if target:
            marker["successful_target_calls"] += 1
        return output

    model.forward = forward
    engine.provenance = lambda: {**provenance(), "fault_injection": dict(marker)}
    return engine


def main():
    root = Path(sys.argv.pop(1)).resolve(strict=True)
    sys.path.insert(0, str(root))
    import nanovllm
    from nanovllm.qwen38 import server

    if not Path(nanovllm.__file__).resolve().is_relative_to(root):
        raise ValueError("Wrong fault-probe engine origin")
    original = nanovllm.LLM
    nanovllm.LLM = lambda *args, **kwargs: install_fault(original(*args, **kwargs))
    server.main()


if __name__ == "__main__":
    main()
