"""Issue #190's frozen, standard-library-only retrieval evaluation packet."""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import importlib
import json
import os
import platform
import pstats
import random
import statistics
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PACKET = Path(__file__).resolve().parents[1]
PROTOCOL = PACKET / "plan/protocol.json"
FREEZE_FILES = (
    "plan/protocol.json", "plan/README.md", "validator/development.json",
    "validator/withheld.json", "validator/evaluate.py", "validator/README.md",
    "plan/amendment-1.md", "plan/freeze-v1.json",
)
MODES = ("search", "relevance", "context_material", "default_diagnostic")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def indexed_rows(rows, expected):
    counts = Counter((r.get("mode"), r.get("case")) for r in rows)
    errors = {"missing": sorted(expected - counts.keys(), key=repr),
              "unexpected": sorted(counts.keys() - expected, key=repr),
              "duplicates": sorted((key for key, n in counts.items() if n != 1), key=repr)}
    return {(r.get("mode"), r.get("case")): r for r in rows}, {k: v for k, v in errors.items() if v}


def compare_quality(left, right, selected):
    expected = {(mode, case["id"]) for case in selected for mode in MODES}
    a, a_errors = indexed_rows(left, expected)
    b, b_errors = indexed_rows(right, expected)
    errors = {side: error for side, error in (("A", a_errors), ("B", b_errors)) if error}
    failures = [{"mode": mode, "case": case} for mode, case in sorted(expected)
                if (mode, case) in a and (mode, case) in b and a[mode, case] != b[mode, case]]
    return errors, failures


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")


def stamp():
    return datetime.now(timezone.utc).isoformat()


def freeze(make=False, dry=False):
    hashes = {p: sha((PACKET / p).read_bytes()) for p in FREEZE_FILES}
    path = PACKET / "plan/freeze.json"
    if make:
        if path.exists():
            raise ValueError("freeze_exists: never replace an existing freeze silently")
        value = {"schema_version": 1, "revision": 2,
                 "supersedes_content_sha256": read(PACKET / "plan/freeze-v1.json")["content_sha256"],
                 "frozen_at_utc": stamp(), "files": hashes,
                 "content_sha256": sha(canonical(hashes))}
        write(path, value)
        return value
    if not path.exists() and dry:
        return {"state": "unfrozen_dry_run", "content_sha256": sha(canonical(hashes))}
    value = read(path)
    if value["files"] != hashes or value["content_sha256"] != sha(canonical(hashes)):
        raise ValueError("freeze_mismatch: stop before importing or timing a candidate")
    return value


def cases(split="development", limit=None):
    result = read(PACKET / "validator/development.json")["cases"]
    if split == "all":
        result += read(PACKET / "validator/withheld.json")["cases"]
    return result[:limit] if limit is not None else result


def inventory(root, paths):
    files = {p.relative_to(root).as_posix(): {"sha256": sha(p.read_bytes()),
                                           "bytes": p.stat().st_size}
             for p in sorted(set(paths)) if p.is_file()
             and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    return {"files": files, "sha256": sha(canonical(files)), "file_count": len(files),
            "bytes": sum(v["bytes"] for v in files.values())}


def git(root, *args):
    run = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True)
    return run.stdout.decode("utf-8").strip()


def source_identity(root):
    data = root / "src/inferrsi/data"
    source = inventory(root, (root / "src/inferrsi").rglob("*.py"))
    corpus = inventory(root, [*(data / "repo_packs").rglob("*.json"),
                              *(data / "knowledge_packs").rglob("*"),
                              *(data / "skill_library").rglob("*")])
    library = inventory(root, (data / "skill_library").rglob("*"))
    records = [p for p in (data / "repo_packs").rglob("*.json") if "knowledge" in p.parts]
    records += list((data / "knowledge_packs").rglob("*.json"))
    record_values = [read(p) for p in records]
    return {"git_head": git(root, "rev-parse", "HEAD"),
            "tracked_source_dirty": bool(git(root, "status", "--porcelain",
                                              "--untracked-files=no", "--", "src/inferrsi")),
            "python_sources": source, "corpus": corpus,
            "library": {k: v for k, v in library.items() if k != "files"},
            "knowledge_record_count": len(record_values),
            "packaged_skill_count": sum(r.get("index_type") == "packaged-skill"
                                        for r in record_values)}


def fixture_check(root, selected):
    data = root / "src/inferrsi/data"
    paths = [p for p in (data / "repo_packs").rglob("*.json") if "knowledge" in p.parts]
    paths += list((data / "knowledge_packs").rglob("*.json"))
    records = {r["id"]: r for p in paths if "id" in (r := read(p))}
    require(len({c["id"] for c in selected}) == len(selected), "duplicate_fixture_case")
    for case in selected:
        require(case["cue"].strip() and case["category"], "invalid_fixture_case: " + case["id"])
        if not case["relevant"]:
            require(case["no_answer_rationale"], "missing_negative_rationale: " + case["id"])
        for label in case["relevant"]:
            path = (root / label["source"]).resolve()
            require(path.is_relative_to(root) and path.is_file(), "invalid_label_source: " + case["id"])
            require(label["support"] in path.read_text(encoding="utf-8"), "label_support_absent: " + case["id"])
            record = records[label["id"]]
            require(label["source"] in record["source_files"], "unbound_label_source: " + case["id"])
            require(label["rationale"] and record["repo"] == "inferrsi", "invalid_label_scope: " + case["id"])
            require(case["backend"] is None or record["backend"] in (case["backend"], "common"), "invalid_label_backend: " + case["id"])
    return {"cases": len(selected), "answerable": sum(bool(c["relevant"]) for c in selected),
            "negative": sum(not c["relevant"] for c in selected),
            "fixture_sha256": sha(canonical(selected))}


def load_source(root):
    sys.path.insert(0, str(root / "src"))
    modules = {}
    for name in ("inferrsi", "inferrsi.catalog", "inferrsi.knowledge_operations", "inferrsi.cli"):
        module = importlib.import_module(name)
        path = Path(module.__file__).resolve()
        if not path.is_relative_to(root / "src/inferrsi"):
            raise ValueError("module_origin_mismatch: " + name)
        modules[name] = {"source": path.relative_to(root).as_posix(),
                         "sha256": sha(path.read_bytes())}
    return modules


def environment():
    clock = time.get_clock_info("perf_counter")
    return {"python_version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "python_executable_sha256": sha(Path(sys.executable).read_bytes()),
            "system": platform.system(), "release": platform.release(),
            "machine": platform.machine(), "logical_cpu_count": os.cpu_count(),
            "perf_counter_resolution_seconds": clock.resolution,
            "site_initializers_disabled": bool(sys.flags.no_site),
            "python_optimization": sys.flags.optimize,
            "filesystem_cache": "not controlled; process cold is not OS-cache cold"}


def invoke(mode, case, reader=None):
    from inferrsi.catalog import search_knowledge
    from inferrsi.knowledge_operations import KnowledgeReader
    common = {"repo": "inferrsi", "backend": case["backend"], "limit": 5}
    if mode == "search":
        return search_knowledge(case["cue"], **common)
    reader = reader if reader is not None else KnowledgeReader()
    if mode == "default_diagnostic":
        return reader.collect(case["cue"], **common)
    options = {"material": True, "max_bytes": 1048576, "context_bytes": 65536} if mode == "context_material" else {}
    return reader.collect("", relevance=case["cue"], **common, **options)


def snapshot(value, compact=False):
    encoded = canonical(value)
    result = {"sha256": sha(encoded), "serialized_bytes": len(encoded)}
    if compact:
        return result
    items = value if isinstance(value, list) else value["items"]
    result["ordered_items"] = [
        {"id": item["id"], **{k: item[k] for k in ("ref", "revision") if k in item},
         **({"resource_count": len(item["resources"]),
             "resource_hashes_sha256": sha(canonical(item["resources"])),
             "dependencies_sha256": sha(canonical(item["dependencies"]))}
            if "resources" in item else {})} for item in items]
    if isinstance(value, dict):
        for key in ("no_match", "omissions", "collisions", "material_bytes", "selection",
                    "context_omissions", "context_bytes", "context_budget"):
            if key in value:
                result[key] = value[key]
        if "contexts" in value:
            result["contexts"] = [
                {k: v for k, v in context.items() if k != "resources"}
                | {"resources": [{k: v for k, v in resource.items() if k != "content"}
                                  for resource in context["resources"]]}
                for context in value["contexts"]]
    return result


def worker(root, request):
    modules = load_source(root)
    if "expected_source_sha256" in request:
        actual = inventory(root, (root / "src/inferrsi").rglob("*.py"))["sha256"]
        if actual != request["expected_source_sha256"]:
            raise ValueError("worker_source_digest_changed_before_measurement")
    from inferrsi.knowledge_operations import KnowledgeReader
    action = request["action"]
    if action == "identity":
        return {"modules": modules, "environment": environment(), **source_identity(root)}
    selected = request["cases"]
    if action in ("quality", "trace"):
        outputs = []
        for case in selected:
            for mode in MODES:
                value = invoke(mode, case)
                ids = [v["id"] for v in (value if isinstance(value, list) else value["items"])]
                ranks = [i + 1 for i, identity in enumerate(ids[:5])
                         if identity in {label["id"] for label in case["relevant"]}]
                outputs.append({"case": case["id"], "mode": mode,
                                "answerable": bool(case["relevant"]),
                                "success_at_5": int(bool(ranks)),
                                "reciprocal_rank_at_5": 1 / ranks[0] if ranks else 0,
                                "output": snapshot(value)})
        return {"modules": modules, "outputs": outputs}
    if action == "profile":
        profiler = cProfile.Profile()
        profiler.enable()
        invoke("relevance", selected[0])
        profiler.disable()
        rows = []
        for (filename, line, name), (primitive, calls, total, cumulative, _) in pstats.Stats(profiler).stats.items():
            path = Path(filename)
            label = path.relative_to(root).as_posix() if path.is_relative_to(root) else "<external>/" + path.name
            rows.append({"source": label, "line": line, "function": name,
                         "primitive_calls": primitive, "calls": calls,
                         "total_seconds": total, "cumulative_seconds": cumulative})
        return {"modules": modules, "case": selected[0]["id"],
                "mode": "fresh-reader relevance, cProfile diagnostic only",
                "profile": sorted(rows, key=lambda r: -r["cumulative_seconds"])[:80]}
    reader = KnowledgeReader()
    warmups = [("relevance", case) for case in selected]
    warmups += [("default_diagnostic", selected[1]), ("context_material", selected[2])]
    for mode, case in warmups:
        invoke(mode, case, reader)
    cache = {"records_populated": reader._records is not None, "library_populated": reader._library is not None}
    require(all(cache.values()), "warmup_cache_not_populated")
    measurements = []
    workloads = [(mode, case) for case in selected for mode in ("hot_relevance", "cold_relevance", "search")]
    workloads += [(mode, selected[index]) for index, modes in
                  ((1, ("hot_default_diagnostic", "cold_default_diagnostic")),
                   (2, ("hot_context_material", "cold_context_material"))) for mode in modes]
    for mode, case in workloads:
        operation = mode.removeprefix("hot_").removeprefix("cold_")
        start = time.perf_counter_ns()
        value = invoke(operation, case, reader if mode.startswith("hot_") else None)
        elapsed = time.perf_counter_ns() - start
        measurements.append({"mode": mode, "case": case["id"], "ns": elapsed,
                             "output": snapshot(value, compact=True)})
    return {"modules": modules, "warmup_cache_state": cache, "api": measurements}


def child(python, root, request):
    env = {**os.environ, "PYTHONPATH": str(root / "src"), "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONIOENCODING": "utf-8", "PYTHONOPTIMIZE": "0"}
    run = subprocess.run([python, "-S", str(Path(__file__).resolve()), "_worker", "--source", str(root)],
                         input=canonical(request), capture_output=True, env=env, cwd=PACKET)
    if run.returncode:
        raise ValueError("isolated_worker_failed: " + run.stderr.decode("utf-8", "replace")[-400:].replace(str(root), "<source>"))
    return json.loads(run.stdout)


def cli(python, root, mode, case, expected_source):
    if inventory(root, (root / "src/inferrsi").rglob("*.py"))["sha256"] != expected_source:
        raise ValueError("CLI_source_digest_changed_before_measurement")
    args = ["knowledge", "search", case["cue"], "--repo-type", "inferrsi"] if mode == "search" else ["collect"]
    if mode == "default_diagnostic":
        args += [case["cue"]]
    elif mode != "search":
        args += ["--relevance", case["cue"]]
    if mode == "context_material":
        args += ["--material", "--max-bytes", "1048576", "--context-bytes", "65536"]
    args += ["--limit", "5", "--json"]
    env = {**os.environ, "PYTHONPATH": str(root / "src"), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8", "PYTHONOPTIMIZE": "0"}
    start = time.perf_counter_ns()
    run = subprocess.run([python, "-S", "-m", "inferrsi", *args], capture_output=True, env=env, cwd=PACKET)
    elapsed = time.perf_counter_ns() - start
    if run.returncode:
        raise ValueError("CLI_invocation_failed: mode=" + mode)
    start = time.perf_counter_ns()
    value = json.loads(run.stdout.decode("utf-8"))
    decode_ns = time.perf_counter_ns() - start
    return {"mode": mode, "case": case["id"], "process_ns": elapsed, "decode_ns": decode_ns,
            "scope": "repo=inferrsi" if mode == "search" else "unfiltered packaged CLI diagnostic",
            "stdout_sha256": sha(run.stdout), "stdout_bytes": len(run.stdout),
            "output": snapshot(value, compact=True)}


def percentile(values, p):
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    low = int(position)
    return ordered[low] + (ordered[min(low + 1, len(ordered) - 1)] - ordered[low]) * (position - low)


def bootstrap(reductions, protocol):
    rule = protocol["performance"]["bootstrap"]
    rng = random.Random(rule["seed"])
    draws = [statistics.median(rng.choices(reductions, k=len(reductions))) for _ in range(rule["iterations"])]
    return {"paired_median_reduction": statistics.median(reductions),
            "confidence_95": [percentile(draws, p) for p in rule["quantiles"]],
            "paired_reductions": reductions, "bootstrap": rule}


def quality_summary(rows):
    result = {}
    for split in ("development", "withheld", "all"):
        subset = [r for r in rows if split == "all" or r["case"].startswith("dev" if split == "development" else "withheld")]
        for mode in MODES:
            positive = [r for r in subset if r["mode"] == mode and r["answerable"]]
            negative = [r for r in subset if r["mode"] == mode and not r["answerable"]]
            if not positive and not negative:
                continue
            result[split + "/" + mode] = {
                "answerable_count": len(positive),
                "success_at_5": statistics.mean(r["success_at_5"] for r in positive) if positive else None,
                "mrr_at_5": statistics.mean(r["reciprocal_rank_at_5"] for r in positive) if positive else None,
                "negative_count": len(negative),
                "negative_empty_count": sum(not r["output"]["ordered_items"] for r in negative)}
    return result


def preflight(args, protocol, frozen):
    roots = {"A": Path(args.baseline).resolve(), "B": Path(args.candidate).resolve()}
    identities = {side: child(args.python, root, {"action": "identity"}) for side, root in roots.items()}
    if identities["A"]["git_head"] != protocol["baseline_sha"]:
        raise ValueError("baseline_revision_mismatch")
    if identities["B"]["git_head"] != args.candidate_sha:
        raise ValueError("candidate_revision_mismatch")
    if identities["B"]["python_sources"]["sha256"] != args.candidate_source_sha:
        raise ValueError("candidate_source_digest_mismatch")
    if any(v["tracked_source_dirty"] for v in identities.values()):
        raise ValueError("tracked_source_dirty")
    if identities["A"]["corpus"]["sha256"] != identities["B"]["corpus"]["sha256"]:
        raise ValueError("corpus_mismatch")
    if identities["A"]["environment"] != identities["B"]["environment"]:
        raise ValueError("interpreter_or_environment_mismatch")
    return roots, {"started_at_utc": stamp(), "dry_run": args.dry_run,
                   "entry_python_optimization": sys.flags.optimize,
                   "verdict": "INCONCLUSIVE", "freeze_content_sha256": frozen["content_sha256"],
                   "identities": identities}


def benchmark_summary(pairs, protocol, expected_pairs=None):
    expected_pairs = protocol["performance"]["pairs"] if expected_pairs is None else expected_pairs
    hot = protocol["performance"]["hot_cases"]
    api_keys = {(mode, case) for case in hot for mode in ("hot_relevance", "cold_relevance", "search")}
    api_keys |= {(mode, hot[index]) for index, modes in
                 ((1, ("hot_default_diagnostic", "cold_default_diagnostic")),
                  (2, ("hot_context_material", "cold_context_material"))) for mode in modes}
    cli_keys = {(mode, hot[2] if mode == "context_material" else hot[1]) for mode in MODES}
    errors = []
    ids = [pair.get("pair") for pair in pairs]
    if any(type(i) is not int for i in ids) or Counter(ids) != Counter(range(expected_pairs)):
        errors.append({"pair_ids": ids, "expected_pair_ids": list(range(expected_pairs))})
    for pair in pairs:
        index = pair.get("pair")
        if type(index) is not int or pair.get("order") != ("AB" if index % 2 == 0 else "BA"):
            errors.append({"pair": index, "invalid_order": pair.get("order")})
        for side in ("A", "B"):
            for family, keys in (("api", api_keys), ("cli", cli_keys)):
                _, error = indexed_rows(pair.get(side, {}).get(family, []), keys)
                if error:
                    errors.append({"pair": index, "side": side, "family": family, **error})
    if errors:
        return {"measurement_structure_errors": errors, "primary": None,
                "performance_gate_passed": False, "output_parity_assessed": False,
                "output_parity_failures": [], "latency_ns": {}}
    grouped = {}
    reductions = []
    parity_failures = []
    for pair in pairs:
        for side in ("A", "B"):
            for row in pair[side]["api"]:
                grouped.setdefault("api/" + row["mode"] + "/" + row["case"] + "/" + side, []).append(row["ns"])
            for row in pair[side]["cli"]:
                for metric in ("process_ns", "decode_ns"):
                    grouped.setdefault("cli/" + row["mode"] + "/" + row["case"] + "/" + metric + "/" + side, []).append(row[metric])
        medians = {side: statistics.median(r["ns"] for r in pair[side]["api"] if r["mode"] == "hot_relevance") for side in ("A", "B")}
        reductions.append(1 - medians["B"] / medians["A"])
        for family in ("api", "cli"):
            keys = api_keys if family == "api" else cli_keys
            left_rows, _ = indexed_rows(pair["A"][family], keys)
            right_rows, _ = indexed_rows(pair["B"][family], keys)
            for key in sorted(keys):
                left, right = left_rows[key], right_rows[key]
                if left["output"] != right["output"] or (family == "cli" and left["stdout_sha256"] != right["stdout_sha256"]):
                    parity_failures.append({"pair": pair["pair"], "family": family, "mode": left["mode"], "case": left["case"]})
    estimate = bootstrap(reductions, protocol)
    gate = protocol["performance"]["gate"]
    passed = (estimate["paired_median_reduction"] >= gate["minimum_paired_median_reduction"]
              and estimate["confidence_95"][0] > gate["lower_95_percent_bound_must_exceed"])
    return {"primary": estimate, "performance_gate_passed": passed,
            "measurement_structure_errors": [], "output_parity_assessed": True,
            "output_parity_failures": parity_failures,
            "latency_ns": {key: {"n": len(values), "p50": percentile(values, .5), "p95": percentile(values, .95)}
                           for key, values in sorted(grouped.items())}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "check-freeze", "validate", "identity", "profile", "trace", "quality", "bench", "selfcheck", "_worker"))
    parser.add_argument("--source")
    parser.add_argument("--baseline")
    parser.add_argument("--candidate")
    parser.add_argument("--candidate-sha")
    parser.add_argument("--candidate-source-sha")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--output")
    parser.add_argument("--split", choices=("development", "all"), default="development")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--case-limit", type=int)
    parser.add_argument("--pairs", type=int)
    args = parser.parse_args()
    if args.action == "_worker":
        print(canonical(worker(Path(args.source).resolve(), json.load(sys.stdin))).decode("utf-8"))
        return
    protocol = read(PROTOCOL)
    if args.action == "freeze":
        value = freeze(make=True)
    elif args.action == "selfcheck":
        require(percentile([1, 3], .95) == 2.9, "percentile_selfcheck")
        require(bootstrap([.3] * 20, protocol)["confidence_95"] == [.3, .3], "bootstrap_selfcheck")
        require(snapshot({"items": [], "no_match": True})["ordered_items"] == [], "snapshot_selfcheck")
        selected = [{"id": f"synthetic{i:02}"} for i in range(24)]
        quality = [{"case": c["id"], "mode": mode} for c in selected for mode in MODES]
        require(compare_quality(quality, quality[:-1], selected)[0], "missing_quality_row_accepted")
        require(compare_quality(quality, quality + [quality[0]], selected)[0], "duplicate_quality_row_accepted")
        hot = protocol["performance"]["hot_cases"]
        api = [{"mode": mode, "case": case, "ns": 100, "output": {}} for case in hot for mode in ("hot_relevance", "cold_relevance", "search")]
        api += [{"mode": mode, "case": hot[index], "ns": 100, "output": {}} for index, modes in ((1, ("hot_default_diagnostic", "cold_default_diagnostic")), (2, ("hot_context_material", "cold_context_material"))) for mode in modes]
        cli_rows = [{"mode": mode, "case": hot[2] if mode == "context_material" else hot[1], "process_ns": 100, "decode_ns": 10, "output": {}, "stdout_sha256": "synthetic"} for mode in MODES]
        pairs = [{"pair": i, "order": "AB" if i % 2 == 0 else "BA", "A": {"api": api, "cli": cli_rows}, "B": {"api": [{**r, "ns": 50} for r in api], "cli": cli_rows}} for i in range(20)]
        require(benchmark_summary(pairs, protocol)["performance_gate_passed"], "complete_synthetic_pairs_rejected")
        for pair in pairs:
            pair["B"] = {"api": api[:-1], "cli": []}
        require(benchmark_summary(pairs, protocol)["measurement_structure_errors"], "missing_benchmark_rows_accepted")
        pairs[0]["pair"] = 1
        require(benchmark_summary(pairs, protocol)["measurement_structure_errors"], "duplicate_pair_accepted")
        value = {"selfcheck": "passed", "entry_python_optimization": sys.flags.optimize}
    else:
        frozen = freeze(dry=args.dry_run)
        if not args.dry_run and (args.case_limit is not None or args.pairs not in (None, protocol["performance"]["pairs"])):
            raise ValueError("formal_sample_count_change_requires_new_protocol_freeze")
        if args.dry_run and args.split == "all":
            raise ValueError("dry_run_must_not_open_withheld")
        if args.action == "check-freeze":
            value = frozen
        elif args.action == "identity":
            value = child(args.python, Path(args.source).resolve(), {"action": "identity"})
        elif args.action in ("validate", "profile", "trace"):
            if args.split == "all":
                raise ValueError("withheld_requires_quality_preflight_and_candidate_freeze")
            selected = cases(limit=args.case_limit)
            value = fixture_check(Path(args.source).resolve(), selected)
            if args.action != "validate":
                cue = next(c for c in selected if c["id"] == ("dev05" if args.action == "profile" else "dev09"))
                value = child(args.python, Path(args.source).resolve(), {"action": args.action, "cases": [cue]})
        else:
            if not all((args.baseline, args.candidate, args.candidate_sha, args.candidate_source_sha)):
                raise ValueError("explicit_baseline_candidate_revision_and_source_digest_required")
            roots, value = preflight(args, protocol, frozen)
            if args.action == "quality":
                selected = cases(args.split, args.case_limit)
                value["fixture"] = fixture_check(roots["A"], selected)
                value["variants"] = {side: child(args.python, root, {"action": "quality", "cases": selected, "expected_source_sha256": value["identities"][side]["python_sources"]["sha256"]}) for side, root in roots.items()}
                value["metrics"] = {side: quality_summary(v["outputs"]) for side, v in value["variants"].items()}
                left, right = (value["variants"][side]["outputs"] for side in ("A", "B"))
                value["measurement_structure_errors"], value["parity_failures"] = compare_quality(left, right, selected)
                value["verdict"] = "INCONCLUSIVE" if value["measurement_structure_errors"] else "FAIL" if value["parity_failures"] else "PASS" if args.split == "all" and not args.dry_run else "INCONCLUSIVE"
            else:
                if not args.output:
                    raise ValueError("bench_requires_output_for_incremental_raw_sample_retention")
                selected = [c for c in cases() if c["id"] in protocol["performance"]["hot_cases"]]
                value["pairs"] = []
                start = time.perf_counter_ns()
                for index in range(args.pairs or protocol["performance"]["pairs"]):
                    pair = {"pair": index, "order": "AB" if index % 2 == 0 else "BA"}
                    value["pairs"].append(pair)
                    for side in pair["order"]:
                        source_sha = value["identities"][side]["python_sources"]["sha256"]
                        pair[side] = child(args.python, roots[side], {"action": "bench", "cases": selected, "expected_source_sha256": source_sha})
                        pair[side]["cli"] = [cli(args.python, roots[side], mode, selected[2] if mode == "context_material" else selected[1], source_sha) for mode in ("search", "default_diagnostic", "relevance", "context_material")]
                        value["elapsed_ns"] = time.perf_counter_ns() - start
                        write(args.output, value)
                    print("completed paired group " + str(index + 1), file=sys.stderr, flush=True)
                value["summary"] = benchmark_summary(value["pairs"], protocol, args.pairs or protocol["performance"]["pairs"])
                sufficient = len(value["pairs"]) == protocol["performance"]["pairs"] and not args.dry_run
                value["verdict"] = "INCONCLUSIVE" if not sufficient or value["summary"]["measurement_structure_errors"] else "PASS" if value["summary"]["performance_gate_passed"] and not value["summary"]["output_parity_failures"] else "FAIL"
            value["source_and_corpus_unchanged_at_end"] = {}
            for side, root in roots.items():
                final = child(args.python, root, {"action": "identity"})
                same = all(final[key]["sha256"] == value["identities"][side][key]["sha256"] for key in ("python_sources", "corpus"))
                value["source_and_corpus_unchanged_at_end"][side] = same
                if not same:
                    value["verdict"] = "INCONCLUSIVE"
            value["completed_at_utc"] = stamp()
    if args.output:
        write(args.output, value)
    # Keep stdout free of fixture text, personal paths and full corpus inventories.
    print(json.dumps({k: value[k] for k in ("verdict", "dry_run", "cases", "answerable", "negative", "content_sha256", "selfcheck") if k in value}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, AssertionError, OSError, subprocess.SubprocessError) as exc:
        # Paths supplied by the operator stay local; do not leak full tracebacks.
        print("evaluation stopped: " + type(exc).__name__ + ": " + str(exc).replace(str(PACKET), "<packet>"), file=sys.stderr)
        raise SystemExit(2)
