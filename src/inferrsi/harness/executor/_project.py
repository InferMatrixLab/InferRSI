"""Freeze an ordinary project's commands, instructions and acceptance inputs."""

import math
import shutil
from pathlib import Path

from inferrsi.harness.evaluator import MIN_PAIRS
from inferrsi.harness.records.artifact_primitives import sha256

PROJECT_DECISIONS = ("point", "paired")


def validate_project(settings: dict) -> None:
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
    if "quality_benchmark" in settings and not (
        isinstance(settings["quality_benchmark"], str) and settings["quality_benchmark"].strip()
    ):
        raise ValueError("An explicit quality benchmark identity is required")
    if settings["direction"] not in ("minimize", "maximize"):
        raise ValueError("Metric direction must be explicit")
    if type(settings["repetitions"]) is not int or settings["repetitions"] < 1:
        raise ValueError("Positive repetitions required")
    if type(settings["warmups"]) is not int or settings["warmups"] < 0:
        raise ValueError("Nonnegative warmups required")
    value = settings["min_improvement_pct"]
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("An explicit finite nonnegative improvement gate is required")
    if settings.get("decision", "point") not in PROJECT_DECISIONS:
        raise ValueError("Decision must be point or paired")
    if settings.get("decision") == "paired" and settings["repetitions"] < MIN_PAIRS:
        raise ValueError(f"A paired decision needs at least {MIN_PAIRS} repetitions")
    if type(settings.get("require_explanation", False)) is not bool:
        raise ValueError("require_explanation must be a boolean")
    if settings.get("require_explanation") and settings["repetitions"] < MIN_PAIRS:
        # Fewer pairs give no interval for any expectation, so every round would be
        # unverifiable and no candidate could ever be adopted.
        raise ValueError(f"--require-explanation needs at least {MIN_PAIRS} repetitions")


def prepare_project(destination: Path, protocol: Path, instructions: Path, settings: dict) -> dict:
    """Retain the caller's explicit acceptance inputs, without inventing criteria."""
    validate_project(settings)
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
