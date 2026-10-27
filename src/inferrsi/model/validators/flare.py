import argparse
import hashlib
import json
import statistics
import struct
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ...infra import artifacts

SOURCE = {
    "repository": "https://github.com/NVIDIA/flare-local-inference",
    "revision": "bce032c014bae34502ba22d3304fa084d5b40afe",
    "readset": ["qualify/performance.py", "qualify/provenance.py"],
}
METRIC = {
    "key": "metrics.delivery_ttft_ns",
    "unit": "ns",
    "clock_domain": "client.perf_counter_ns.elapsed",
    "grouping": "SSE event token groups; median across measured ttft-512 requests",
    "comparison_scope": "flare_http_delivery_ttft_512",
}
UPSTREAM_CLOCK = (
    "client perf_counter_ns; native token timestamps are a separate process-relative domain"
)
SCHEMA = "inferrsi-flare-delivery-packet-v1"
COUNTERS = (
    "flare_cache_reused_tokens_total",
    "flare_requests_completed_total",
    "flare_requests_failed_total",
    "flare_requests_cancelled_total",
)
RESOURCES = (
    "flare_active_requests",
    "flare_free_request_slots",
    "flare_retiring_request_slots",
    "flare_pending_requests",
    "flare_free_kv_pages",
    "flare_cached_kv_pages",
    "flare_free_snapshots",
    "flare_cached_checkpoints",
)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _integer(value, label, minimum=0):
    _require(type(value) is int and value >= minimum, f"invalid {label}")
    return value


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _load(path):
    root = path.resolve().parent
    raw_manifest = path.read_bytes()
    manifest = json.loads(raw_manifest)
    _require(manifest["schema"] == SCHEMA, "unsupported packet schema")
    _require(manifest["source"] == SOURCE, "unsupported source/readset identity")
    _require(manifest["metric"] == METRIC, "unsupported metric clock/grouping/scope")
    _require(type(manifest["synthetic"]) is bool, "synthetic must be explicit")
    _require(isinstance(manifest["files"], dict), "files must map paths to digests")
    files, identities = {}, {}
    for name, expected in manifest["files"].items():
        location = (root / name).resolve()
        _require(
            not Path(name).is_absolute() and location.is_relative_to(root),
            "packet file escapes its root",
        )
        _require(location != path.resolve(), "manifest cannot be its own asset")
        if name == manifest["package"]:
            actual = artifacts.sha256(location)
        else:
            files[name] = location.read_bytes()
            actual = _sha(files[name])
        _require(actual == expected, f"input digest mismatch: {name}")
        identities[name] = actual
    _require(manifest["package"] in identities, "missing package bytes")
    return manifest, files, {"manifest_sha256": _sha(raw_manifest), "files": identities}


def _corpus(corpus):
    _require(corpus["schema"] == "flare-http-performance-v1-corpus", "unsupported corpus schema")
    repetitions = _integer(corpus["repetitions"], "corpus repetitions", 1)
    expected = [("warmup", "decode", 4, -1, False)]
    for repetition in range(repetitions):
        expected.extend(
            (f"ttft-{length}-r{repetition}", f"ttft-{length}", 1, repetition, True)
            for length in (512, 4096)
        )
        expected.extend(
            (f"decode-b{batch}-r{repetition}", f"decode-b{batch}", batch, repetition, True)
            for batch in (1, 2, 4)
        )
        expected.extend(
            [
                (f"prefill-65536-r{repetition}", "prefill-65536", 1, repetition, True),
                (f"prefix-seed-r{repetition}", "prefix-seed", 1, repetition, False),
                (f"prefix-hit-r{repetition}", "prefix-hit", 1, repetition, True),
            ]
        )
    groups = corpus["groups"]
    actual = [(g["id"], g["kind"], g["batch"], g["repetition"], g["measured"]) for g in groups]
    _require(actual == expected, "missing or changed corpus group")
    cases = {case["id"]: case for case in corpus["cases"]}
    _require(len(cases) == len(corpus["cases"]), "duplicate corpus case")
    used = []
    for group in groups:
        _require(len(group["cases"]) == group["batch"], "group batch/case mismatch")
        for name in group["cases"]:
            case = cases[name]
            used.append(name)
            _require(case["group"] == group["id"], "case/group mismatch")
            tokens = case["prompt_tokens"]
            length = {
                "ttft-4096": 4096,
                "prefix-seed": 4096,
                "prefix-hit": 4107,
                "prefill-65536": 65536,
            }.get(group["kind"], 512)
            output = 256 if group["kind"].startswith("decode") else 1
            _require(len(tokens) == length and case["output_tokens"] == output, "token geometry")
            _require(
                all(type(t) is int and 0 <= t < 248320 for t in tokens), "invalid prompt tokens"
            )
            request = case["request"]
            _require(
                request["model"] == corpus["model_id"] and request["max_tokens"] == output,
                "request/model/output mismatch",
            )
            for key, data in (
                ("request_sha256", _encoded(request)),
                ("prompt_tokens_sha256", struct.pack(f"<{len(tokens)}I", *tokens)),
                ("rendered_prompt_sha256", case["rendered_prompt"].encode()),
            ):
                _require(case[key] == _sha(data), f"corpus fingerprint mismatch: {key}")
            if group["kind"] == "prefix-hit":
                seed = cases[case["prefix_seed"]]
                _require(
                    case["expected_cache"] == "prefix-4096"
                    and seed["group"] == f"prefix-seed-r{group['repetition']}"
                    and tokens[:4096] == seed["prompt_tokens"],
                    "prefix token identity mismatch",
                )
            else:
                _require(case["expected_cache"] == "cold", "unexpected cache condition")
    _require(sorted(used) == sorted(cases), "duplicate or missing case coverage")
    return groups, cases


def _sse(raw):
    payloads, data = [], []
    for line in raw.decode("utf-8").splitlines():
        if not line:
            if data:
                value = "\n".join(data)
                payloads.append(value if value == "[DONE]" else json.loads(value))
                data = []
        elif line.startswith("data:"):
            data.append(line[5:].removeprefix(" "))
    _require(not data and bool(payloads), "missing or truncated raw SSE")
    return payloads


def _observation(observation, raw, case):
    _require(observation["case"] == case["id"], "observation case mismatch")
    _require(observation["status"] == 200 and not observation.get("client_error"), "client failure")
    _integer(observation["request_start_perf_counter_ns"], "client request start")
    events = observation["events"]
    _require([e["data"] for e in events] == _sse(raw), "raw SSE/event grouping mismatch")
    delivery, native, ids, prompts = [], [], [], []
    usages, finishes, metadata, cached_counts = [], [], [], []
    done, previous = 0, 0
    for index, event in enumerate(events):
        timestamp = _integer(event["elapsed_ns"], "client event timestamp")
        _require(timestamp >= previous, "nonmonotonic client clock")
        previous = timestamp
        payload = event["data"]
        if payload == "[DONE]":
            done += 1
            _require(index == len(events) - 1, "events after DONE")
            continue
        _require(isinstance(payload, dict) and "error" not in payload, "stream error")
        if payload.get("prompt_token_ids") is not None:
            prompts.append(payload["prompt_token_ids"])
        if payload.get("usage") is not None:
            usages.append(payload["usage"])
        if payload.get("performance") is not None:
            metadata.append(payload["performance"])
        if payload.get("reused_prompt_tokens") is not None:
            cached_counts.append(payload["reused_prompt_tokens"])
        for choice in payload.get("choices", []):
            _require(choice["index"] == 0, "unexpected choice index")
            if choice.get("finish_reason") is not None:
                finishes.append(choice["finish_reason"])
            tokens = choice.get("token_ids")
            times = choice.get("token_timestamps_ns")
            if tokens is None:
                _require(not times, "timestamps without tokens")
                continue
            _require(
                isinstance(tokens, list)
                and all(type(t) is int and 0 <= t < 248320 for t in tokens),
                "invalid output tokens",
            )
            _require(
                isinstance(times, list) and len(times) == len(tokens),
                "missing or unaligned native timestamps",
            )
            native.extend(_integer(t, "native timestamp") for t in times)
            ids.extend(tokens)
            if tokens:
                delivery.append({"timestamp_ns": timestamp, "token_ids": tokens})
    _require(done == 1 and delivery and finishes == ["length"], "incomplete stream")
    _require(prompts == [case["prompt_tokens"]], "prompt token mismatch")
    _require(len(ids) == case["output_tokens"], "incomplete generated tokens")
    _require(usages and metadata, "missing usage/native timing")
    usage, timing = usages[-1], metadata[-1]
    _require(
        usage["prompt_tokens"] == len(case["prompt_tokens"])
        and usage["completion_tokens"] == len(ids)
        and usage["total_tokens"] == len(case["prompt_tokens"]) + len(ids),
        "usage mismatch",
    )
    ingress = _integer(timing["ingress_ns"], "native ingress")
    enqueue = _integer(timing["enqueue_ns"], "native enqueue")
    _require(ingress <= enqueue <= native[0], "native clock order")
    _require(all(a <= b for a, b in zip(native, native[1:])), "nonmonotonic native clock")
    reused = _integer(timing["reused_prompt_tokens"], "actual reused tokens")
    expected_reuse = 4096 if case["expected_cache"] == "prefix-4096" else 0
    _require(reused == expected_reuse, "actual reused tokens mismatch")
    cached_counts.append(reused)
    if "prompt_tokens_details" in usage:
        cached_counts.append(usage["prompt_tokens_details"]["cached_tokens"])
    _require(all(type(n) is int and n == reused for n in cached_counts), "cache counter mismatch")
    singleton = all(len(group["token_ids"]) == 1 for group in delivery)
    itl = [b["timestamp_ns"] - a["timestamp_ns"] for a, b in zip(delivery, delivery[1:])]
    analysis = observation.get("analysis", {})
    if "passed" in analysis:
        _require(analysis["passed"] is True, "reported failed observation")
    for key, value in (
        ("token_groups", delivery),
        ("delivery_itl_exact", singleton),
        ("delivery_itl_ns", itl if singleton else []),
    ):
        if key in analysis:
            _require(analysis[key] == value, "expanded or changed coalesced event grouping")
    ttft = delivery[0]["timestamp_ns"]
    _require(ttft > 0, "delivery TTFT must be positive")
    return {
        "case": case["id"],
        "delivery_ttft_ns": ttft,
        "reused_prompt_tokens": reused,
        "token_groups": delivery,
        "delivery_itl_exact": singleton,
        "coalesced_groups": sum(len(group["token_ids"]) > 1 for group in delivery),
    }


def _counters(raw):
    values = {}
    required = set(COUNTERS + RESOURCES)
    for line in raw.decode("utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts[0] not in required:
            continue
        _require(len(parts) == 2 and parts[0] not in values, "ambiguous metrics snapshot")
        value = Decimal(parts[1])
        _require(value.is_finite() and value >= 0 and value == int(value), "invalid counter")
        values[parts[0]] = int(value)
    _require(set(values) == required, "missing raw counter/resource sample")
    _require(
        all(
            values[name] == 0
            for name in (
                "flare_active_requests",
                "flare_retiring_request_slots",
                "flare_pending_requests",
            )
        )
        and values["flare_free_request_slots"] == 4,
        "scheduler is not idle",
    )
    return values


def adapt(packet_path: Path) -> dict:
    manifest, files, identities = _load(packet_path)
    corpus = json.loads(files[manifest["corpus"]])
    groups, cases = _corpus(corpus)
    measurements = json.loads(files[manifest["measurements"]])
    memory = json.loads(files[manifest["memory_report"]])
    _require(measurements["backend"] == "flare", "only native Flare packets are supported")
    _require(measurements["measurement"]["clock"] == UPSTREAM_CLOCK, "wrong clock domain")
    capacity = _integer(memory["prefill_chunk_size"], "prepared prefill capacity", 1)
    _require(
        capacity in (512, 4096) and capacity == measurements["prefill_chunk_size"],
        "prepared capacity mismatch",
    )
    _require(
        not measurements["errors"] and measurements["passed"] is True,
        "qualification contains failed groups",
    )
    _require(
        [g["id"] for g in measurements["groups"]] == [g["id"] for g in groups],
        "missing or changed measurement group",
    )
    _require(all(g["passed"] is True for g in measurements["groups"]), "reported failed group")
    observations = measurements["observations"]
    _require(
        sorted(o["case"] for o in observations) == sorted(cases),
        "missing or duplicate raw observations",
    )
    recomputed, samples = [], []
    for group in groups:
        root = f"{manifest['run']}/{group['id']}"
        before_name, after_name = manifest["snapshots"][group["id"]]
        before, after = _counters(files[before_name]), _counters(files[after_name])
        results = []
        for name in group["cases"]:
            observation = json.loads(files[f"{root}/{name}/observation.json"])
            expected = observation
            analysis = observation.get("analysis", {})
            ttft = analysis.get("delivery_ttft_ns")
            if (
                group["kind"] in ("ttft-4096", "prefill-65536")
                and ttft
                and "http_prefill_tokens_per_second" not in analysis
            ):
                # Pinned Flare adds this derived value only after saving the sidecar.
                expected = {
                    **observation,
                    "analysis": {
                        **analysis,
                        "http_prefill_tokens_per_second": (
                            len(cases[name]["prompt_tokens"]) * 1e9 / ttft
                        ),
                    },
                }
            _require(
                observation in observations or expected in observations,
                "observation sidecar differs",
            )
            request = json.loads(files[f"{root}/{name}/request.json"])
            expected_request = dict(cases[name]["request"])
            expected_request.update(
                stream=True,
                return_token_ids=True,
                stream_options={"include_usage": True},
                return_token_timestamps=True,
            )
            _require(request == expected_request, "sent request differs from frozen corpus")
            _require(
                observation["request_sha256"] == _sha(_encoded(request)),
                "sent request fingerprint mismatch",
            )
            result = _observation(observation, files[f"{root}/{name}/response.sse"], cases[name])
            results.append(result)
            if group["kind"] == "ttft-512" and group["measured"]:
                samples.append(result["delivery_ttft_ns"])
        deltas = {name: after[name] - before[name] for name in COUNTERS}
        _require(
            deltas[COUNTERS[0]] == sum(r["reused_prompt_tokens"] for r in results)
            and deltas[COUNTERS[1]] == len(results)
            and deltas[COUNTERS[2]] == deltas[COUNTERS[3]] == 0,
            "request/reuse counter mismatch",
        )
        for free, cached in (
            ("flare_free_kv_pages", "flare_cached_kv_pages"),
            ("flare_free_snapshots", "flare_cached_checkpoints"),
        ):
            _require(
                before[free] + before[cached] == after[free] + after[cached],
                "resource conservation mismatch",
            )
        recomputed.extend(results)
    _require(len(samples) == corpus["repetitions"], "incomplete selected TTFT groups")
    return {
        "schema": "inferrsi-flare-delivery-receipt-v1",
        "status": "validated",
        "synthetic": manifest["synthetic"],
        "source": SOURCE,
        "metric_contract": METRIC,
        "metrics": {"delivery_ttft_ns": statistics.median(samples)},
        "samples_ns": samples,
        "identities": identities,
        "package_sha256": identities["files"][manifest["package"]],
        "corpus_sha256": identities["files"][manifest["corpus"]],
        "prepared_capacity": capacity,
        "observations": recomputed,
        "adapter": {
            "flare.py": artifacts.sha256(__file__),
            "artifacts.py": artifacts.sha256(artifacts.__file__),
        },
        "limits": "Offline delivery contract; task quality and service performance unverified.",
    }


def validate_pair(baseline: Path, candidate: Path) -> dict:
    before, after = adapt(baseline), adapt(candidate)
    for key in (
        "source",
        "metric_contract",
        "synthetic",
        "package_sha256",
        "corpus_sha256",
        "prepared_capacity",
    ):
        _require(before[key] == after[key], f"comparison identity mismatch: {key}")
    return {
        "schema": "inferrsi-flare-pair-receipt-v1",
        "status": "validated",
        "baseline": before,
        "candidate": after,
        "limits": "Pair consistency only; validation_command also needs task-quality gates.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate existing Flare delivery evidence offline."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    measure = commands.add_parser("measure")
    measure.add_argument("--packet", type=Path, required=True)
    measure.add_argument("--peer", type=Path, required=True)
    pair = commands.add_parser("validate-pair")
    pair.add_argument("--baseline", type=Path, required=True)
    pair.add_argument("--candidate", type=Path, required=True)
    for command in (measure, pair):
        command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    inputs = (
        [args.packet, args.peer] if args.command == "measure" else [args.baseline, args.candidate]
    )
    if any(args.output.resolve().is_relative_to(p.resolve().parent) for p in inputs):
        parser.error("output must be outside every input packet directory")
    try:
        pair_receipt = validate_pair(*inputs)
        if args.command == "measure":
            receipt = pair_receipt["baseline"]
            receipt["comparison_peer"] = pair_receipt["candidate"]["identities"]
        else:
            receipt = pair_receipt
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        IndexError,
        InvalidOperation,
        OverflowError,
    ) as exc:
        receipt = {
            "schema": "inferrsi-flare-rejection-v1",
            "status": "rejected",
            "error": str(exc),
            "metrics": {},
        }
        artifacts.write_json(args.output, receipt)
        return 2
    artifacts.write_json(args.output, receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
