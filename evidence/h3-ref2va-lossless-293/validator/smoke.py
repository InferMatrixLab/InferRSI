import argparse
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

import compare
import lpips
import torch
from integrity import load_scorer

parser = argparse.ArgumentParser(
    description="Synthetic CPU validator regression, not model qualification"
)
parser.add_argument("--alexnet-weights", type=Path, required=True)
parser.add_argument("--lpips-weights", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
validator = Path(__file__).resolve().parent

weights = json.loads((validator / "weights.json").read_text())
alex = args.alexnet_weights
linear = args.lpips_weights
scorer, identity = load_scorer(alex, linear, weights)
original = lpips.LPIPS(net="alex", verbose=False).eval()
assert set(scorer.state_dict()) == set(original.state_dict())
for name, tensor in scorer.state_dict().items():
    assert torch.equal(tensor, original.state_dict()[name]), name
gates = json.loads((validator / "gates.json").read_text())
gates.update(width=64, height=64)
spec = importlib.util.spec_from_file_location(
    "legacy_compare", validator.parent.parent / "h3-ref2va-ascend-293/validator/compare.py"
)
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
with tempfile.TemporaryDirectory() as d:
    p = Path(d)
    for label, duration in [("complete", 0.5), ("truncated", 0.1)]:
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=64x64:rate=24:duration=0.5",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency=440:sample_rate=32000:duration={duration}",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-ar",
                "32000",
                "-ac",
                "2",
                str(p / f"{label}.mp4"),
            ],
            check=True,
        )
    complete = compare.compare(
        p / "complete.mp4", p / "complete.mp4", gates, 12, alex, linear, weights
    )
    assert complete["verdict"] == "PASS", complete
    old = legacy.compare(p / "truncated.mp4", p / "truncated.mp4", gates, 12)
    assert old["verdict"] == "PASS", old
    try:
        compare.compare(p / "truncated.mp4", p / "truncated.mp4", gates, 12, alex, linear, weights)
    except ValueError as exc:
        rejection = str(exc)
    else:
        raise AssertionError("truncated pair accepted")
    result = {
        "synthetic": True,
        "scope": "CPU validator regression only; not model quality or speedup",
        "scorer_state_matches_legacy": True,
        "weights": identity,
        "complete_identity": complete,
        "legacy_truncated_identity": old,
        "new_truncated_rejection": rejection,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
