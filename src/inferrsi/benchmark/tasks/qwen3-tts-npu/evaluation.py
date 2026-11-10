"""Streaming TTS observations and offline assessment of retained audio evidence."""

import array
import base64
import concurrent.futures
import hashlib
import http.client
import io
import json
import math
import statistics
import sys
import time
import urllib.request
import wave
from pathlib import Path

TASK_FILES = (
    "task.json",
    "workload.jsonl",
    "baseline.py",
    "inference.py",
    "service.py",
    "model-assets.json",
    "TASK.md",
    "sources.json",
    "LICENSE",
    "benchmark.py",
    "evaluation.py",
)


def task_resources():
    return Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def prepare(output, *, concurrencies, warmups, gates, scorer_id):
    """Freeze task, original texts and caller-selected gates before candidate search."""
    if (
        not concurrencies
        or any(type(c) is not int or c < 1 for c in concurrencies)
        or len(set(concurrencies)) != len(concurrencies)
    ):
        raise ValueError("Concurrencies must be distinct positive integers")
    if type(warmups) is not int or warmups < 1:
        raise ValueError("At least one explicit warmup is required")
    if not scorer_id.strip():
        raise ValueError("An immutable audio scorer identity is required")
    required = {
        "min_improvement_pct",
        "max_error_rate_increase",
        "max_speaker_drop",
        "max_duration_change_pct",
        "max_ttfa_regression_pct",
    }
    if set(gates) != required or any(
        type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in gates.values()
    ):
        raise ValueError("All five finite nonnegative campaign gates are required")
    if gates["max_duration_change_pct"] >= 100:
        raise ValueError("The duration gate must reject empty or nearly empty responses")
    workload_bytes = task_resources().joinpath("workload.jsonl").read_bytes()
    request_count = len([line for line in workload_bytes.splitlines() if line.strip()])
    if max(concurrencies) > request_count:
        raise ValueError("Concurrency exceeds the number of requests in the workload")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    for name in TASK_FILES:
        (output / name).write_bytes(task_resources().joinpath(name).read_bytes())
    policy = {
        "schema_version": 1,
        "task_sha256": sha((output / "task.json").read_bytes()),
        "workload_sha256": sha((output / "workload.jsonl").read_bytes()),
        "concurrencies": concurrencies,
        "warmups": warmups,
        "quality_scorer_id": scorer_id,
        "gates": gates,
        "grader_sha256": sha(Path(__file__).read_bytes()),
        "baseline_launcher_sha256": sha((output / "baseline.py").read_bytes()),
        "runtime_sha256": {name: sha((output / name).read_bytes()) for name in TASK_FILES},
    }
    write(output / "policy.json", policy)
    return policy


def load_prepared(root):
    root = Path(root)
    policy = read(root / "policy.json")
    if policy["grader_sha256"] != sha(Path(__file__).read_bytes()) or policy[
        "baseline_launcher_sha256"
    ] != sha((root / "baseline.py").read_bytes()):
        raise ValueError("Prepared grader or baseline launcher changed")
    for name, key in (("task.json", "task_sha256"), ("workload.jsonl", "workload_sha256")):
        if sha((root / name).read_bytes()) != policy[key]:
            raise ValueError("Prepared evaluation bytes changed")
    for name in TASK_FILES:
        if policy["runtime_sha256"][name] != sha((root / name).read_bytes()):
            raise ValueError("Prepared task runtime changed: " + name)
    workload = [
        json.loads(line)
        for line in (root / "workload.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return policy, workload, sha((root / "policy.json").read_bytes())


def _remaining(deadline):
    remaining = deadline - time.perf_counter()
    if remaining <= 0:
        raise TimeoutError("Request deadline exceeded")
    return remaining


class _DeadlineReader(io.RawIOBase):
    """Bound each socket read, including partial headers, SSE lines and HTTP chunks."""

    def __init__(self, raw, sock, deadline):
        self.raw, self.sock, self.deadline = raw, sock, deadline

    def readable(self):
        return True

    def readinto(self, buffer):
        self.sock.settimeout(_remaining(self.deadline))
        count = self.raw.readinto(buffer)
        _remaining(self.deadline)
        return count

    def close(self):
        try:
            self.raw.close()
        finally:
            super().close()


class _DeadlineHandler(urllib.request.HTTPHandler, urllib.request.HTTPSHandler):
    """Keep urllib routing and TLS verification; wrap its response before parsing."""

    def __init__(self, deadline):
        urllib.request.HTTPSHandler.__init__(self)
        self.deadline = deadline

    def do_open(self, connection_type, request, **kwargs):
        def response(sock, **options):
            result = http.client.HTTPResponse(sock, **options)
            result.fp = io.BufferedReader(
                _DeadlineReader(result.fp.detach(), sock, self.deadline)
            )
            return result

        def connection(host, **options):
            result = connection_type(host, **options)
            result.response_class = response
            return result

        request.timeout = _remaining(self.deadline)
        return super().do_open(connection, request, **kwargs)


def _request(endpoint, payload, output, request_id, timeout):
    """One attempt, including failed partial audio. SSE chunks may split PCM samples."""
    started = time.perf_counter()
    deadline = started + timeout
    pcm = bytearray()
    record = {
        "id": request_id,
        "payload_sha256": sha(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()),
        "success": False,
        "ttfa_seconds": None,
        "terminal": None,
        "chunks": [],
    }
    try:
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        opener = urllib.request.build_opener(_DeadlineHandler(deadline))
        with opener.open(request, timeout=_remaining(deadline)) as response:
            if response.status != 200 or "text/event-stream" not in response.headers.get(
                "Content-Type", ""
            ):
                raise ValueError("A successful SSE response is required")
            for raw in response:
                _remaining(deadline)
                if not raw.startswith(b"data:"):
                    continue
                event = json.loads(raw[5:])
                kind = event.get("type")
                if record["terminal"] is not None:
                    raise ValueError("Data after terminal event")
                if kind == "speech.audio.delta":
                    if event.get("sample_rate", 24000) != 24000 or event.get("channels", 1) != 1:
                        raise ValueError("Expected 24 kHz mono PCM16")
                    block = base64.b64decode(event["audio"], validate=True)
                    pcm.extend(block)
                    elapsed = time.perf_counter() - started
                    if len(pcm) >= 2 and record["ttfa_seconds"] is None:
                        record["ttfa_seconds"] = elapsed
                    record["chunks"].append({"seconds": elapsed, "bytes": len(block)})
                elif kind == "speech.audio.done":
                    if event.get("finish_reason") in {"length", "abort", "error", "cancelled"}:
                        raise ValueError("Unsuccessful generation termination")
                    record["terminal"] = event
                else:
                    raise ValueError("Unexpected SSE event or server error")
                if len(pcm) > 24000 * 2 * 600:
                    raise ValueError("Response exceeds ten minutes of PCM")
            _remaining(deadline)
        if record["terminal"] is None or not pcm or len(pcm) % 2:
            raise ValueError("Missing terminal, empty PCM or incomplete sample")
        samples = array.array("h", pcm)
        if sys.byteorder != "little":
            samples.byteswap()
        if min(samples) == max(samples):
            raise ValueError("Constant or silent audio")
        record["success"] = True
    except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException) as error:
        # Preserve the error class without storing private endpoint/HTTP error bodies.
        record["error"] = type(error).__name__
    record.update(
        elapsed_seconds=time.perf_counter() - started,
        pcm_sha256=sha(pcm),
        pcm_bytes=len(pcm),
        audio_seconds=len(pcm) / 48000,
    )
    with wave.open(str(output / (request_id + ".wav")), "wb") as audio:
        audio.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        audio.writeframes(pcm)
    write(output / (request_id + ".json"), record)
    return record


def summarize(records, wall_seconds):
    if not records or not positive(wall_seconds) or not all(r["success"] for r in records):
        return None
    return {
        "rtf": statistics.mean(r["elapsed_seconds"] / r["audio_seconds"] for r in records),
        "ttfa_median_ms": statistics.median(r["ttfa_seconds"] for r in records) * 1000,
        "audio_seconds_per_second": sum(r["audio_seconds"] for r in records) / wall_seconds,
    }


def collect(prepared, output, *, endpoint, model, timeout):
    """Observe a caller-managed service. Its lifecycle is owned by the outer Harness."""
    if not positive(timeout):
        raise ValueError("Socket/request timeout must be positive and finite")
    policy, workload, policy_hash = load_prepared(prepared)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    records = {
        "schema_version": 1,
        "policy_sha256": policy_hash,
        "model": model,
        "cohorts": [],
        "status": "running",
        "quality": "NOT_EVALUATED",
    }
    write(output / "result.json", records)
    payloads = [
        {**row, "model": model, "stream": True, "stream_format": "sse", "response_format": "pcm"}
        for row in workload
    ]
    for concurrency in policy["concurrencies"]:
        cohort = {"concurrency": concurrency, "warmups": [], "requests": []}
        records["cohorts"].append(cohort)
        for index in range(policy["warmups"]):
            record = _request(
                endpoint,
                payloads[index % len(payloads)],
                output,
                f"c{concurrency}-w{index}",
                timeout,
            )
            cohort["warmups"].append(record)
            if not record["success"]:
                records["status"] = "request_failure"
                write(output / "result.json", records)
                return records
        started = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [
                pool.submit(
                    _request, endpoint, payload, output, f"c{concurrency}-r{index}", timeout
                )
                for index, payload in enumerate(payloads)
            ]
            cohort["requests"] = [future.result() for future in futures]
        cohort["wall_seconds"] = time.perf_counter() - started
        cohort["metrics"] = summarize(cohort["requests"], cohort["wall_seconds"])
        write(output / "result.json", records)
        if cohort["metrics"] is None:
            records["status"] = "request_failure"
            write(output / "result.json", records)
            return records
    records["status"] = "collected"
    write(output / "result.json", records)
    return records


def _verify_trial(directory, policy, workload, policy_hash):
    document = read(Path(directory) / "result.json")
    if document["policy_sha256"] != policy_hash or document["status"] != "collected":
        raise ValueError("Trial is incomplete or belongs to another prepared evaluation")
    if [c["concurrency"] for c in document["cohorts"]] != policy["concurrencies"]:
        raise ValueError("Missing, reordered or duplicated concurrency cohort")
    retained = {}
    for cohort in document["cohorts"]:
        concurrency = cohort["concurrency"]
        for phase, count, marker in (
            ("warmups", policy["warmups"], "w"),
            ("requests", len(workload), "r"),
        ):
            rows = cohort[phase]
            if [r["id"] for r in rows] != [f"c{concurrency}-{marker}{i}" for i in range(count)]:
                raise ValueError("Missing, duplicated or reordered request")
            for index, row in enumerate(rows):
                payload = {
                    **workload[index % len(workload)],
                    "model": document["model"],
                    "stream": True,
                    "stream_format": "sse",
                    "response_format": "pcm",
                }
                expected_hash = sha(
                    json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
                )
                if not row["success"] or row["payload_sha256"] != expected_hash:
                    raise ValueError("Failed request or changed payload")
                with wave.open(str(Path(directory) / (row["id"] + ".wav")), "rb") as audio:
                    if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (
                        1,
                        2,
                        24000,
                    ):
                        raise ValueError("Changed audio format")
                    pcm = audio.readframes(audio.getnframes())
                if (
                    not pcm
                    or sha(pcm) != row["pcm_sha256"]
                    or len(pcm) != row["pcm_bytes"]
                    or len(pcm) / 48000 != row["audio_seconds"]
                    or not positive(row["elapsed_seconds"])
                    or not positive(row["ttfa_seconds"])
                    or row["ttfa_seconds"] > row["elapsed_seconds"]
                    or not isinstance(row["terminal"], dict)
                    or row["terminal"].get("type") != "speech.audio.done"
                    or row["terminal"].get("finish_reason")
                    in {"length", "abort", "error", "cancelled"}
                ):
                    raise ValueError("Missing or inconsistent retained audio/timing evidence")
                samples = array.array("h", pcm)
                if sys.byteorder != "little":
                    samples.byteswap()
                if min(samples) == max(samples) or sum(c["bytes"] for c in row["chunks"]) != len(
                    pcm
                ):
                    raise ValueError("Constant audio or inconsistent chunk evidence")
                retained[row["id"]] = row
        if (
            not positive(cohort["wall_seconds"])
            or summarize(cohort["requests"], cohort["wall_seconds"]) != cohort["metrics"]
        ):
            raise ValueError("Metrics do not match retained requests")
    return document, retained


def assess(prepared, baseline, candidate, quality):
    """Read retained bytes only. Supplied ASR/speaker scores have a frozen scorer ID."""
    result = {
        "scope": "retained streaming audio and supplied independent quality scores",
        "verdict": "INCONCLUSIVE",
        "reasons": [],
        "speedup": None,
        "policy_sha256": None,
        "cases": [],
    }
    try:
        policy, workload, policy_hash = load_prepared(prepared)
        result["policy_sha256"] = policy_hash
        before, base_rows = _verify_trial(baseline, policy, workload, policy_hash)
        after, cand_rows = _verify_trial(candidate, policy, workload, policy_hash)
        if before["model"] != after["model"]:
            raise ValueError("Served model identities differ")
        scores = read(quality)
        if scores["scorer_id"] != policy["quality_scorer_id"]:
            raise ValueError("Quality scorer identity changed")
        by_side = {}
        for side, rows in (("baseline", base_rows), ("candidate", cand_rows)):
            values = scores[side]
            if len(values) != len(rows) or {s["id"] for s in values} != set(rows):
                raise ValueError("Audio scoring coverage is incomplete")
            by_side[side] = {s["id"]: s for s in values}
            for score in values:
                if score["pcm_sha256"] != rows[score["id"]]["pcm_sha256"]:
                    raise ValueError("Audio scores refer to different PCM bytes")
                if (
                    type(score["error_rate"]) not in (float, int)
                    or not math.isfinite(score["error_rate"])
                    or score["error_rate"] < 0
                    or type(score["speaker_similarity"]) not in (float, int)
                    or not math.isfinite(score["speaker_similarity"])
                    or not -1 <= score["speaker_similarity"] <= 1
                ):
                    raise ValueError("Invalid audio score")
        failed = []
        gates = policy["gates"]
        for request_id, base in base_rows.items():
            cand = cand_rows[request_id]
            bs, cs = by_side["baseline"][request_id], by_side["candidate"][request_id]
            if (
                cs["error_rate"] > bs["error_rate"] + gates["max_error_rate_increase"]
                or cs["speaker_similarity"] < bs["speaker_similarity"] - gates["max_speaker_drop"]
                or abs(cand["audio_seconds"] / base["audio_seconds"] - 1) * 100
                > gates["max_duration_change_pct"]
            ):
                failed.append("Audio quality/duration gate failed for " + request_id)
        for bc, cc in zip(before["cohorts"], after["cohorts"]):
            bm, cm = bc["metrics"], cc["metrics"]
            speedup = bm["rtf"] / cm["rtf"]
            result["cases"].append(
                {
                    "concurrency": bc["concurrency"],
                    "baseline": bm,
                    "candidate": cm,
                    "observed_speedup": speedup,
                }
            )
            gain = (1 - cm["rtf"] / bm["rtf"]) * 100
            if gain <= 0 or gain < gates["min_improvement_pct"]:
                failed.append("RTF gain gate failed at concurrency " + str(bc["concurrency"]))
            if cm["ttfa_median_ms"] > bm["ttfa_median_ms"] * (
                1 + gates["max_ttfa_regression_pct"] / 100
            ):
                failed.append("First-audio gate failed at concurrency " + str(bc["concurrency"]))
        result.update(verdict="FAIL" if failed else "PASS", reasons=failed)
        if not failed:
            result["speedup"] = math.exp(
                statistics.mean(math.log(c["observed_speedup"]) for c in result["cases"])
            )
    except (OSError, ValueError, KeyError, TypeError, wave.Error, ZeroDivisionError) as error:
        result["reasons"].append(type(error).__name__ + ": incomplete or inconsistent evidence")
    return result
