"""Read-only, CPU-only retrieval evidence runner; no model or hardware invocation.

Use --help. Baseline/candidate paths and frozen protocol are explicit inputs.
Each checkout runs its own evaluator against its published interfaces. Cross-version
comparisons retain unpaired measurements and compare only shared operations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def identity(root):
    groups = {}
    for name, paths in (
        ("python", [*sorted((root / "src").rglob("*.py")), root / "tools/evaluate_indexer.py"]),
        ("corpus", sorted((root / "src/inferrsi/knowledge/data").rglob("*"))
                    + sorted((root / "src/inferrsi/harness/data").rglob("*"))),
    ):
        members = {
            p.relative_to(root).as_posix(): digest(p.read_bytes())
            for p in paths if p.is_file() and "__pycache__" not in p.parts
        }
        groups[name] = {"sha256": digest(encode(members)), "files": len(members)}
    groups["revision"] = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    groups["environment"] = {
        "python": platform.python_version(), "system": platform.system(),
        "release": platform.release(), "machine": platform.machine(), "cpu_count": os.cpu_count(),
    }
    return groups


def child(root, action, payload):
    env = {"PATH": os.defpath, "PYTHONPATH": str(root / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    runner = root / "tools/evaluate_indexer.py"
    if not runner.is_file():
        raise ValueError("Use the retained frozen evaluator for a checkout without its own worker.")
    run = subprocess.run(
        [sys.executable, str(runner), "--worker", str(root), action],
        input=json.dumps(payload), text=True, capture_output=True, env=env, check=True, timeout=180,
    )
    return json.loads(run.stdout)


def cli(root, query, limit, scope):
    args = [sys.executable, "-m", "inferrsi", "find", query, "--no-external",
            "--limit", str(limit), "--json"]
    for name, value in scope.items():
        flag = "--repo-type" if name == "repo" else "--" + name
        args.extend((flag, ",".join(value) if name == "kinds" else value))
    start = time.perf_counter_ns()
    run = subprocess.run(args, capture_output=True, check=True, timeout=180, env={
        "PATH": os.defpath, "PYTHONPATH": str(root / "src"), "PYTHONDONTWRITEBYTECODE": "1",
    })
    elapsed = time.perf_counter_ns() - start
    start = time.perf_counter_ns()
    result = json.loads(run.stdout)
    decode = time.perf_counter_ns() - start
    return {"ns": elapsed, "decode_ns": decode, "bytes": len(run.stdout),
            "output_sha256": digest(encode(result))}


def find_options(case):
    query = case.get("query", "")
    if case.get("relevance") is not None:
        if query.strip():
            raise ValueError("Supply one Find question or use the pinned legacy runner.")
        query = case["relevance"]
    scope = dict(case.get("filters", {}))
    kind = scope.pop("kind", None)
    if kind:
        scope["kinds"] = ("record", "skill") if kind == "knowledge" else (kind,)
    return query, case.get("limit", 5), scope


def measure(call):
    start = time.perf_counter_ns()
    value = call()
    elapsed = time.perf_counter_ns() - start
    data = encode(value)
    return {"ns": elapsed, "bytes": len(data), "output_sha256": digest(data)}


def worker(root, action, payload):
    sys.path.insert(0, str(root / "src"))
    from inferrsi.knowledge.knowledge_find import find, installed_skill_root, load_corpus
    from inferrsi.knowledge.knowledge_operations import KnowledgeReader

    if action == "identity":
        return identity(root)
    if action == "bench":
        rows = {}
        for case in payload["queries"]:
            query, limit, scope = find_options(case)
            corpus = load_corpus(**scope)
            find(query, corpus, limit=limit)
            rows["hot_find/" + case["id"]] = measure(lambda: find(query, corpus, limit=limit))
        case = payload["queries"][0]
        query, limit, scope = find_options(case)
        rows["fresh_find"] = measure(lambda: find(query, load_corpus(**scope), limit=limit))
        hits = find(query, load_corpus(**scope), limit=limit, pin_material=True)
        if hits["items"]:
            hit = hits["items"][0]
            rows["pinned_read"] = measure(lambda: KnowledgeReader().read_hit(hit)[0])
        for name, probe in (("cli_find_relevance", case),
                            ("cli_find_search", {"query": "cgroupv2", "limit": 5})):
            query, limit, scope = find_options(probe)
            rows[name] = cli(root, query, limit, scope)
            result = find(query, load_corpus(**scope), limit=limit)
            if digest(encode(result)) != rows[name]["output_sha256"]:
                raise ValueError("Find API/CLI payload mismatch: " + name)
        return rows
    if action == "contracts":
        from inferrsi.knowledge._skill_selection import SkillIndexError, indexed_skill
        reader = KnowledgeReader()
        cgroup = "inferrsi.common.skills.cgroup_resource_controls"
        afd = "inferrsi.cuda.skills.audit_afd_p2p_exchanges"
        rows = []
        def check(name, passed, output):
            rows.append({"id": name, "passed": bool(passed), "output": output})
        result = find("floristry orchid", load_corpus())
        check("no_match", result["no_match"], result)
        result = find("P2pNccl", load_corpus(backend="ascend"))
        check("incompatible_filter", result["no_match"], result)
        result = reader.collect(ids=[cgroup], relevance="unrelated orchid")
        check("explicit_id_unrelated", [x["id"] for x in result["items"]] == [cgroup], result)
        small = reader.collect(ids=[afd], context_bytes=1)
        required = small["context_omissions"][0]["required_bytes"]
        exact = reader.collect(ids=[afd], context_bytes=required)
        check("exact_required_budget", bool(exact["contexts"]) and
              exact["context_bytes"] == required and not exact["context_omissions"], exact)
        short = reader.collect(ids=[afd], context_bytes=required - 1)
        check("undersized_required_budget", not short["contexts"] and
              short["context_omissions"][0]["reason"] == "context_limit", short)
        bundle = reader.read(cgroup)
        record = reader.records()[cgroup]
        core = record["skill_documents"]["original"]
        bundle.content[core] += b"\nchanged source"
        bundle.dependencies.clear()  # isolate projection validation from dependency validation
        view = {**bundle.view(), "authority": "package"}
        rejected = False
        try:
            indexed_skill(record, view, bundle.content)
        except SkillIndexError:
            rejected = True
        check("stale_source_projection", rejected, {"rejected": rejected})
        return rows
    if action == "cases":
        rows = []
        for case in payload:
            query, limit, scope = find_options(case)
            found = find(query, load_corpus(**scope), limit=limit, pin_material=True)
            reader = KnowledgeReader(skill_root=installed_skill_root())
            hits = [hit for hit in found["items"] if "revision" in hit]
            result = reader.pack_find_hits(hits, cue=query, limit=limit,
                                           context_bytes=case.get("context_bytes", 262144))
            ids = [hit["material_ref"].partition(":")[2] if "material_ref" in hit else hit["id"]
                   for hit in found["items"]]
            ranks = [ids.index(i) + 1 for i in case["relevant_ids"] if i in ids]
            selected = [i for i in case["relevant_ids"] if i in ids]
            complete = []
            for target in selected:
                context = next((c for c in result["contexts"]
                                if c["ref"] == "package:" + target), None)
                checks = []
                if context:
                    bundle = reader.read(context["ref"], revision=context["revision"])
                    # Read the exact revision once; verify every complete emitted resource.
                    for resource in context["resources"]:
                        data = bundle.content[resource["path"]]
                        if resource.get("locator") == "skill-procedure":
                            checks.append(digest(data) == resource["source_sha256"])
                            data = b"".join(data[start:end] for start, end
                                            in resource["source_byte_ranges"])
                        checks.append(data == resource["content"].encode()
                                      and digest(data) == resource["sha256"])
                    paths = [r["path"] for r in context["resources"]]
                    checks.extend(any(p.endswith(s) for p in paths)
                                  for s in case.get("required_resource_suffixes", []))
                    checks.append(bundle.revision == context["revision"])
                complete.append(bool(context) and all(checks))
            returned = {"find": found, "candidate_input": result}
            rows.append({"id": case["id"], "split": case["split"], "hit_at_5": bool(ranks),
                         "rr_at_5": 1 / min(ranks) if ranks else 0,
                         "retrieved_relevant": len(selected), "complete_relevant": sum(complete),
                         "forbidden_hits": sorted(set(ids) & set(case.get("forbidden_ids", []))),
                         "output_sha256": digest(encode(returned)), "result": returned})
        return rows
    raise ValueError(action)


def percentile(values, q):
    return sorted(values)[max(0, math.ceil(q * len(values)) - 1)]


def summarize(groups):
    first = groups[0]
    names = [name for name in first["A"] if name in first["B"]]
    rows = {}
    for name in names:
        arms = {arm: [g[arm][name]["ns"] / 1e6 for g in groups] for arm in ("A", "B")}
        rows[name] = {
            arm: {"n": len(v), "p50_ms": statistics.median(v), "p95_ms": percentile(v, .95)}
            for arm, v in arms.items()
        }
        for stat in ("p50_ms", "p95_ms"):
            rows[name][stat + "_change_percent"] = (
                100 * (rows[name]["B"][stat] / rows[name]["A"][stat] - 1))
        rows[name]["output_parity"] = all(
            g["A"][name]["output_sha256"] == g["B"][name]["output_sha256"] for g in groups)
    primary = [name for name in names if name.startswith(("hot_find/", "hot_relevance/"))]
    summary = {"paths": rows, "primary_reduction_percent": None, "primary_95ci": None}
    if primary:
        gains = [statistics.median(
            100 * (g["A"][name]["ns"] - g["B"][name]["ns"]) / g["A"][name]["ns"]
            for name in primary
        ) for g in groups]
        rng = random.Random(255)
        bootstrap = [statistics.median(rng.choices(gains, k=len(gains))) for _ in range(10000)]
        summary.update(primary_reduction_percent=statistics.median(gains),
                       primary_95ci=[percentile(bootstrap, .025), percentile(bootstrap, .975)])
    unpaired = {arm: sorted(first[arm].keys() - rows.keys()) for arm in ("A", "B")}
    if any(unpaired.values()):
        summary["unpaired_paths"] = unpaired
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("action", nargs="?")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--cases", type=Path, nargs="*")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.worker.resolve(), args.action, json.load(sys.stdin))))
        return
    if not all((args.baseline, args.candidate, args.protocol, args.output)):
        parser.error("baseline, candidate, protocol and output are required")
    protocol = json.loads(args.protocol.read_text())
    roots = {"A": args.baseline.resolve(), "B": args.candidate.resolve()}
    before = {a: child(p, "identity", {}) for a, p in roots.items()}
    if before["A"]["revision"] != protocol["baseline_revision"]:
        raise ValueError("baseline revision mismatch")
    if before["A"]["corpus"] != before["B"]["corpus"]:
        raise ValueError("corpus mismatch")
    result = {"protocol_sha256": digest(args.protocol.read_bytes()), "before": before,
              "groups": [], "verdict": "INCONCLUSIVE"}
    try:
        for index in range(protocol["measurement"]["groups"]):
            order = "AB" if index % 2 == 0 else "BA"
            group = {"index": index, "order": order}
            for arm in order:
                group[arm] = child(roots[arm], "bench", protocol)
            result["groups"].append(group)
            write(args.output / "timing.json", result)
            print(f"Completed group {index + 1}", flush=True)
        result["after"] = {a: child(p, "identity", {}) for a, p in roots.items()}
        if result["after"] != before:
            raise ValueError("source/corpus/environment changed during measurement")
        result["summary"] = summarize(result["groups"])
        summary = result["summary"]
        failed = []
        if (summary["primary_reduction_percent"] is not None and
                summary["primary_reduction_percent"] < protocol["primary"]["gain_min_percent"]):
            failed.append("primary practical gain")
        if summary["primary_95ci"] is not None and summary["primary_95ci"][0] <= 0:
            failed.append("primary confidence interval")
        for name, row in summary["paths"].items():
            primary = name.startswith(("hot_find/", "hot_relevance/"))
            p50_limit = (protocol["primary"]["each_query_p50_max_regression_percent"]
                         if primary else protocol["secondary_limits"][
                             "each_path_p50_max_regression_percent"])
            if row["p50_ms_change_percent"] > p50_limit:
                failed.append(name + " p50 regression")
            if not primary and row["p95_ms_change_percent"] > protocol["secondary_limits"][
                    "each_path_p95_max_regression_percent"]:
                failed.append(name + " p95 regression")
            if not row["output_parity"]:
                failed.append(name + " output mismatch")
        result["failed_gates"] = failed
        result["verdict"] = "FAIL" if failed else "PASS"
        result["verdict_scope"] = "Timing only; accuracy and contracts reported separately"
        if "unpaired_paths" in summary:
            if not failed:
                result["verdict"] = "INCONCLUSIVE"
            result["verdict_scope"] = (
                "The runtimes expose different measurement contracts. Shared operations have "
                "paired timings and output parity. Each arm retains all of its measurements."
            )
        contracts = {arm: child(root, "contracts", {}) for arm, root in roots.items()}
        write(args.output / "contracts.json", contracts)
        measured = result["groups"][0]
        same_api = (any(name.startswith("hot_find/") for name in measured["A"])
                    == any(name.startswith("hot_find/") for name in measured["B"]))
        result["contract_checks_by_arm"] = {
            arm: all(row["passed"] for row in checks) for arm, checks in contracts.items()
        }
        if not all(result["contract_checks_by_arm"].values()):
            result["contracts_pass"] = False
        else:
            result["contracts_pass"] = contracts["A"] == contracts["B"] if same_api else None
        if args.cases:
            cases = [c for path in args.cases for c in json.loads(path.read_text())["cases"]]
            outcomes = {arm: child(root, "cases", cases) for arm, root in roots.items()}
            for arm, rows in outcomes.items():
                write(args.output / (arm + "-cases.json"), rows)
            result["accuracy_output_parity"] = outcomes["A"] == outcomes["B"] if same_api else None
            result["cases_sha256"] = {path.name: digest(path.read_bytes()) for path in args.cases}
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["verdict"] = "INCONCLUSIVE"
        raise
    finally:
        write(args.output / "timing.json", result)


if __name__ == "__main__":
    main()
