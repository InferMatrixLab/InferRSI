"""Frozen release-example HTTP workloads; no generation POST is retried."""

import argparse
import base64
import hashlib
import io
import json
import statistics
import time
from pathlib import Path

import numpy as np
import requests
from PIL import Image


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def run(args):
    plan = json.loads(args.plan.read_text())
    for name, expected in plan["assets"].items():
        if digest((args.examples / name).read_bytes()) != expected["sha256"]:
            raise ValueError(f"Frozen input changed: {name}")
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "images").mkdir()
    write_json(args.output / "workload.json", plan)
    session = requests.Session()
    session.trust_env = False
    workloads = [w for w in plan["workloads"] if w["id"] in args.workloads]
    records = []
    reference = (args.examples / "reference1.png").read_bytes()
    t2i = json.loads((args.examples / "request.t2i.json").read_text())
    failure = None
    for workload in workloads:
        seeds = plan["additional_quality_seeds"] if args.quality else [plan["seed"]]
        for seed in seeds:
            warmups, repeats = (0, 1) if args.quality else (args.warmups, args.repeats)
            for index in range(warmups + repeats):
                fields = {
                    "model": args.model,
                    "prompt": t2i["prompt"] if workload["task"] == "t2i" else
                    (args.examples / "prompt.edit.txt").read_text(),
                    "size": workload["size"], "seed": seed,
                    "generator_device": "cpu", "num_inference_steps": 6,
                    "response_format": "b64_json", "output_format": "png",
                    "output_compression": 100,
                }
                if args.stage_metrics:
                    fields["return_stage_metrics"] = True
                row = {"workload": workload["id"], "seed": seed,
                       "index": index, "warmup": index < warmups,
                       "request": fields, "complete": False}
                records.append(row)
                write_json(args.output / "requests.json", records)
                endpoint = "/v1/images/generations"
                if workload["task"] == "edit":
                    endpoint = "/v1/images/edits"
                    body = {k: str(v).lower() if isinstance(v, bool) else str(v)
                            for k, v in fields.items()}
                    req = requests.Request("POST", args.base_url + endpoint, data=body,
                                           files={"image": ("reference1.png", reference, "image/png")})
                else:
                    req = requests.Request("POST", args.base_url + endpoint, json=fields)
                prepared = session.prepare_request(req)
                try:
                    start = time.perf_counter()
                    response = session.send(prepared, timeout=args.timeout, stream=True)
                    content = response.content
                    row["latency_s"] = time.perf_counter() - start
                    row["http_status"] = response.status_code
                    row["response_bytes"] = len(content)
                    response.raise_for_status()
                    payload = json.loads(content)
                    if len(payload["data"]) != 1:
                        raise ValueError("Expected exactly one image")
                    png = base64.b64decode(payload["data"][0]["b64_json"], validate=True)
                    with Image.open(io.BytesIO(png)) as image:
                        image.load()
                        if image.format != "PNG" or image.size != tuple(map(int, workload["size"].split("x"))):
                            raise ValueError("Image format or dimensions differ from frozen workload")
                        rgb = np.array(image.convert("RGB"))
                        if np.all(rgb == rgb[0, 0]):
                            raise ValueError("Constant-color output")
                    name = f"{workload['id']}-seed{seed}-{index}.png"
                    (args.output / "images" / name).write_bytes(png)
                    row.update(complete=True, image="images/" + name,
                               png_sha256=digest(png), rgb_sha256=digest(rgb.tobytes()),
                               image_shape=list(rgb.shape), metrics=payload.get("metrics"))
                    print(f"{workload['id']} seed={seed} index={index} "
                          f"warmup={row['warmup']} E2E={row['latency_s']:.4f}s", flush=True)
                except Exception as exc:
                    row["error"] = f"{type(exc).__name__}: {exc}"
                    failure = row["error"]
                    print(failure, flush=True)
                write_json(args.output / "requests.json", records)
                if failure:
                    break
            if failure:
                break
        if failure:
            break
    summaries = {}
    for workload in workloads:
        values = [r["latency_s"] for r in records if r["workload"] == workload["id"]
                  and not r["warmup"] and r["complete"]]
        if values:
            median = statistics.median(values)
            summaries[workload["id"]] = {
                "samples_s": values, "median_s": median,
                "target_s": workload["target_s"],
                "target_met": median <= workload["target_s"],
                "h200_inverse_latency_fraction": workload["h200_s"] / median,
            }
    expected = len(workloads) * (len(plan["additional_quality_seeds"]) if args.quality
                                  else args.warmups + args.repeats)
    result = {"workloads": summaries, "requests": len(records),
              "expected_requests": expected, "stage_metrics_enabled": args.stage_metrics,
              "quality_run": args.quality,
              "evidence": {"requests_complete": len(records) == expected and all(r["complete"] for r in records)},
              "error": failure}
    if len(summaries) == len(workloads):
        result["metrics"] = {"max_target_latency_ratio": max(
            v["median_s"] / v["target_s"] for v in summaries.values())}
    write_json(args.output / "summary.json", result)
    return 0 if result["evidence"]["requests_complete"] else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:18120")
    parser.add_argument("--model", default="MiniMaxAI/MiniMax-H3-Image")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--examples", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workloads", nargs="+", default=["W1", "W2", "W3"], choices=["W1", "W2", "W3"])
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=1800)
    parser.add_argument("--quality", action="store_true")
    parser.add_argument("--stage-metrics", action="store_true")
    args = parser.parse_args()
    if args.warmups < 0 or args.repeats < 1 or args.timeout <= 0:
        parser.error("Invalid warmup/repeat/timeout")
    raise SystemExit(run(args))
