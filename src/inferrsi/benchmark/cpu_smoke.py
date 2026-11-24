"""The accepted CPU evidence-smoke profile; configuration reads only owned worker bytes."""

from copy import deepcopy
from hashlib import sha256
from importlib.resources import files
from io import BytesIO

from . import preparation


def worker_source() -> bytes:
    """Explicit read-only resource port; no worker import or execution."""
    return files("inferrsi.benchmark.workers").joinpath("fixture_worker.py").read_bytes()


def protocol(worker_bytes: bytes, *, control_domain: str) -> dict:
    """Build a protocol from supplied bytes, with no host I/O or guessed domain."""
    if not isinstance(worker_bytes, bytes):
        raise TypeError("Expected worker source bytes.")
    preparation._require(preparation._id(control_domain), "Invalid actual control domain.")
    digest = sha256(worker_bytes).hexdigest()
    pin = {
        "artifact": {"location": "tasks/p1-cpu-smoke/fixture_worker.py", "sha256": digest,
                     "size_bytes": len(worker_bytes), "media_type": "text/x-python"},
        "format_schema": {"name": "utf8-text", "revision": "1"},
        "required_for": ["prepare", "execute"],
    }
    requirements = []
    for key, claim, phase, kinds in (
        ("format", "F", "preparing", ["harness_capture"]),
        ("grader", "C", "finalizing", ["task_worker"]),
        ("samples", "M", "running", ["harness_capture", "task_worker"]),
        ("cleanup", "M", "finalizing", ["harness_capture"]),
    ):
        requirements.append({
            "check_id": key, "checker_revision": "1", "allowed_producer_kinds": kinds,
            "subject": "candidate", "phase": phase,
            "artifact_schema": {"name": key + "-proof", "revision": "1"},
            "matching_rule_revision": "1", "allowed_control_domains": [control_domain],
            "for_claims": [claim],
        })
    return {
        "schema_version": 1, "task": {"name": "p1-cpu-smoke", "revision": "1"},
        "grader": {"name": "p1-cpu-smoke-rules", "revision": "1"},
        "operation": "evaluate", "validation_scope": "p1",
        "candidate_contract": deepcopy(preparation._CANDIDATE),
        "worker_recipe": {
            "recipe_revision": "1", "runtime_role": "local-python",
            "entrypoint_kind": "python_module", "entrypoint": "fixture_worker",
            "entrypoint_revision": "1", "code_sha256": digest,
            "args": ["{input:candidate}", "{output:grader}"], "input_roles": ["candidate"],
            "outputs": [{"role": "grader", "path": "outputs/grader.json", "required": True,
                         "media_type": "application/json",
                         "format_schema": {"name": "fixture-grader", "revision": "1"}}],
            "required_capabilities": ["local-process-tree"],
        },
        "input_requirements": {"candidate_role": "candidate"},
        "claim_definitions": [{
            "claim_id": key, "validation_scope": "p1",
            "decision_rule": {"name": "p1-" + key, "revision": "1"},
            "required_checks": checks, "requires_completed_measurement": key == "M",
            "requires_cleanup_confirmed": key == "M",
        } for key, checks in (("F", ["format"]), ("C", ["grader"]),
                               ("M", ["samples", "cleanup"]))],
        "metric_definitions": [], "required_evidence": requirements,
        "task_parameters": {"decimal_fixture": "1.25", "label": "CPU evidence smoke"},
        "baseline": {"role": "baseline-code", **deepcopy(pin)},
        "reference": None, "quality_reference": None,
        "sampling": {"order": ["AB", "BA"], "repetitions": 2},
        "feedback_visibility": ["format"], "budget_policy_refs": [],
        "resources": [{"role": "worker-code", **deepcopy(pin)}],
        "display_notes": "CPU handoff/evidence smoke; no performance-gain or model-quality claim.",
    }


def prepare_service(*, control_domain: str):
    """Snapshot the packaged worker; close resources through the existing prepare port."""
    source = worker_source()

    def resources(role):
        if role not in ("worker-code", "baseline-code"):
            raise FileNotFoundError("Unknown task resource role.")
        return BytesIO(source)

    return preparation.PreparationService(
        protocol(source, control_domain=control_domain), resources=resources,
        worker_role="worker-code",
    )


def default_request():
    return {
        "schema_version": 1, "task": {"name": "p1-cpu-smoke", "revision": "1"},
        "operation": "evaluate", "validation_scope": "p1", "input_pins": [],
        "task_parameters": {"decimal_fixture": "1.25", "label": "CPU evidence smoke"},
        "comparison_conditions": {}, "expected_candidate": None, "budget_policy_refs": [],
    }
