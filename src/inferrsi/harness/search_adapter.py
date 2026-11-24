"""Artifact-backed finite-edit generation and authenticated command evaluations.

Commands and graders are trusted host inputs frozen before search. Candidates
must run in a sandbox supplied by the application when their code is untrusted;
the existing local process domain supplies cleanup, not filesystem isolation.
"""

import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path, PureWindowsPath

from inferrsi.contracts.claim import Verdict

from . import candidates
from . import search_tree as tree
from .artifact_primitives import digest, sha256
from .atomic_json import atomic_write_json
from .optimization_session import runtime_environment
from .search_records import encode
from .trials.external import execute_trial
from .verification_plans import Job


def development_binding(adapter):
    """Bind search evidence to the evaluator's frozen experiment, when supplied."""
    evaluator = getattr(adapter, "evaluator", None)
    if getattr(evaluator, "final_only", False):
        raise ValueError("A holdout-bound evaluator can only run during final validation")
    identity = getattr(evaluator, "experiment_identity", None)
    return {} if identity is None else {"experiment_identity": identity}


def validate_development_evidence(state, binding):
    if binding and any(attempt.experiment_identity != binding["experiment_identity"]
                       for attempt in state.attempts):
        raise ValueError("Imported evidence belongs to another development experiment")


@dataclass(frozen=True)
class Edit:
    token: str
    path: str
    before: str
    after: str

    def __post_init__(self):
        path = Path(self.path)
        if (
            not self.token
            or not self.before
            or self.before == self.after
            or path.is_absolute()
            or ".." in path.parts
            or not path.parts
        ):
            raise ValueError("Edit must name one permitted relative file and a nonempty change")


class ArtifactAdapter:
    def __init__(self, root, edits, checks, evaluator, *, domain):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.edits, self.checks = tuple(edits), dict(checks)
        if (
            not self.edits
            or len({e.token for e in self.edits}) != len(self.edits)
            or not self.checks
            or any(type(v) is not int or v <= 0 for v in self.checks.values())
            or not domain
        ):
            raise ValueError("Frozen edit vocabulary, check caps and domain are required")
        self.evaluator, self.domain = evaluator, domain
        self.identity = digest(
            {
                "edits": [asdict(e) for e in self.edits],
                "checks": self.checks,
                "evaluator": evaluator.identity,
                "domain": domain,
                "generation": "finite-edit-softmax-v1",
            }
        )

    def path(self, node):
        path = self.root / "candidates" / node.candidate_id
        if path.parent != self.root / "candidates" or path.is_symlink():
            raise ValueError("Candidate ID must name one retained snapshot")
        if candidates.identity(path) != node.artifact_digest:
            raise ValueError("Retained candidate artifact changed")
        return path

    def import_root(self, source, *, snapshot, context):
        destination = self.root / "candidates" / "root"
        destination.parent.mkdir(exist_ok=True)
        fingerprint = candidates.retain(Path(source), destination)
        return tree.Candidate(
            "root",
            fingerprint,
            None,
            tree.Producer(snapshot, self.identity, digest(context), digest([])),
        )

    def jobs(self, state):
        return tuple(
            Job(f"{node.candidate_id}:{check}", self.checks[check], node.candidate_id, check)
            for node in state.candidates
            if tree.candidate_valid(state, node.candidate_id)
            and not any(
                r.verdict == Verdict.FAIL for r in tree.evidence(state, node.candidate_id).values()
            )
            for check in tree.missing_checks(state, node.candidate_id)
        )

    def domains(self, kind, node, check):
        return (self.domain,) if kind == "verify" else ()

    def _save(self, operation, binding, result):
        if Path(operation).name != operation or operation in (".", ".."):
            raise ValueError("Operation must name one retained execution")
        binding = binding | {"adapter": self.identity, "operation": operation}
        path = self.root / "receipts" / (operation + ".json")
        path.parent.mkdir(exist_ok=True)
        atomic_write_json(
            path,
            {
                "binding": binding,
                "result": result,
                "digest": digest({"binding": binding, "result": result}),
            },
        )
        return result

    def draft(self, parent, state, snapshot, rng, operation, deadline):
        started = time.monotonic()
        source = self.path(parent)
        files = candidates.members(source)
        legal = [
            (index, edit)
            for index, edit in enumerate(self.edits)
            if edit.path in files
            and files[edit.path].read_text(encoding="utf-8").count(edit.before) == 1
        ]
        choice, node = None, None
        if legal and time.time() < deadline:
            vectors = [
                tuple(float(i == index) for i in range(len(self.edits))) for index, _ in legal
            ]
            choice = snapshot.choose(
                "drafter",
                [edit.token for _, edit in legal],
                vectors,
                rng=rng,
                context=digest(asdict(parent)),
                collect=True,
            )
            edit = legal[choice.selected][1]
            destination = self.root / "candidates" / operation
            candidates.retain(source, destination)
            path = destination / edit.path
            text = path.read_text(encoding="utf-8")
            path.write_text(text.replace(edit.before, edit.after, 1), encoding="utf-8")
            node = tree.Candidate(
                operation,
                candidates.identity(destination),
                parent.candidate_id,
                tree.Producer(
                    digest(snapshot.document()),
                    self.identity,
                    digest(asdict(parent)),
                    digest([encode(r) for r in state.receipts]),
                ),
                parent.dependencies,
            )
        result = {
            "candidate": asdict(node) if node else None,
            "choice": asdict(choice) if choice else None,
            "cleanup_verified": True,
            "elapsed_ms": max(1, math.ceil((time.monotonic() - started) * 1000)),
        }
        if time.time() >= deadline:
            result["candidate"] = None
            result["error"] = "draft_deadline"
        return self._save(operation, {"candidate": asdict(parent), "kind": "draft"}, result)

    def verify(self, node, check, operation, deadline):
        started = time.monotonic()
        source = self.path(node)
        output = self.root / "executions" / operation
        result = self.evaluator.evaluate(source, check, output, deadline)
        if candidates.identity(source) != node.artifact_digest:
            raise ValueError("Evaluation changed the retained candidate")
        verdict = Verdict(result["verdict"])
        objective = result.get("objective")
        if objective is not None and (
            type(objective) not in (int, float) or not math.isfinite(objective)
        ):
            raise ValueError("Nonfinite benchmark score")
        result = {
            **result,
            "verdict": verdict.value,
            "elapsed_ms": max(1, math.ceil((time.monotonic() - started) * 1000)),
            "evidence_digest": digest(result),
            "objective": objective,
        }
        return self._save(
            operation, {"candidate": asdict(node), "check": check, "kind": "verify"}, result
        )

    def _matches_legacy_execution(self, operation, result):
        record = getattr(self.evaluator, "legacy_execution_record", None)
        if not record:
            return False
        relative = Path("executions") / operation / record
        path = self.root / relative
        if not path.is_file():
            return False
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != result.get("execution_sha256"):
            return False
        # Compare the operation-specific suffix, so moving an archive preserves its evidence.
        result_path = json.loads(raw).get("result_path")
        suffix = relative.with_name("result.json").parts
        if not isinstance(result_path, str):
            return False
        return PureWindowsPath(result_path).parts[-len(suffix):] == suffix

    def recover_accounting(self, operation, pending):
        """Read the bound physical receipt without adopting candidate output."""
        if Path(operation).name != operation or operation in (".", ".."):
            raise ValueError("Operation must name one retained execution")
        path = self.root / "receipts" / (operation + ".json")
        if not path.is_file():
            return None
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if (
            digest({"binding": receipt["binding"], "result": receipt["result"]})
            != receipt["digest"]
        ):
            raise ValueError("Recovery receipt changed")
        expected = {
            "candidate": pending["binding"]["candidate"],
            "kind": pending["kind"],
            "adapter": self.identity,
        }
        if pending["kind"] == "verify":
            expected["check"] = pending["binding"]["check"]
        if "operation" in receipt["binding"]:
            expected["operation"] = operation
        elif pending.get("final") and not self._matches_legacy_execution(
            operation, receipt["result"]
        ):
            raise ValueError("Legacy final receipt lacks matching operation execution evidence")
        if digest(expected) != digest(receipt["binding"]):
            raise ValueError("Recovery receipt belongs to a different operation")
        return receipt["result"]

    def recover(self, operation, pending):
        result = self.recover_accounting(operation, pending)
        if result is None:
            return None
        for raw in (pending["binding"]["candidate"], result.get("candidate")):
            if raw is not None:
                self.path(
                    tree.Candidate(
                        **(
                            raw
                            | {
                                "producer": tree.Producer(**raw["producer"]),
                                "dependencies": tuple(
                                    tree.Dependency(**d) for d in raw["dependencies"]
                                ),
                            }
                        )
                    )
                )
        return result


class CommandEvaluator:
    """Frozen independent evaluator command with explicit JSON result protocol.

    The grader writes {verdict, objective?} to {result}; the shared executor
    independently supplies process/cleanup facts. Useful for project protocols
    and CPU integration controls, not an implicit production qualification.
    """

    legacy_execution_record = "execution.json"

    def __init__(self, commands, resources):
        self.commands = {key: tuple(value) for key, value in commands.items()}
        self.resources = {Path(path).resolve(): sha256(Path(path)) for path in resources}
        self.identity = digest(
            {"commands": self.commands, "resources": {str(k): v for k, v in self.resources.items()}}
        )

    def evaluate(self, candidate, check, output, deadline):
        if any(sha256(path) != expected for path, expected in self.resources.items()):
            raise ValueError("Frozen evaluator resources changed")
        command = tuple(arg.replace("{candidate}", str(candidate)) for arg in self.commands[check])
        output.parent.mkdir(parents=True, exist_ok=True)
        record = execute_trial(
            command,
            candidate,
            output,
            time.monotonic() + max(0, deadline - time.time()),
            None,
            environment=runtime_environment(),
            include_cleanup=True,
        )
        result = {
            "verdict": "INCONCLUSIVE",
            "objective": None,
            "cleanup_verified": record["cleanup_verified"],
            "execution_sha256": sha256(output / "execution.json"),
        }
        if (
            record["status"] == "completed"
            and record["returncode"] == 0
            and record["cleanup_verified"] is True
        ):
            document = json.loads(Path(record["result_path"]).read_text(encoding="utf-8"))
            result.update(
                verdict=Verdict(document["verdict"]).value,
                objective=document.get("objective"),
                result_sha256=sha256(Path(record["result_path"])),
            )
        if any(sha256(path) != expected for path, expected in self.resources.items()):
            raise ValueError("Evaluator resources changed during execution")
        return result
