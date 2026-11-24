"""Benchmark-owned evaluators composed with Harness speculative search.

The engine protocol remains one indivisible check; no CPU or partial-case run
can impersonate its NPU performance qualification. Skill grading stays in the
existing independent comparator and quality-first rules.
"""

import math
import sys
import time
from pathlib import Path

from inferrsi.apps.workflows.improvement import assessment
from inferrsi.benchmark.improvement import SelectionPolicy, holdout_accepts
from inferrsi.benchmark.registry import task_resources
from inferrsi.harness import candidates, task_protocol
from inferrsi.harness.artifact_primitives import digest, sha256
from inferrsi.harness.atomic_json import atomic_write_json
from inferrsi.harness.optimization_session import runtime_environment
from inferrsi.harness.trials.external import execute_trial


class EngineEvaluator:
    def __init__(self, package, frozen, *, arguments, python=sys.executable, prefix=()):
        self.frozen = Path(frozen).resolve()
        self.plan = task_protocol.prepare(
            Path(str(task_resources(package))), self.frozen, arguments
        )
        self.python, self.prefix = python, tuple(prefix)
        self.identity = digest(
            {
                "lane": "engine",
                "task": package,
                "plan": self.plan,
                "python": python,
                "prefix": self.prefix,
            }
        )

    def _check_resources(self, *, during=False):
        actual = {
            p.relative_to(self.frozen).as_posix(): sha256(p)
            for p in self.frozen.rglob("*")
            if p.is_file()
        }
        if actual != self.plan["frozen_files"]:
            suffix = " during execution" if during else ""
            raise ValueError("Frozen benchmark resources changed" + suffix)

    def evaluate(self, candidate, check, output, deadline):
        if check != "evaluation":
            raise ValueError("Packaged engine protocol requires one full evaluation job")
        self._check_resources()
        output.mkdir(parents=True)
        candidates.retain(candidate / "candidate.py", output / "candidate.py")
        from inferrsi.harness import optimization_session

        execution = None
        cleanup = True
        try:
            args = task_protocol.run(
                self.frozen,
                self.plan["frozen_files"]["optimization.py"],
                "arguments",
                deadline=time.monotonic() + max(0, deadline - time.time()),
                candidate=output / "candidate.py",
                output=output / "measurement",
                settings=self.plan["evaluation_settings"],
            )
            command = (
                *self.prefix,
                self.python,
                str(Path(optimization_session.__file__).resolve()),
                str(self.frozen / "benchmark.py"),
                *args,
            )
            environment = runtime_environment()
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            execution = execute_trial(
                command,
                output,
                output / "execution",
                time.monotonic() + max(0, deadline - time.time()),
                None,
                environment=environment,
                include_cleanup=True,
            )
            cleanup = execution["cleanup_verified"]
            self._check_resources(during=True)
            assessed = task_protocol.run(
                self.frozen,
                self.plan["frozen_files"]["optimization.py"],
                "assess",
                deadline=time.monotonic() + max(0, deadline - time.time()),
                directory=output,
                settings=self.plan["evaluation_settings"],
                execution=execution,
            )
        except task_protocol.TaskProtocolError as error:
            if error.kind != "timeout":
                raise
            # Retain a real timeout as INCONCLUSIVE even when no time remains
            # for assessment. Cleanup covers both the task and protocol process;
            # an unknown protocol exit cannot release the measurement domain.
            cleanup = cleanup is True and error.cleanup_verified is True
            assessed = {"verdict": "INCONCLUSIVE", "score": None, "reason": "protocol_timeout"}
        self._check_resources(during=True)
        if cleanup is not True:
            assessed = {"verdict": "INCONCLUSIVE", "score": None}
        atomic_write_json(output / "assessment.json", assessed)
        return {
            "verdict": assessed["verdict"],
            "objective": assessed.get("score"),
            "cleanup_verified": cleanup,
            "assessment_sha256": sha256(output / "assessment.json"),
            "execution_sha256": sha256(output / "execution/execution.json")
            if execution is not None else None,
        }


class SkillEvaluator:
    """Use an explicitly bound independent comparator, with an exact lexicographic utility.

    The comparator's run method returns a verified report and cleanup facts; it
    must run the existing Skill comparison for the supplied candidate and split.
    No generic model client or fixed-output fixture is silently selected here.
    """

    def __init__(self, comparator, *, split, policy, token_cap, task_count):
        if not isinstance(policy, SelectionPolicy) or split not in ("development", "holdout"):
            raise ValueError("A frozen Skill selection policy and explicit split are required")
        if (
            type(token_cap) is not int
            or token_cap < 1
            or type(task_count) is not int
            or task_count < 1
            or task_count * (token_cap + 1) > 2**53 - 1
        ):
            raise ValueError("Skill utility must be exactly representable within declared bounds")
        self.comparator, self.split, self.policy = comparator, split, policy
        self.experiment_identity = comparator.identity
        self.final_only = split == "holdout"
        self.holdout_scope = (
            getattr(comparator, "holdout_scope", None) if split == "holdout" else None
        )
        self.previous_holdout_scope_prefix = getattr(
            comparator, "previous_holdout_scope_prefix", None
        )
        self.token_cap, self.task_count = token_cap, task_count
        self.identity = digest(
            {
                "lane": "skill",
                "comparator": comparator.identity,
                "split": split,
                "min_success_rate": policy.min_success_rate,
                "max_regressions": policy.max_regressions,
                "token_cap": token_cap,
                "task_count": task_count,
                "utility": "successes*(token_cap+1)-tokens",
            }
        )

    def validate_final(self, scope):
        if self.split != "holdout" or not self.holdout_scope or scope != self.holdout_scope:
            raise ValueError("Skill final requires a holdout-bound evaluator and its frozen scope")

    def evaluate(self, candidate, check, output, deadline):
        if check != "evaluation":
            raise ValueError("Skill comparison is an indivisible evaluation job")
        report, cleanup = self.comparator.run(candidate, output, deadline, split=self.split)
        score = assessment(report, self.policy)
        tokens = score["usage"]["candidate"]["total_tokens"]
        if (
            cleanup is not True
            or not score["complete"]
            or score["reason"] == "unknown_usage"
            or tokens is None
            or type(tokens) is not int
            or not 0 <= tokens <= self.token_cap
            or score["trials"] != self.task_count
        ):
            verdict, objective = "INCONCLUSIVE", None
        elif score["reason"] not in ("eligible", "no_improvement"):
            verdict, objective = "FAIL", None
        else:
            # One extra success dominates the entire possible token range.
            # This exact radix preserves the existing quality-then-token order.
            verdict = "PASS"
            objective = score["successes"] * (self.token_cap + 1) - tokens
            if not math.isfinite(objective):
                raise ValueError("Invalid Skill utility")
            if self.split == "holdout" and not holdout_accepts(score):
                verdict, objective = "FAIL", None
        return {
            "verdict": verdict,
            "objective": objective,
            "cleanup_verified": cleanup,
            "report_digest": digest(report),
            "assessment": score,
        }
