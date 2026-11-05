"""Check that the selected overlay changes only the declared effective knobs."""

import argparse
import copy
import json
from pathlib import Path

from vllm_omni.config.stage_config import resolve_deploy_yaml


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--deploy-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    baseline = resolve_deploy_yaml(a.deploy_dir / "minicpmo_4_5_turn.yaml")
    candidate = resolve_deploy_yaml(a.deploy_dir / "minicpmo_4_5_cpu_reference_trt_mps.yaml")
    normalized = copy.deepcopy(candidate)
    assert normalized["cuda_mps"] is True
    if "cuda_mps" in baseline:
        normalized["cuda_mps"] = baseline["cuda_mps"]
    else:
        normalized.pop("cuda_mps")
    extra = normalized["connectors"]["connector_of_shared_memory"]["extra"]
    base_extra = baseline["connectors"]["connector_of_shared_memory"]["extra"]
    assert extra.pop("token2wav_spk_cpu_reference") is True
    for key, default in [("token2wav_device_spk", True), ("token2wav_trt", False)]:
        assert extra.pop(key) is base_extra.get(key, default)
        if key in base_extra:
            extra[key] = base_extra[key]
    assert normalized == baseline
    a.out.write_text(
        json.dumps(
            {
                "verdict": "PASS",
                "scope": "Resolved settings only, not runtime or speech qualification",
                "effective_changes": ["cuda_mps=true", "token2wav_spk_cpu_reference=true"],
                "baseline": baseline,
                "candidate": candidate,
            },
            indent=2,
        )
        + "\n"
    )
    print("PASS: only declared MPS and CPU-reference speaker settings differ")


if __name__ == "__main__":
    main()
