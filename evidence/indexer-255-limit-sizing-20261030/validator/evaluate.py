"""One frozen paired study; this file does not modify either source tree."""
import argparse
import gzip
import hashlib
import json
import math
import os
import platform
import random
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path

MODES = ("default_api", "context_api", "default_cli", "search_cli")


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def env(root):
    return {"PATH": os.defpath, "PYTHONPATH": str(root / "src"),
            "PYTHONDONTWRITEBYTECODE": "1"}


def identity(root):
    source = {}
    for path in sorted((root / "src").rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            source[path.relative_to(root).as_posix()] = digest(path.read_bytes())
    corpus = {key: val for key, val in source.items() if key.startswith("src/inferrsi/data/")}
    revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                       text=True).strip()
    return {"revision": revision, "source_sha256": digest(encode(source)),
            "corpus_sha256": digest(encode(corpus)), "source_files": source}


def cli(root, mode):
    args = [sys.executable, "-m", "inferrsi"]
    if mode == "search_cli":
        args += ["knowledge", "search", "cgroupv2", "--limit", "5", "--json"]
    else:
        args += ["collect", "", "--limit", "5", "--json"]
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu0 = usage.ru_utime + usage.ru_stime
    start = time.perf_counter_ns()
    completed = subprocess.run(args, cwd=root, env=env(root), capture_output=True,
                               check=True, timeout=180)
    elapsed = time.perf_counter_ns() - start
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = round((usage.ru_utime + usage.ru_stime - cpu0) * 1e9)
    decode_start = time.perf_counter_ns()
    value = json.loads(completed.stdout)
    decode_ns = time.perf_counter_ns() - decode_start
    return value, {"wall_ns": elapsed, "cpu_ns": cpu, "decode_ns": decode_ns,
                   "stdout_bytes": len(completed.stdout)}


def worker(root, capture):
    sys.path.insert(0, str(root / "src"))
    from inferrsi import knowledge_operations
    from inferrsi.knowledge_operations import KnowledgeReader
    assert Path(knowledge_operations.__file__).resolve().is_relative_to(root / "src")
    rows, captures = {}, {}
    for mode in MODES:
        before = time.monotonic_ns()
        load = os.getloadavg()
        if mode.endswith("_api"):
            reader = KnowledgeReader()
            options = {"query": "", "limit": 5}
            if mode == "context_api":
                options.update(relevance="memory", context_bytes=262144)
            reader.collect(**options)
            start_cpu = time.process_time_ns()
            start = time.perf_counter_ns()
            value = reader.collect(**options)
            stats = {"wall_ns": time.perf_counter_ns() - start,
                     "cpu_ns": time.process_time_ns() - start_cpu}
        else:
            value, stats = cli(root, mode)
        payload = encode(value)
        rows[mode] = {**stats, "monotonic_start_ns": before, "loadavg": load,
                      "output_sha256": digest(payload), "output_bytes": len(payload)}
        if capture:
            captures[mode] = value
    assert rows["default_api"]["output_sha256"] == rows["default_cli"]["output_sha256"]
    return {"rows": rows, "captures": captures,
            "module_path_relative": str(Path(knowledge_operations.__file__).relative_to(root)),
            "module_sha256": digest(Path(knowledge_operations.__file__).read_bytes())}


def percentile(values, q):
    return sorted(values)[max(0, math.ceil(len(values) * q) - 1)]


def summary(groups):
    rng = random.Random(25531)
    indices = [[rng.randrange(len(groups)) for _ in groups] for _ in range(10000)]
    result = {}
    for mode in MODES:
        a = [g["A"]["rows"][mode]["wall_ns"] for g in groups]
        b = [g["B"]["rows"][mode]["wall_ns"] for g in groups]
        paired_gain = [100 * (x - y) / x for x, y in zip(a, b)]
        gains = [statistics.median([paired_gain[i] for i in ix]) for ix in indices]
        medchanges, tailchanges = [], []
        for ix in indices:
            aa, bb = [a[i] for i in ix], [b[i] for i in ix]
            medchanges.append(100 * (statistics.median(bb) / statistics.median(aa) - 1))
            tailchanges.append(100 * (percentile(bb, .95) / percentile(aa, .95) - 1))
        row = {
            "n": len(groups), "A_p50_ms": statistics.median(a) / 1e6,
            "B_p50_ms": statistics.median(b) / 1e6,
            "A_p95_ms": percentile(a, .95) / 1e6, "B_p95_ms": percentile(b, .95) / 1e6,
            "paired_median_gain_percent": statistics.median(paired_gain),
            "paired_gain_95ci": [percentile(gains, .025), percentile(gains, .975)],
            "p50_change_percent": 100 * (statistics.median(b) / statistics.median(a) - 1),
            "p95_change_percent": 100 * (percentile(b, .95) / percentile(a, .95) - 1),
            "p50_change_95ci": [percentile(medchanges, .025), percentile(medchanges, .975)],
            "p95_change_95ci": [percentile(tailchanges, .025), percentile(tailchanges, .975)],
        }
        for arm in ("A", "B"):
            cpu = [g[arm]["rows"][mode]["cpu_ns"] for g in groups]
            row[arm + "_cpu_p50_ms"] = statistics.median(cpu) / 1e6
        result[mode] = row
    primary = result["default_api"]
    primary_pass = (primary["paired_median_gain_percent"] >= 5
                    and primary["paired_gain_95ci"][0] > 0)
    point_pass = all(r["p50_change_percent"] <= 10 and r["p95_change_percent"] <= 20
                     for key, r in result.items() if key != "default_api")
    uncertainty_pass = all(r["p50_change_95ci"][1] <= 10
                           for key, r in result.items() if key != "default_api")
    verdict = "FAIL" if not primary_pass or not point_pass else (
        "PASS" if uncertainty_pass else "INCONCLUSIVE")
    return {"paths": result, "primary_pass": primary_pass,
            "secondary_points_pass": point_pass, "secondary_uncertainty_pass": uncertainty_pass,
            "timing_verdict": verdict,
            "note": "Timing only; independent correctness/resource gates also required."}


def run(args):
    roots = {"A": Path(args.baseline).resolve(), "B": Path(args.candidate).resolve()}
    output = Path(args.output).resolve()
    output.mkdir(exist_ok=False)
    freeze = json.loads(Path(__file__).with_name("candidate-runner-freeze.json").read_text())
    assert digest(Path(__file__).read_bytes()) == freeze["files"]["evaluate.py"]
    identities = {arm: identity(root) for arm, root in roots.items()}
    assert identities["A"]["revision"] == freeze["baseline"]
    assert identities["B"]["revision"] == freeze["candidate"]
    (output / "environment.json").write_bytes(encode({
        "python": sys.version, "platform": platform.system(),
        "release": platform.release(), "machine": platform.machine(),
        "cpu_count": os.cpu_count(), "freeze": freeze,
    }))
    assert identities["A"]["corpus_sha256"] == identities["B"]["corpus_sha256"]
    (output / "identities-before.json").write_bytes(encode(identities))
    (output / "runner.sha256").write_text(digest(Path(__file__).read_bytes()) + "\n")
    groups = []
    order = ["AB"] * 60 + ["BA"] * 60
    random.Random(25530).shuffle(order)
    (output / "order.json").write_bytes(encode(order))
    for number, arms in enumerate(order):
        group = {"group": number, "order": arms}
        for arm in arms:
            command = [sys.executable, str(Path(__file__).resolve()), "--worker",
                       str(roots[arm])]
            if number == 0:
                command.append("--capture")
            proc = subprocess.run(command, cwd=roots[arm], env=env(roots[arm]),
                                  capture_output=True, check=True, timeout=900)
            result = json.loads(proc.stdout)
            # Retain each completed arm before the other arm can fail.
            (output / f"group-{number:03d}-{arm}.json").write_bytes(encode(result))
            captures = result.pop("captures")
            if captures:
                (output / (arm + "-capture.json.gz")).write_bytes(
                    gzip.compress(encode(captures), mtime=0))
            group[arm] = result
        for mode in MODES:
            assert group["A"]["rows"][mode]["output_sha256"] == (
                group["B"]["rows"][mode]["output_sha256"]), (number, mode)
        groups.append(group)
        with (output / "groups.jsonl").open("ab") as stream:
            stream.write(encode(group) + b"\n")
        print(f"{number + 1}/120 paired groups retained", flush=True)
    after = {arm: identity(root) for arm, root in roots.items()}
    (output / "identities-after.json").write_bytes(encode(after))
    assert identities == after
    (output / "summary.json").write_bytes(encode(summary(groups)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker")
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--baseline")
    parser.add_argument("--candidate")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.worker:
        print(encode(worker(Path(args.worker).resolve(), args.capture)).decode())
    else:
        try:
            run(args)
        except Exception as exc:
            output = Path(args.output).resolve()
            if output.is_dir():
                failure = {"verdict": "INCONCLUSIVE", "error_type": type(exc).__name__,
                           "detail": str(exc), "no_resume": True}
                if isinstance(exc, (subprocess.CalledProcessError, subprocess.TimeoutExpired)):
                    failure["stdout"] = (exc.stdout or b"").decode("utf-8", "replace")
                    failure["stderr"] = (exc.stderr or b"").decode("utf-8", "replace")
                (output / "failure.json").write_bytes(encode(failure))
            raise
