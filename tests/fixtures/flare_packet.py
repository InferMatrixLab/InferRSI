import argparse
import hashlib
import json
import struct
from pathlib import Path

from inferrsi.model.validators.flare import METRIC, SCHEMA, SOURCE, UPSTREAM_CLOCK


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(value) + b"\n")


def build_packet(root: Path, ttft_ns=100_000_000, repetitions=1):
    root.mkdir(parents=True)
    groups, cases = [], []

    def add(name, kind, batch, repetition, measured):
        names = []
        length = {
            "ttft-4096": 4096,
            "prefix-seed": 4096,
            "prefix-hit": 4107,
            "prefill-65536": 65536,
        }.get(kind, 512)
        output = 256 if kind.startswith("decode") else 1
        for lane in range(batch):
            identifier = f"{name}-{lane}"
            tokens = [1000 + len(cases)] * length
            request = {
                "model": "synthetic-fixture-model",
                "max_tokens": output,
                "temperature": 1,
                "top_p": 0.95,
                "top_k": 20,
                "min_p": 0,
                "repetition_penalty": 1,
                "presence_penalty": 0,
                "frequency_penalty": 0,
                "seed": 42,
                "messages": [{"role": "user", "content": identifier}],
                "chat_template_kwargs": {"enable_thinking": False},
                "add_generation_prompt": True,
            }
            case = {
                "id": identifier,
                "group": name,
                "request": request,
                "prompt_tokens": tokens,
                "rendered_prompt": identifier,
                "expected_cache": "cold",
                "output_tokens": output,
            }
            if kind == "prefix-hit":
                seed = next(c for c in cases if c["group"] == f"prefix-seed-r{repetition}")
                case.update(expected_cache="prefix-4096", prefix_seed=seed["id"])
                case["prompt_tokens"] = seed["prompt_tokens"] + [2222] * 11
                case["request"] = json.loads(encoded(seed["request"]))
                case["request"]["messages"][-1]["content"] += " apple" * 11
            for key, data in (
                ("request_sha256", encoded(case["request"])),
                ("prompt_tokens_sha256", struct.pack(f"<{length}I", *case["prompt_tokens"])),
                ("rendered_prompt_sha256", case["rendered_prompt"].encode()),
            ):
                case[key] = hashlib.sha256(data).hexdigest()
            cases.append(case)
            names.append(identifier)
        groups.append(
            {
                "id": name,
                "kind": kind,
                "batch": batch,
                "repetition": repetition,
                "measured": measured,
                "cases": names,
            }
        )

    add("warmup", "decode", 4, -1, False)
    for repetition in range(repetitions):
        for length in (512, 4096):
            add(f"ttft-{length}-r{repetition}", f"ttft-{length}", 1, repetition, True)
        for batch in (1, 2, 4):
            add(f"decode-b{batch}-r{repetition}", f"decode-b{batch}", batch, repetition, True)
        for kind in ("prefill-65536", "prefix-seed", "prefix-hit"):
            add(f"{kind}-r{repetition}", kind, 1, repetition, kind != "prefix-seed")
    corpus = {
        "schema": "flare-http-performance-v1-corpus",
        "model_id": "synthetic-fixture-model",
        "revision": "synthetic-fixture-revision",
        "repetitions": repetitions,
        "nonce": "synthetic",
        "groups": groups,
        "cases": cases,
    }
    write_json(root / "corpus.json", corpus)
    (root / "package.fixture").write_bytes(b"SYNTHETIC FIXTURE; NOT A MODEL OR RUNTIME PACKAGE\n")
    write_json(root / "memory.json", {"prefill_chunk_size": 512})
    measurements = {
        "backend": "flare",
        "prefill_chunk_size": 512,
        "measurement": {"clock": UPSTREAM_CLOCK},
        "groups": [],
        "observations": [],
        "errors": [],
        "passed": True,
    }
    snapshots = {}
    for group in groups:
        folder = root / "run" / group["id"]
        folder.mkdir(parents=True)
        observations = []
        reused = 0
        for identifier in group["cases"]:
            case = next(c for c in cases if c["id"] == identifier)
            local = folder / identifier
            local.mkdir()
            output = list(range(case["output_tokens"]))
            reused_tokens = 4096 if case["expected_cache"] == "prefix-4096" else 0
            reused += reused_tokens
            # Two tokens arrive together in the first event of each decode request.
            chunks = [output] if len(output) == 1 else [output[:2], output[2:]]
            events, token_groups = [], []
            native = 1_000_000_000_000
            for index, tokens in enumerate(chunks):
                elapsed = ttft_ns + index * 20_000_000
                payload = {
                    "usage": None,
                    "prompt_token_ids": None,
                    "performance": None,
                    "reused_prompt_tokens": None,
                    "choices": [
                        {
                            "index": 0,
                            "token_ids": tokens,
                            "token_timestamps_ns": [native + t * 100 for t in tokens],
                        }
                    ],
                }
                events.append({"elapsed_ns": elapsed, "data": payload})
                token_groups.append({"timestamp_ns": elapsed, "token_ids": tokens})
            events.append(
                {
                    "elapsed_ns": ttft_ns + 30_000_000,
                    "data": {
                        "prompt_token_ids": case["prompt_tokens"],
                        "choices": [{"index": 0, "finish_reason": "length"}],
                        "usage": {
                            "prompt_tokens": len(case["prompt_tokens"]),
                            "completion_tokens": len(output),
                            "total_tokens": len(case["prompt_tokens"]) + len(output),
                            "prompt_tokens_details": {"cached_tokens": reused_tokens},
                        },
                        "performance": {
                            "ingress_ns": native - 1000,
                            "enqueue_ns": native - 500,
                            "reused_prompt_tokens": reused_tokens,
                        },
                    },
                }
            )
            events.append({"elapsed_ns": ttft_ns + 40_000_000, "data": "[DONE]"})
            request = dict(case["request"])
            request.update(
                stream=True,
                return_token_ids=True,
                return_token_timestamps=True,
                stream_options={"include_usage": True},
            )
            observation = {
                "case": identifier,
                "request_sha256": hashlib.sha256(encoded(request)).hexdigest(),
                "status": 200,
                "request_start_perf_counter_ns": 99_000_000_000,
                "events": events,
                "analysis": {
                    "passed": True,
                    "delivery_ttft_ns": ttft_ns,
                    "token_groups": token_groups,
                    "delivery_itl_exact": len(output) == 1,
                    "delivery_itl_ns": [],
                },
            }
            write_json(local / "request.json", request)
            raw = b"".join(
                b"data: "
                + (e["data"].encode() if isinstance(e["data"], str) else encoded(e["data"]))
                + b"\n\n"
                for e in events
            )
            (local / "response.sse").write_bytes(raw)
            write_json(local / "observation.json", observation)
            observations.append(observation)
        values = {
            "flare_active_requests": 0,
            "flare_free_request_slots": 4,
            "flare_retiring_request_slots": 0,
            "flare_pending_requests": 0,
            "flare_free_kv_pages": 100,
            "flare_cached_kv_pages": 10,
            "flare_free_snapshots": 10,
            "flare_cached_checkpoints": 2,
            "flare_cache_reused_tokens_total": 0,
            "flare_requests_completed_total": 0,
            "flare_requests_failed_total": 0,
            "flare_requests_cancelled_total": 0,
        }
        names = []
        for side in ("before", "after"):
            if side == "after":
                values.update(
                    flare_cache_reused_tokens_total=reused,
                    flare_requests_completed_total=group["batch"],
                )
            name = f"run/{group['id']}/metrics-{side}-000.txt"
            (root / name).write_bytes("".join(f"{k} {v}\n" for k, v in values.items()).encode())
            names.append(name)
        snapshots[group["id"]] = names
        measurements["groups"].append({"id": group["id"], "passed": True})
        # Pinned Flare augments in-memory analysis after saving observation sidecars.
        for observation in observations:
            ttft = observation["analysis"]["delivery_ttft_ns"]
            if ttft and group["kind"] in ("ttft-4096", "prefill-65536"):
                case = next(c for c in cases if c["id"] == observation["case"])
                observation["analysis"]["http_prefill_tokens_per_second"] = (
                    len(case["prompt_tokens"]) * 1e9 / ttft
                )
        measurements["observations"].extend(observations)
    write_json(root / "measurements.json", measurements)
    manifest = {
        "schema": SCHEMA,
        "source": SOURCE,
        "metric": METRIC,
        "synthetic": True,
        "package": "package.fixture",
        "corpus": "corpus.json",
        "memory_report": "memory.json",
        "measurements": "measurements.json",
        "run": "run",
        "snapshots": snapshots,
        "files": {
            p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*"))
            if p.is_file()
        },
    }
    write_json(root / "packet.json", manifest)
    return root / "packet.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Write a synthetic offline Flare contract fixture."
    )
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(build_packet(args.output))
