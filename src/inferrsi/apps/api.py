"""Public Python entry points for evaluating and inspecting Apps runs."""

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Protocol

from .handoff.candidate_provider import CandidateProvider as CandidateProvider
from .handoff.evidence_capture import EvidenceCapture as EvidenceCapture
from .storage.archive import ResourceReader, RunOutput
from .storage.artifact_reader import AssessmentArtifacts
from .views.attempt import read_attempt_view as read_attempt_view
from .workflows import evaluation


class Assessor(Protocol):
    """Benchmark's offline evaluation port."""

    def __call__(
        self, prepared: dict, evidence: dict, /, *, artifacts: AssessmentArtifacts,
    ) -> dict: ...


def prepare(
    request: dict,
    *,
    workspace: Path,
    storage_config: dict,
    prepare_benchmark: Callable[[dict], tuple[dict, bytes, ResourceReader] | dict],
    encode_prepared: Callable[[dict], bytes],
    validate_prepared: Callable[[dict, bytes], None],
    output_id: str | None = None,
) -> RunOutput:
    """Freeze a Benchmark request, archive its closure, and publish the Apps result.

    The host adapts the Benchmark prepare port to return the prepared object,
    protocol bytes and a role-keyed reader. Each stream returned by the reader
    is owned by Apps for that read. The pure encoder and validator raise
    ValueError for invalid content or PublicError for a structured rejection.
    The host adapts any Benchmark-specific rejection exception to those types.
    No Harness port is called during preparation.
    """
    return evaluation.prepare(
        request, workspace=workspace, storage_config=storage_config,
        prepare_benchmark=prepare_benchmark, encode_prepared=encode_prepared,
        validate_prepared=validate_prepared, output_id=output_id,
    )


def execute(
    request: dict,
    *,
    workspace: Path,
    execute_harness: Callable[[dict], dict],
    bind_execution: Callable[[dict], dict] | None = None,
    storage_config: dict | None = None,
    output_id: str | None = None,
) -> RunOutput:
    """Bind the saved request and submit its original attempt to Harness.

    The trusted host supplies the Harness port and a storage configuration for
    the Apps binder, or provides an existing custom binder. Either port may
    raise PublicError or return its wire form. Workspace and output_id locate
    Apps output. Harness owns the RunStore, request identity and replay decisions.
    """
    return evaluation.execute(
        request, workspace=workspace, execute_harness=execute_harness,
        bind_execution=bind_execution, storage_config=storage_config, output_id=output_id,
    )


def assess(
    request: dict,
    *,
    workspace: Path,
    storage_config: dict,
    assess_benchmark: Assessor,
    validate_assessment: Callable[[dict], None],
    encode_assessment: Callable[[dict], bytes],
    output_id: str | None = None,
) -> RunOutput:
    """Assess one fixed record with the supplied offline Benchmark port.

    The port receives the frozen preparation, EvidenceInput and a reader scoped
    to those inputs. It can return or raise a structured public rejection.
    The pure Benchmark validator and encoder check and serialize the result.
    """
    return evaluation.assess(
        request, workspace=workspace, storage_config=storage_config,
        assess_benchmark=assess_benchmark, validate_assessment=validate_assessment,
        encode_assessment=encode_assessment, output_id=output_id,
    )


class EvaluationPort:
    """Apps adapter for the evaluation leg of a Harness generation loop."""

    def __init__(
        self, *, storage_config: dict, output_root_for: Callable[[str], str],
        assess_benchmark: Assessor, validate_assessment: Callable[[dict], None],
        encode_assessment: Callable[[dict], bytes],
    ):
        self._storage_config = deepcopy(storage_config)
        self._output_root_for = output_root_for
        self._assess_benchmark = assess_benchmark
        self._validate_assessment = validate_assessment
        self._encode_assessment = encode_assessment

    def execution_for(
        self, prepared_ref: dict, proposal: dict, attempt: dict, *, scope: str,
    ) -> dict:
        """Bind the frozen worker using Harness's original attempt and scope."""
        return evaluation.execution_for(
            prepared_ref, proposal, attempt, scope=scope, storage_config=self._storage_config,
            output_root_for=self._output_root_for,
        )

    def assess(self, record: dict) -> dict:
        """Return all archived claim results to Harness for its feedback policy."""
        return evaluation.assess_for_feedback(
            record, storage_config=self._storage_config, assess_benchmark=self._assess_benchmark,
            validate_assessment=self._validate_assessment,
            encode_assessment=self._encode_assessment,
        )
