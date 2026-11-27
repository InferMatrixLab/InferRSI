"""Explicit bounded-provider Skill comparator for the speculative-search Python API.

This checkout tool composes the existing comparison authority. It never selects
a model/client implicitly, and does not turn fixed-output fixtures into live runs.
"""

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

from inferrsi.harness.executor import candidates, runtime_environment
from inferrsi.harness.executor.trials.external import execute_trial
from inferrsi.harness.records.artifact_primitives import digest, sha256
from inferrsi.harness.records.atomic_json import atomic_write_json
from inferrsi.knowledge.knowledge_operations import KnowledgeReader
from tools import skill_eval_compare as compare
from tools.skill_eval_improve import materialize

TASK_SCOPE = "skill-tasks-v1:"
LEGACY_SCOPE = "skill-data:"


def _canonical_value(value):
    # JSON numbers written as 1, 1.0 or 1e0 represent the same case input.
    if isinstance(value, dict):
        return {k: _canonical_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_canonical_value(v) for v in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _members(cases):
    if not isinstance(cases, list) or not cases:
        raise ValueError("Skill task set requires a nonempty case list")
    ids, inputs = set(), set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"]:
            raise ValueError("Skill task set requires a case ID")
        if case["id"] in ids:
            raise ValueError("Duplicate Skill case ID")
        ids.add(case["id"])
        inputs.add(digest(_canonical_value({
            k: v for k, v in case.items() if k not in {"id", "split", "provenance"}
        })))
    return ids, inputs


def task_set_sha256(cases):
    """Freeze split membership from distinct case inputs, independent of labels and order."""
    _, inputs = _members(cases)
    return digest(sorted(inputs))


def _read_tasks(path, raw_sha256, split):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != raw_sha256:
        raise ValueError("Frozen Skill split changed")
    cases = json.loads(data)
    ids, inputs = _members(cases)
    if any(case.get("split") != split for case in cases):
        raise ValueError("Skill task belongs to another declared split")
    return cases, ids, inputs


def migrate_holdout(control, raw_sha256, archive):
    """Bind an already consumed legacy Skill claim to its verified task set."""
    def archive_scope():
        _, _, inputs = _read_tasks(archive, raw_sha256, "holdout")
        return TASK_SCOPE + digest(sorted(inputs))

    return control.bind_consumed_holdout(LEGACY_SCOPE + raw_sha256, archive_scope)


class Comparator:
    """Bind a repo, original baseline and two disjoint externally declared splits.

    config contains comparison (the existing comparator config, including client),
    allowed_paths, and splits. Descriptors freeze path, sha256, scope and task_count.
    New finals also freeze the holdout task_set_sha256 before any holdout access.
    Holdout bytes are only opened by run(split='holdout'), after the caller's
    WorkControl final claim. The controller must use that declared scope.
    """

    previous_holdout_scope_prefix = LEGACY_SCOPE

    def __init__(self, repo, config, baseline_source):
        self.repo = Path(repo).resolve()
        self.config = copy.deepcopy(config)
        if set(config) != {"comparison", "allowed_paths", "splits"}:
            raise ValueError("Unknown or missing Skill comparator configuration")
        comparison = config["comparison"]
        if "client" not in comparison or comparison["mode"] != "update":
            raise ValueError("Skill search requires an explicit bounded provider update config")
        if set(config["splits"]) != {"development", "holdout"}:
            raise ValueError("Separate development and holdout descriptors are required")
        dev, final = (config["splits"][key] for key in ("development", "holdout"))
        if dev["scope"] == final["scope"] or dev["sha256"] == final["sha256"]:
            raise ValueError("Development and holdout must have distinct declared identities")
        for split in (dev, final):
            if (
                set(split) - {"task_set_sha256"} != {"path", "sha256", "scope", "task_count"}
                or ("task_set_sha256" in split and (
                    not isinstance(split["task_set_sha256"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", split["task_set_sha256"])
                ))
                or type(split["task_count"]) is not int
                or split["task_count"] < 1
                or not Path(split["path"]).is_absolute()
            ):
                raise ValueError("Split requires an absolute source and frozen identity/count")
        self.baseline = comparison["snapshots"]["baseline"]["git_revision"]
        root = Path(baseline_source)
        library = compare.snapshot(self.repo, self.baseline, comparison["skill_root"], root)
        bundle = KnowledgeReader(skill_root=library).read("checkout:" + comparison["skill"])
        self.original = dict(bundle.content)
        if set(config["allowed_paths"]) - self.original.keys():
            raise ValueError("Allowed edits must belong to the original Skill bundle")
        self._controllers = {
            name: sha256(compare.ROOT / name)
            for name in (
                *compare.CONTROLLERS,
                "tools/speculative_skill.py",
                "tools/skill_eval_improve.py",
            )
        }
        self.identity = digest(
            {
                "config": config,
                "baseline": self.baseline,
                "resources": {k: digest(v.hex()) for k, v in self.original.items()},
                "controllers": self._controllers,
            }
        )
        self._config_digest = digest(self.config)
        self.holdout_scope = (
            TASK_SCOPE + final["task_set_sha256"] if "task_set_sha256" in final else None
        )

    def export_root(self, destination):
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=False)
        for name, value in self.original.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)
        return destination

    def _read_split(self, split):
        descriptor = self.config["splits"][split]
        cases, ids, inputs = _read_tasks(descriptor["path"], descriptor["sha256"], split)
        if len(cases) * self.config["comparison"]["limits"]["repeats"] != descriptor["task_count"]:
            raise ValueError("Skill trial count differs from the frozen split")
        frozen_set = descriptor.get("task_set_sha256")
        if frozen_set is not None and digest(sorted(inputs)) != frozen_set:
            raise ValueError("Frozen Skill task set differs from its declared identity")
        return cases, ids, inputs

    def run(self, candidate, output, deadline, *, split):
        if digest(self.config) != self._config_digest or any(
            sha256(compare.ROOT / name) != expected for name, expected in self._controllers.items()
        ):
            raise ValueError("Frozen Skill configuration or controller changed")
        files = candidates.members(candidate)
        if set(files) != self.original.keys():
            raise ValueError("Skill candidate changed the frozen bundle membership")
        edits = {
            name: path.read_text(encoding="utf-8")
            for name, path in files.items()
            if path.read_bytes() != self.original[name]
        }
        if set(edits) - set(self.config["allowed_paths"]):
            raise ValueError("Skill candidate changed a protected resource")
        comparison = copy.deepcopy(self.config["comparison"])
        revisions, _ = materialize(
            self.repo,
            self.baseline,
            comparison["skill_root"],
            comparison["skill"],
            {"inv": edits} if edits else {},
            self.config["allowed_paths"],
        )
        if split == "holdout" and self.holdout_scope is None:
            raise ValueError("Skill final requires a frozen holdout task_set_sha256")
        cases, ids, inputs = self._read_split(split)
        if split == "holdout":
            _, development_ids, development_inputs = self._read_split("development")
            if ids & development_ids or inputs & development_inputs:
                raise ValueError("Development and holdout Skill tasks overlap")
        output.mkdir(parents=True, exist_ok=False)
        comparison.update(
            cases="tasks.json",
            snapshots={
                "baseline": {"git_revision": self.baseline},
                "candidate": {"git_revision": revisions.get("inv", self.baseline)},
            },
        )
        atomic_write_json(output / "tasks.json", cases)
        atomic_write_json(output / "config.json", comparison)
        prepared = output / "comparison"
        authorization = compare.prepare(output / "config.json", self.repo, prepared)
        environment = runtime_environment()
        environment["PYTHONPATH"] = str(compare.ROOT) + os.pathsep + environment["PYTHONPATH"]
        command = (
            sys.executable,
            "-m",
            "tools.speculative_skill",
            "--output",
            str(prepared),
            "--authorization",
            authorization,
        )
        record = execute_trial(
            command,
            compare.ROOT,
            output / "execution",
            time.monotonic() + max(0, deadline - time.time()),
            None,
            environment=environment,
            include_cleanup=True,
        )
        if sha256(prepared / "plan/freeze.json") != authorization:
            raise ValueError("Skill comparison plan changed during execution")
        report = compare.read_report(prepared)
        atomic_write_json(output / "report.json", report)
        return report, record["cleanup_verified"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authorization", required=True)
    args = parser.parse_args()
    compare.execute(args.output, args.authorization, require_request_authorization=True)
    compare.report(args.output)


if __name__ == "__main__":
    main()
