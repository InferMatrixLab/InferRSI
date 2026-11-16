"""Harness protocol for caller-supplied project checks and retained outputs.

The caller supplies the workload, measurement and quality meaning. This adapter
does not infer acceptance from natural language or launch any commands.
"""

import json
import math
import shutil
from pathlib import Path
from statistics import median

from .artifact_primitives import sha256
from .measurement import MIN_PAIRS, explain, paired_statistics, profile_evidence, validate_mechanism

DECISIONS = ("point", "paired")


def validate(settings: dict) -> None:
    for key in ("measure_command", "quality_command"):
        command = settings[key]
        if not command or not all(isinstance(arg, str) and arg for arg in command):
            raise ValueError(f"An explicit {key} argv is required")
        if not any("{protocol}" in arg for arg in command):
            raise ValueError(f"{key} must use a retained {{protocol}} script")
        if not any("{result}" in arg for arg in command):
            raise ValueError(f"{key} must write to the supplied {{result}} path")
    for key in ("metric_key", "metric_unit", "quality_key", "scope"):
        if not isinstance(settings[key], str) or not settings[key].strip():
            raise ValueError(f"An explicit {key} is required")
    if settings["direction"] not in ("minimize", "maximize"):
        raise ValueError("Metric direction must be explicit")
    if type(settings["repetitions"]) is not int or settings["repetitions"] < 1:
        raise ValueError("Positive repetitions required")
    if type(settings["warmups"]) is not int or settings["warmups"] < 0:
        raise ValueError("Nonnegative warmups required")
    value = settings["min_improvement_pct"]
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("An explicit finite nonnegative improvement gate is required")
    if settings.get("decision", "point") not in DECISIONS:
        raise ValueError("Decision must be point or paired")
    if settings.get("decision") == "paired" and settings["repetitions"] < MIN_PAIRS:
        raise ValueError(f"A paired decision needs at least {MIN_PAIRS} repetitions")
    if type(settings.get("require_explanation", False)) is not bool:
        raise ValueError("require_explanation must be a boolean")


def prepare(destination: Path, protocol: Path, instructions: Path, settings: dict) -> dict:
    """Retain the caller's explicit acceptance inputs, without inventing criteria."""
    validate(settings)
    if not protocol.is_dir() or protocol.is_symlink() or not instructions.is_file():
        raise ValueError("Existing protocol directory and task instructions are required")
    if destination.resolve().is_relative_to(protocol.resolve()):
        raise ValueError("Frozen output must be outside the protocol directory")
    paths = [p for p in protocol.rglob("*") if p.is_file()]
    if not paths or any(p.is_symlink() for p in protocol.rglob("*")):
        raise ValueError("Protocol must contain regular retained files")
    before = {p.relative_to(protocol).as_posix(): sha256(p) for p in paths}
    destination.mkdir(parents=True)
    shutil.copytree(protocol, destination / "protocol")
    (destination / "TASK.md").write_bytes(instructions.read_bytes())
    after = {p.relative_to(protocol).as_posix(): sha256(p)
             for p in protocol.rglob("*") if p.is_file()}
    copied = {p.relative_to(destination / "protocol").as_posix(): sha256(p)
              for p in (destination / "protocol").rglob("*") if p.is_file()}
    if before != after or copied != before:
        raise ValueError("Acceptance inputs changed during freeze")
    return {"evaluation_settings": settings,
            "frozen_files": {p.relative_to(destination).as_posix(): sha256(p)
                             for p in destination.rglob("*") if p.is_file()}}


def steps(settings: dict) -> list[dict]:
    result = [{"id": f"quality-{side}", "phase": "quality", "side": side,
               "argv": settings["quality_command"]} for side in ("baseline", "candidate")]
    for phase, count in (("warmup", settings["warmups"]),
                         ("measurement", settings["repetitions"])):
        for index in range(count):
            for side in (("baseline", "candidate") if index % 2 == 0
                         else ("candidate", "baseline")):
                result.append({"id": f"{phase}-{index + 1:03d}-{side}",
                               "phase": phase, "side": side,
                               "argv": settings["measure_command"]})
    return result


def _value(document, key):
    value = document
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def inspect_step(directory: Path, settings: dict, definition: dict, execution: dict) -> dict:
    """Interpret one frozen script's explicit result, never guess a crash's cause."""
    failure = {"status": "infrastructure_failure", "reason": "failed_execution"}
    if execution.get("status") != "completed":
        return failure
    relative = "execution/" + definition["id"] + "/result.json"
    path = directory / relative
    try:
        if path.is_symlink():
            raise ValueError("Symbolic result")
        document = json.loads(path.read_bytes())
        if not isinstance(document, dict):
            raise ValueError("Result must be an object")
    except (OSError, ValueError):
        return {**failure, "reason": "missing_or_invalid_result"}
    evidence = {relative: sha256(path)}
    rejected = document.get("status") == "candidate_failure"
    quality = _value(document, settings["quality_key"])
    if rejected or (definition["phase"] == "quality" and quality is False):
        return {"status": ("candidate_failure" if definition["side"] == "candidate"
                           else "infrastructure_failure"),
                "reason": "candidate_check_rejected" if definition["side"] == "candidate"
                          else "baseline_check_rejected",
                "quality_passed": False if definition["phase"] == "quality" else None,
                "evidence_files": evidence}
    if definition["phase"] == "quality" and type(quality) is not bool:
        return {**failure, "reason": "missing_boolean_quality_evidence", "evidence_files": evidence}
    value = _value(document, settings["metric_key"])
    if definition["phase"] == "measurement" and (
        type(value) not in (int, float) or not math.isfinite(value) or value <= 0
    ):
        return {**failure, "reason": "invalid_metric", "evidence_files": evidence}
    profile = {key: document[key] for key in ("breakdown", "counters") if key in document}
    return {"status": "completed", "value": value, "profile": profile,
            "evidence_files": evidence}




def assess(directory: Path, settings: dict, execution: dict, *,
           mechanism: dict | None = None) -> dict:
    """Judge one attempt; ``mechanism`` is the declaration bound before execution."""
    evidence = {}

    def result(status, reason, **fields):
        return {"status": status, "score": None,
                "verdict": "FAIL" if status == "candidate_failure" else "INCONCLUSIVE",
                "reason": reason, "evidence_files": evidence, **fields}

    expected = steps(settings)
    actual = execution.get("steps", [])
    checks = execution.get("source_checks", [])
    if (not actual or len(actual) > len(expected) or len(checks) != len(actual)
            or any(c.get("verified") is not True for c in checks)):
        return result("infrastructure_failure", "incomplete_execution")
    samples = {"baseline": [], "candidate": []}
    profiles = {"baseline": [], "candidate": []}
    candidate_quality = None
    for definition, record in zip(expected, actual):
        if record.get("id") != definition["id"]:
            return result("infrastructure_failure", "failed_or_mismatched_execution")
        checked = inspect_step(directory, settings, definition, record)
        evidence.update(checked.get("evidence_files", {}))
        if checked["status"] != "completed":
            return result(checked["status"], checked["reason"],
                          quality_passed=(checked.get("quality_passed")
                                          if checked.get("quality_passed") is not None
                                          else candidate_quality))
        if definition["phase"] == "quality" and definition["side"] == "candidate":
            candidate_quality = True
        if definition["phase"] == "measurement":
            samples[definition["side"]].append(checked["value"])
            profiles[definition["side"]].append(checked["profile"])
    if execution.get("status") != "completed" or len(actual) != len(expected):
        return result("infrastructure_failure", "incomplete_execution")
    before, after = median(samples["baseline"]), median(samples["candidate"])
    improvement = (after - before) / before * 100
    if settings["direction"] == "minimize":
        improvement = -improvement
    speedup = before / after if settings["direction"] == "minimize" else after / before
    if not all(math.isfinite(value) for value in (improvement, speedup)):
        return result("infrastructure_failure", "nonfinite_derived_metric")
    point_accepted = improvement > 0 and improvement >= settings["min_improvement_pct"]
    decision = settings.get("decision", "point")
    paired = paired_statistics(samples["baseline"], samples["candidate"],
                               direction=settings["direction"],
                               min_improvement_pct=settings["min_improvement_pct"],
                               point_gate_passed=point_accepted,
                               decides=decision == "paired")
    verdict, reason = (("PASS", "fixed_checks_satisfied") if point_accepted
                       else ("FAIL", "performance_gate_not_met"))
    if decision == "paired":
        relation = paired.get("gate_relation")
        if paired.get("status") != "available":
            verdict, reason = "INCONCLUSIVE", "paired_statistics_unavailable"
        elif relation == "above_gate":
            verdict, reason = "PASS", "paired_interval_above_gate"
        elif relation == "straddles_gate":
            # Not shown to pass is not evidence that the gate was missed.
            verdict, reason = "INCONCLUSIVE", "within_noise"
        else:
            verdict, reason = "FAIL", "performance_gate_not_met"
    try:
        mechanism = None if mechanism is None else validate_mechanism(mechanism)
        mechanism_error = None
    except ValueError as error:
        mechanism, mechanism_error = None, str(error)
    reference = [item["region"] for item in (mechanism or {}).get("expect", [])
                 if "region" in item and item["direction"] == "unchanged"]
    try:
        observed = profile_evidence(profiles["baseline"], profiles["candidate"],
                                    reference_regions=reference,
                                    family_size=len((mechanism or {}).get("expect", [])) or 1)
    except (ArithmeticError, TypeError, ValueError) as error:
        # Profile evidence is a report: a failure here must not change the verdict.
        observed = {"status": "unavailable", "reason": f"Profile evidence failed: {error}"}
    explanation = explain(mechanism, observed)
    if mechanism_error:
        explanation = {"status": "unverifiable", "reason": mechanism_error}
    if settings.get("require_explanation", False) and verdict == "PASS":
        # Only evidence against the prediction fails; missing evidence is INCONCLUSIVE.
        if explanation["status"] == "contradicted":
            verdict, reason = "FAIL", "explanation_" + explanation["status"]
        elif explanation["status"] != "explained":
            verdict, reason = "INCONCLUSIVE", "explanation_" + explanation["status"]
    accepted = verdict == "PASS"
    return result(
        "completed", reason,
        verdict=verdict, score=after, baseline_score=before,
        eligible=accepted, quality_passed=True, improvement_pct=improvement, speedup=speedup,
        metrics={"name": settings["metric_key"], "unit": settings["metric_unit"],
                 "direction": settings["direction"], "baseline": before, "candidate": after,
                 "samples": samples},
        scope=settings["scope"], statistical_significance="not_established",
        paired_statistics=paired, decision=decision,
        require_explanation=settings.get("require_explanation", False),
        profile_evidence=observed, explanation=explanation,
        quality_contract="Only the supplied frozen quality script and its boolean result",
        environment_qualification="Caller-managed; no automatic hardware isolation claim",
    )
