"""Inputs for one managed campaign or packaged benchmark session operation."""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal


@dataclass(frozen=True, kw_only=True)
class _Session:
    session: Path


@dataclass(frozen=True, kw_only=True)
class _StartSession(_Session):
    action: ClassVar[str] = "start"
    rounds: int
    max_minutes: float
    evaluation_timeout_seconds: float
    condition: str
    python: str = sys.executable
    evaluation_prefix: str = ""
    final_reserve_seconds: float | None = None
    knowledge: Literal["on", "off"] = "on"
    ranking_policy: str = "default"


@dataclass(frozen=True, kw_only=True)
class StartBenchmarkSession(_StartSession):
    task: str
    evaluation_args: str
    round_mode: Literal["exact", "up_to"] = "exact"


@dataclass(frozen=True, kw_only=True)
class StartProjectSession(_StartSession):
    repo: Path
    include: list[str]
    protocol: Path
    instructions: Path
    round_mode: Literal["exact", "up_to"] = "up_to"
    evaluation_mode: Literal["abba", "service_reuse"] = "abba"
    evaluation_config: Path | None = None
    allow_final_continuation: bool = False
    measure_command: str | None = None
    quality_command: str | None = None
    metric_key: str | None = None
    metric_unit: str | None = None
    quality_key: str | None = None
    quality_benchmark: str | None = None
    scope: str | None = None
    direction: Literal["minimize", "maximize"] | None = None
    min_improvement_pct: float | None = None
    repetitions: int | None = None
    warmups: int | None = None
    decision: Literal["point", "paired"] = "point"
    require_explanation: bool = False


@dataclass(frozen=True, kw_only=True)
class SessionStatus(_Session):
    action: ClassVar[str] = "status"


@dataclass(frozen=True, kw_only=True)
class DiagnoseSession(_Session):
    action: ClassVar[str] = "diagnose"
    bottleneck: str
    evidence: Path


@dataclass(frozen=True, kw_only=True)
class ReadSessionKnowledge(_Session):
    action: ClassVar[str] = "knowledge-read"
    search_ref: str
    locator: str
    page: int = 1


@dataclass(frozen=True, kw_only=True)
class _Retryable(_Session):
    retry_of: str | None = None
    repair_protocol: Path | None = None
    repair_reason: str | None = None
    cleanup_receipt: Path | None = None


@dataclass(frozen=True, kw_only=True)
class BaselineSession(_Retryable):
    action: ClassVar[str] = "baseline"


@dataclass(frozen=True, kw_only=True)
class EvaluateSessionRound(_Retryable):
    action: ClassVar[str] = "round"
    candidate: Path
    hypothesis: str
    strategy: str | None = None
    alternative: list[str] | None = None
    selection_reason: str | None = None
    knowledge_ref: list[str] | None = None
    mechanism_file: Path | None = None
    usage_export: Path | None = None
    continue_after_final: str | None = None
    continuation_reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class FinalizeSession(_Session):
    action: ClassVar[str] = "final"
    usage_export: Path | None = None
    reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class RecoverSession(_Session):
    action: ClassVar[str] = "recover"
    confirm_domain_empty: bool = False
    cleanup_receipt: Path | None = None


@dataclass(frozen=True, kw_only=True)
class ProfileSession(_Session):
    action: ClassVar[str] = "profile"
    round: int


@dataclass(frozen=True, kw_only=True)
class RefreshSessionReferences(_Retryable):
    action: ClassVar[str] = "refresh-references"
    conditions: Path
    reason: str


@dataclass(frozen=True, kw_only=True)
class ResumeSession(_Session):
    action: ClassVar[str] = "resume"
    reason: str
    cleanup_receipt: Path | None = None


SessionRequest = (
    StartProjectSession | StartBenchmarkSession | SessionStatus | DiagnoseSession
    | ReadSessionKnowledge | BaselineSession | EvaluateSessionRound
    | FinalizeSession | RecoverSession | ProfileSession | RefreshSessionReferences | ResumeSession
)
