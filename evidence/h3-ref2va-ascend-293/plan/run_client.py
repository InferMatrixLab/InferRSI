"""Ref2VA HTTP timing using the pinned upstream H3 accuracy request contract.

Run against an already reserved and warmed/configured server. This client does
not reserve devices, choose an optimization, or establish media quality.
"""

import argparse
import json
import subprocess
import time
from pathlib import Path

import requests


def request(args, label, seconds, seed):
    data = {
        "prompt": args.prompt.read_text(),
        "width": "1344",
        "height": "768",
        "fps": "24",
        "seed": str(seed),
        "flow_shift": "12.0",
        "num_inference_steps": str(args.steps),
        "quality": args.quality,
        "extra_params": json.dumps(
            {"task": "ref2va", "duration": seconds, "aspect_ratio": "16:9", "audio_flow_shift": 3.0}
        ),
    }
    record = {"label": label, "seconds": seconds, "seed": seed, "steps": args.steps, "valid": False}
    start = None
    try:
        with args.video.open("rb") as video, args.audio.open("rb") as audio:
            start = time.perf_counter()
            response = requests.post(
                args.base_url.rstrip("/") + "/v1/videos/sync",
                data=data,
                files=[
                    ("input_references", ("reference.mp4", video, "video/mp4")),
                    ("input_references", ("reference.mp3", audio, "audio/mpeg")),
                ],
                timeout=args.timeout,
            )
            record["e2e_ms"] = (time.perf_counter() - start) * 1000
        record.update(http_status=response.status_code, bytes=len(response.content))
        record["response_metrics"] = {
            name: response.headers[name]
            for name in (
                "X-Request-Id",
                "X-Inference-Time-S",
                "X-Stage-Durations",
                "X-Peak-Memory-MB",
            )
            if name in response.headers
        }
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:1000]}")
        output = args.output / f"{label}.mp4"
        output.write_bytes(response.content)
        media = json.loads(
            subprocess.check_output(
                ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(output)], timeout=120
            )
        )
        record["media"] = media
        videos = [s for s in media["streams"] if s["codec_type"] == "video"]
        audios = [s for s in media["streams"] if s["codec_type"] == "audio"]
        if len(videos) != 1 or len(audios) != 1:
            raise ValueError("Exactly one video and audio stream required")
        v, a = videos[0], audios[0]
        fps_n, fps_d = map(int, v["avg_frame_rate"].split("/"))
        expected = (1344, 768, 24, {5: 124, 15: 362}[seconds], 32000, 2)
        actual = (
            v["width"],
            v["height"],
            fps_n / fps_d,
            int(v["nb_frames"]),
            int(a["sample_rate"]),
            a["channels"],
        )
        if actual != expected:
            raise ValueError(f"Media contract mismatch: {actual} != {expected}")
        record["valid"] = True
    except Exception as exc:
        record["error"] = str(exc)
        if start is not None and "e2e_ms" not in record:
            record["failed_elapsed_ms"] = (time.perf_counter() - start) * 1000
    (args.output / f"{label}.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({k: v for k, v in record.items() if k != "media"}), flush=True)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:19421")
    for name in ("prompt", "video", "audio", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--seconds", type=int, choices=(5, 15), nargs="+", default=[5, 15])
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--quality", choices=("lossless", "high"), default="lossless")
    parser.add_argument("--timeout", type=float, default=14400)
    args = parser.parse_args()
    if args.steps < 1 or args.repeats < 1 or args.timeout <= 0:
        parser.error("steps, repeats and timeout must be positive")
    args.output.mkdir(parents=True, exist_ok=False)
    results = []
    for seconds in args.seconds:
        jobs = [(f"warmup-{seconds}", args.seeds[0])]
        jobs += [
            (f"measured-{seconds}-seed{seed}-{repeat}", seed)
            for seed in args.seeds
            for repeat in range(args.repeats)
        ]
        for label, seed in jobs:
            result = request(args, label, seconds, seed)
            results.append(result)
            (args.output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
            if not result["valid"]:
                raise SystemExit(1)


if __name__ == "__main__":
    main()
