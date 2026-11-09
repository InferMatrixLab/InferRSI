"""Emit a reproducible discovery inventory from local Git history, without fetching."""

import argparse
import json
import re
import subprocess
from pathlib import Path

TOPICS = {
    "deepseek-v4-dspark": (
        r"deepseek[ _-]?v?4|dsv4|deepseek_v4|dspark|indexcache|indexshare|hcpre"
    ),
    "communication": r"dsa.?cp|dsacp|flashcomm.?1|fused.?mc2",
    "priority-models": r"kimi[ _-]?k3|kimi_k3|minimax[ _-]?m3|minimax_m3|glm[ _-]?5",
    "fusion": r"fus(?:e|ed|ion)|gmm.?situ|swiglu.?quant|norm.?quant|qknorm.?rope",
}
PATCH_PATTERN = r"fused|fusion|fuse_|_fuse|npu_.*(norm.*quant|matmul.*(reduce|gather|swiglu))"


def git(repo, *args):
    return subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repo), *args], text=True
    )


def classify(message, paths, patch_hit):
    searchable = message + "\n" + "\n".join(paths)
    topics = [name for name, pattern in TOPICS.items()
              if re.search(pattern, searchable, re.IGNORECASE)]
    if patch_hit and "fusion" not in topics:
        topics.append("fusion")
    return topics


def inventory(repo, revision):
    if git(repo, "rev-parse", "--is-shallow-repository").strip() == "true":
        raise ValueError("Complete reachable history requires a non-shallow repository")
    pin = git(repo, "rev-parse", "--verify", f"{revision}^{{commit}}").strip()
    patch_hits = set(git(
        repo, "log", pin, "--format=%H", "--regexp-ignore-case", "-G", PATCH_PATTERN,
        "--", "vllm_ascend", "csrc",
    ).splitlines())
    raw = git(repo, "log", pin, "--format=%x1e%H%x1f%s%x1f%B%x1f", "--name-only")
    commits = []
    chunks = raw.split("\x1e")[1:]
    for chunk in chunks:
        sha, subject, message, paths_text = chunk.split("\x1f", 3)
        paths = paths_text.splitlines()
        paths = [path for path in paths if path]
        topics = classify(message, paths, sha in patch_hits)
        if topics:
            commits.append({
                "commit": sha, "subject": subject, "topics": topics,
                "runtime_patch_match": sha in patch_hits,
                "paths": paths,
            })
    return {
        "schema_version": 1,
        "repository": "https://github.com/vllm-project/vllm-ascend",
        "commit": pin,
        "reachable_commits": len(chunks),
        "candidate_commits": len(commits),
        "topic_counts": {name: sum(name in row["topics"] for row in commits) for name in TOPICS},
        "screening": {
            "messages_and_paths": TOPICS,
            "runtime_diff_pattern": PATCH_PATTERN,
            "runtime_diff_paths": ["vllm_ascend", "csrc"],
            "boundary": (
                "Keyword/path/diff candidates only; semantic review is recorded separately."
            ),
        },
        "commits": commits,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    print(json.dumps(inventory(args.repo, args.revision), indent=2))


if __name__ == "__main__":
    main()
