"""Compare Find quality and fresh-process CLI time on two clean, pinned worktrees.

Run with --base DIR --candidate DIR --candidate-sha FULL_SHA --output OUTSIDE.json.
Each process uses the same Python executable and only its arm's src on PYTHONPATH.
The seven CLI workloads warm the filesystem, not a resident Python process.
"""

import argparse
import json
import math
import os
import platform
import random
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "find"


def validate_worktree(root, sha):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root).decode().strip()

    if Path(git("rev-parse", "--show-toplevel")).resolve() != root:
        raise ValueError("Expected a worktree root")
    if git("rev-parse", "HEAD") != sha:
        raise ValueError(f"Worktree revision differs from {sha}")
    if git("status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none"):
        raise ValueError(f"Dirty worktree at {sha}")


def workload(protocol):
    labels = json.loads((FIXTURES / "labelled-queries.json").read_bytes())
    queries = [(q["query"], q["expect"]) for group in labels for q in group["queries"]]
    queries.extend((query, None) for query in protocol["previous_fixed_queries"])
    queries.extend((query, None) for query in protocol["tasks"].values())
    return queries


def signature(result):
    return [[item["kind"], item["id"], bool(item.get("read_args"))] for item in result["items"]]


def inspect_arm():
    # Invoked in a separate interpreter rooted in the selected checkout.
    from inferrsi.knowledge import knowledge_find

    if not Path(knowledge_find.__file__).resolve().is_relative_to(Path.cwd() / "src"):
        raise ValueError("Find did not import from the pinned worktree")
    corpus = knowledge_find.load_corpus()
    queries = json.load(sys.stdin)
    print(json.dumps([signature(knowledge_find.find(q, corpus, limit=5)) for q in queries]))


def ratios(timings):
    base, candidate = zip(*timings)
    return statistics.median(candidate) / statistics.median(base)


def summarize_time(samples):
    timings = [pair for pairs in samples.values() for pair in pairs]
    # Keep the task mix fixed. Resample adjacent AB/BA blocks within each task.
    rng = random.Random(516)
    bootstrap = []
    for _ in range(2000):
        drawn = []
        for pairs in samples.values():
            blocks = [pairs[i : i + 2] for i in range(0, len(pairs), 2)]
            for block in rng.choices(blocks, k=len(blocks)):
                drawn.extend(block)
        bootstrap.append(ratios(drawn))
    bootstrap.sort()
    arms = {}
    for col, name in enumerate(("base", "candidate")):
        times = sorted(pair[col] for pair in timings)
        arms[name] = {
            "median_s": statistics.median(times),
            "p95_s": times[math.ceil(0.95 * len(times)) - 1],
        }
    return {
        "arms": arms,
        "pooled_median_ratio": ratios(timings),
        "paired_block_bootstrap_95pct": [bootstrap[49], bootstrap[1949]],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads((FIXTURES / "layout-queries.json").read_bytes())
    roots = {"base": args.base.resolve(), "candidate": args.candidate.resolve()}
    revisions = {"base": protocol["base_sha"], "candidate": args.candidate_sha}
    output = args.output.resolve()
    for arm, root in roots.items():
        if output.is_relative_to(root):
            parser.error("Write the report outside both measured worktrees")
        validate_worktree(root, revisions[arm])
    envs = {
        arm: dict(
            os.environ,
            PYTHONPATH=str(root / "src"),
            PYTHONUTF8="1",
            PYTHONDONTWRITEBYTECODE="1",
            PYTHONNOUSERSITE="1",
            PYTHONHASHSEED="0",
        )
        for arm, root in roots.items()
    }
    queries = workload(protocol)

    def rank_arm(arm):
        return json.loads(
            subprocess.check_output(
                [sys.executable, str(Path(__file__).resolve()), "--inspect"],
                cwd=roots[arm],
                env=envs[arm],
                input=json.dumps([q for q, _ in queries]).encode(),
            )
        )

    # Rank only; these runs produce no timing samples. CLI measurements run serially below.
    with ThreadPoolExecutor(max_workers=2) as pool:
        ranks = dict(zip(roots, pool.map(rank_arm, roots), strict=True))
    details = [
        {"query": q, "expected_kind": kind, "base": old, "candidate": new}
        for (q, kind), old, new in zip(queries, ranks["base"], ranks["candidate"], strict=True)
    ]
    matched = sum(
        [item[:2] for item in row["base"]] == [item[:2] for item in row["candidate"]]
        for row in details
    )
    lost_reads = 0
    for row in details:
        readable = {(kind, key) for kind, key, has_read in row["candidate"] if has_read}
        lost_reads += sum(
            has_read and (kind, key) not in readable for kind, key, has_read in row["base"]
        )
    quality = {
        "matching_ordered_top5": matched,
        "queries": len(queries),
        "lost_readable_hits": lost_reads,
    }
    for arm in roots:
        positive = [row for row in details if row["expected_kind"] not in (None, "none")]
        gaps = [row for row in details if row["expected_kind"] == "none"]
        quality[arm] = {
            "hit_at_3_by_expected_kind": sum(
                any(item[0] == row["expected_kind"] for item in row[arm][:3]) for row in positive
            ),
            "labelled_positive": len(positive),
            "empty_results_on_labelled_gap": sum(not row[arm] for row in gaps),
            "labelled_gap": len(gaps),
        }

    def cli(arm, query):
        start = time.perf_counter()
        raw = subprocess.check_output(
            [
                sys.executable,
                "-m",
                "inferrsi",
                "find",
                query,
                "--limit",
                "5",
                "--no-external",
                "--json",
            ],
            cwd=roots[arm],
            env=envs[arm],
        )
        elapsed = time.perf_counter() - start
        return signature(json.loads(raw)), elapsed

    print(json.dumps(quality), file=sys.stderr, flush=True)
    for arm in roots:
        cli(arm, "warmup inference benchmark")
    tasks = protocol["tasks"]
    samples = {task: [] for task in tasks}
    for repeat in range(protocol["pairs_per_task"]):
        for i, (task, query) in enumerate(tasks.items()):
            order = ("base", "candidate") if (repeat + i) % 2 == 0 else ("candidate", "base")
            times = {}
            for arm in order:
                ids, times[arm] = cli(arm, query)
                if ids != ranks[arm][queries.index((query, None))]:
                    raise ValueError(f"Unstable CLI results for {task} ({arm})")
            samples[task].append([times["base"], times["candidate"]])
        print(f"Timed repeat {repeat + 1} complete", file=sys.stderr, flush=True)
    for arm, root in roots.items():
        validate_worktree(root, revisions[arm])
    latency = summarize_time(samples)
    gate = protocol["gate"]
    passed = (
        matched == len(queries)
        and lost_reads <= gate["max_lost_readable_hits"]
        and latency["pooled_median_ratio"] <= gate["max_candidate_to_base_median_cli_latency_ratio"]
    )
    report = {
        "revisions": revisions,
        "platform": platform.system(),
        "python": platform.python_version(),
        "gate": gate,
        "passed": passed,
        "quality": quality,
        "latency": latency,
        "samples_s_base_candidate": samples,
        "rankings": details,
    }
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("passed", "quality", "latency")}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["--inspect"]:
        inspect_arm()
    else:
        sys.exit(main())
