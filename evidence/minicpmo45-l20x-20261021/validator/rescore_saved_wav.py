"""Repeat native Qwen3 ASR requests; requires local, unredacted scorer output."""

import argparse
import hashlib
import json
from pathlib import Path

import requests


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--wav", type=Path, required=True)
    p.add_argument("--original-quality", type=Path, required=True)
    p.add_argument("--request-id", required=True)
    p.add_argument("--asr-port", type=int, default=29181)
    p.add_argument("--model", default="Qwen/Qwen3-ASR-1.7B")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    original = json.loads(a.original_quality.read_text())["rows"][a.request_id]["wer"]["hyp_text"]
    hashes, equal = [], []
    for _ in range(a.repeats):
        with a.wav.open("rb") as stream:
            response = requests.post(
                f"http://127.0.0.1:{a.asr_port}/v1/audio/transcriptions",
                data={"model": a.model, "language": "en", "response_format": "json"},
                files={"file": (a.wav.name, stream, "audio/wav")},
                timeout=300,
                proxies={"http": None, "https": None},
            )
        response.raise_for_status()
        text = response.json()["text"]
        hashes.append(hashlib.sha256(text.encode()).hexdigest())
        equal.append(text == original)
    a.out.write_text(
        json.dumps(
            {
                "scope": "Diagnostic only; does not replace frozen scores or remove prompts",
                "request_id": a.request_id,
                "wav_sha256": hashlib.sha256(a.wav.read_bytes()).hexdigest(),
                "original_transcript_sha256": hashlib.sha256(original.encode()).hexdigest(),
                "same_as_original": equal,
                "transcript_sha256": hashes,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
