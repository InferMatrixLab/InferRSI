import argparse
import gzip
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser(
    description="Export completed same-GPU control metrics and redact ASR transcripts."
)
parser.add_argument("--runs", type=Path, required=True)
parser.add_argument("--evidence", type=Path, required=True)
args = parser.parse_args()
r = args.runs
e = args.evidence
paths = [
    r / f"quality/vllm-final-fresh-{role}-c{c}.json"
    for role in ("main", "candidate", "torch_mps")
    for c in (16, 32)
]
while True:
    try:
        docs = [json.loads(p.read_text()) for p in paths]
        if all(set(d["tasks"]) == {"wer", "sim", "utmos"} and "summary" in d for d in docs):
            break
    except (OSError, ValueError):
        pass
    time.sleep(3)
spec = importlib.util.spec_from_file_location("summarize", e / "validator/summarize_results.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
profiles = {
    role: m.aggregate(r / f"vllm-final-fresh-{role}") for role in ("main", "candidate", "torch_mps")
}
ratios = []
for c in (16, 32):
    rates = {
        role: next(row["throughput_frames_s_mean"] for row in rows if row["concurrency"] == c)
        for role, rows in profiles.items()
    }
    ratios.append(
        {
            "concurrency": c,
            "candidate_over_main": rates["candidate"] / rates["main"],
            "torch_mps_over_main": rates["torch_mps"] / rates["main"],
            "candidate_over_torch_mps": rates["candidate"] / rates["torch_mps"],
        }
    )
out = {
    "scope": (
        "Sequential same-GPU fresh main, candidate, then Torch plus MPS control; "
        "one measured repeat at C16/C32 on reused first cohort. "
        "Descriptive attribution only, not independent quality qualification."
    ),
    "profiles": profiles,
    "ratios": ratios,
    "quality": {p.stem: d["summary"] for p, d in zip(paths, docs)},
}
(e / "results/final-same-gpu-controls.json").write_text(json.dumps(out, indent=2) + "\n")
for d in docs:
    for row in d["rows"].values():
        row["wer"].pop("hyp_text", None)
(e / "results/final-controls-quality.json.gz").write_bytes(
    gzip.compress(
        (json.dumps({p.stem: d for p, d in zip(paths, docs)}, indent=2) + "\n").encode(), mtime=0
    )
)
for role in ("main", "candidate", "torch_mps"):
    subprocess.run(
        [
            sys.executable,
            str(e / "validator/export_metrics.py"),
            str(r / f"vllm-final-fresh-{role}"),
            str(e / f"results/vllm-final-fresh-{role}.json.gz"),
        ],
        check=True,
    )
print("FINAL CONTROLS ARTIFACTS COMPLETE", flush=True)
