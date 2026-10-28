"""Use the fixed original ten 8K four-position inputs and unchanged scorer."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retrieval_score import score_response  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    for name in ("source", "fixture", "generation-config", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--endpoint", required=True)
    args = p.parse_args()
    sys.path.insert(0, str(args.source.resolve()))
    from protocol import canonical, sha
    from run import complete, termination_policy

    if (
        sha(args.fixture.read_bytes())
        != "935b24411e897b0a1909fe94587ded8b809d7c6777cceac4e2decce8d239f75e"
    ):
        raise ValueError("retrieval fixture changed")
    all_cases = [json.loads(line) for line in args.fixture.read_bytes().split(b"\n") if line]
    if len(all_cases) != 30:
        raise ValueError("original retrieval cohort changed")
    cases = [row for row in all_cases if row["input_tokens"] == 8192]
    if len(cases) != 10 or len({row["id"] for row in cases}) != 10:
        raise ValueError("8K cohort differs")
    for row in cases:
        if (
            len(row["input_ids"]) != 8192
            or sha(json.dumps(row["input_ids"], separators=(",", ":")).encode())
            != row["input_ids_sha256"]
            or len(row["expected"]) != 4
        ):
            raise ValueError("retrieval input/position identity differs")
    stopping = termination_policy(
        args.generation_config, "e70c136c1b78ddc1fb0905bac8e733a4dc448d4f852a5dd75143fffc70be550e"
    )
    args.output.mkdir(parents=True, exist_ok=False)
    with (args.output / "responses.jsonl").open("xb") as stream:
        for index, case in enumerate(cases):
            body = {
                "model": "qwen38-fp8",
                "prompt": case["input_ids"],
                "max_tokens": case["max_output_tokens"],
                "temperature": 0,
                "ignore_eos": False,
                "return_token_ids": True,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            raw = args.output / f"response-{index:02}.sse"
            try:
                result = complete(
                    args.endpoint, body, raw, 180, eos_token_ids=stopping["eos_token_ids"]
                )
                row = {
                    "id": case["id"],
                    "status": "completed",
                    "input_tokens": 8192,
                    "raw_sha256": sha(raw.read_bytes()),
                    "payload_sha256": sha(canonical(body)),
                    "score": score_response(result["text"], case["expected"]),
                    "output_tokens": result["usage"]["completion_tokens"],
                }
            except Exception as error:
                row = {
                    "id": case["id"],
                    "status": "infrastructure_error",
                    "error_type": type(error).__name__,
                    "raw_sha256": sha(raw.read_bytes()) if raw.exists() else None,
                }
                stream.write(canonical(row) + b"\n")
                stream.flush()
                raise
            stream.write(canonical(row) + b"\n")
            stream.flush()


if __name__ == "__main__":
    main()
