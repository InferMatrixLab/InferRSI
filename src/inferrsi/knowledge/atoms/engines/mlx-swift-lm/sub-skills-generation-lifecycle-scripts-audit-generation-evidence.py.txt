#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Audit caller generation evidence records; never run tasks, MLX or Metal.

New Python support distilled from mlx-swift-lm lifecycle contracts at
3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac. This is not a Swift API binding,
event-order simulator or native observation authenticator.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SOURCE_COMMIT = "3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac"
MAX_INPUT_BYTES = 65536
MAX_RECORDS = 128
MAX_COUNT = (1 << 63) - 1
TASK_APIS = {"generateTask", "generateLoopTask", "generateTokensTask", "generateTokenTask"}
STREAM_APIS = {"generate", "ModelContainer.generate"}
FIELDS = {"schema_version", "source_repository", "source_commit", "resolved_mlx_commit",
          "declared_backend", "records"}
RECORD_FIELDS = {"generation_id", "api", "consumer_end", "producer_task_retained",
                 "producer_task_join", "final_info", "mlx_default_stream_sync"}


class EvidenceError(ValueError):
    """The caller declaration does not match the bounded evidence schema."""


def _enum(value: Any, choices: set[str]) -> None:
    if not isinstance(value, str) or value not in choices:
        raise EvidenceError("invalid declared enum")


def _commit(value: Any) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{40}", value) is None:
        raise EvidenceError("revision must be a lowercase full commit")


def audit(plan: Any) -> dict[str, Any]:
    """Report declaration gaps/conflicts, never authenticated native cleanup."""
    if type(plan) is not dict or set(plan) != FIELDS:
        raise EvidenceError("invalid top-level schema")
    if type(plan["schema_version"]) is not int or plan["schema_version"] != 1:
        raise EvidenceError("schema_version must be integer 1")
    if plan["source_repository"] != "ml-explore/mlx-swift-lm":
        raise EvidenceError("unsupported source repository")
    _commit(plan["source_commit"])
    if plan["resolved_mlx_commit"] is not None:
        _commit(plan["resolved_mlx_commit"])
    _enum(plan["declared_backend"], {"metal", "cpu", "unknown", "not_run"})
    records = plan["records"]
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_RECORDS:
        raise EvidenceError("records must be a nonempty bounded list")

    identity_gaps = []
    if plan["source_commit"] != SOURCE_COMMIT:
        identity_gaps.append("source_revision_outside_reviewed_contract")
    if plan["resolved_mlx_commit"] is None:
        identity_gaps.append("resolved_mlx_revision_not_recorded")
    if plan["declared_backend"] in {"unknown", "not_run"}:
        identity_gaps.append("native_backend_not_recorded_or_not_run")

    rows, ids = [], set()
    for record in records:
        if type(record) is not dict or set(record) != RECORD_FIELDS:
            raise EvidenceError("invalid record schema")
        identifier = record["generation_id"]
        if (not isinstance(identifier, str)
                or re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", identifier) is None):
            raise EvidenceError("generation_id must be a bounded opaque ID")
        if identifier in ids:
            raise EvidenceError("generation_id must be unique")
        ids.add(identifier)
        _enum(record["api"], TASK_APIS | STREAM_APIS)
        _enum(record["consumer_end"],
              {"exhausted", "early_break", "consumer_cancelled", "not_observed"})
        retained = record["producer_task_retained"]
        if retained is not None and type(retained) is not bool:
            raise EvidenceError("producer_task_retained must be boolean or null")
        _enum(record["producer_task_join"], {"completed", "not_observed", "unknown"})
        _enum(record["mlx_default_stream_sync"], {"observed", "not_observed", "unknown"})
        info = record["final_info"]
        if info is not None:
            if type(info) is not dict or set(info) != {"stop_reason", "generation_token_count"}:
                raise EvidenceError("invalid final_info schema")
            _enum(info["stop_reason"], {"stop", "length", "cancelled"})
            count = info["generation_token_count"]
            if type(count) is not int or not 0 <= count <= MAX_COUNT:
                raise EvidenceError("token count must be a bounded nonnegative integer")

        conflicts, gaps = [], []
        task_api = record["api"] in TASK_APIS
        joined = record["producer_task_join"] == "completed"
        if retained is True and not task_api:
            conflicts.append("api_does_not_expose_producer_task_handle")
        if joined and retained is not True:
            conflicts.append("completed_join_without_retained_producer_handle")
        if joined and not task_api:
            conflicts.append("stream_only_api_does_not_expose_producer_join")
        coherent_join = joined and retained is True and task_api and not conflicts
        if not coherent_join:
            gaps.append("producer_cleanup_join_unresolved")
        if record["consumer_end"] == "not_observed":
            gaps.append("consumer_end_not_observed")
        if info is None:
            gaps.append("final_info_not_observed_not_a_failure_verdict")
        if record["mlx_default_stream_sync"] != "observed":
            gaps.append("mlx_default_stream_sync_not_independently_observed")
        rows.append({
            "generation_id": identifier,
            "api": record["api"],
            "consumer_end": record["consumer_end"],
            "join_declared_completed": joined,
            "cleanup_evidence": "caller_declared_join_only" if coherent_join else "unresolved",
            "declared_final_info": None if info is None else dict(info),
            "declared_mlx_default_stream_sync": record["mlx_default_stream_sync"],
            "conflicts": conflicts,
            "uncertainty": gaps,
        })
    return {
        "schema_version": 1,
        "status": "caller_evidence_records_audited_only",
        "engine_execution": "not_run_by_helper",
        "native_verification": "not_run",
        "evidence_authentication": "not_verified",
        "performance_claim": "not_assessed",
        "source_commit": plan["source_commit"],
        "resolved_mlx_commit": plan["resolved_mlx_commit"],
        "declared_backend": plan["declared_backend"],
        "identity_gaps": identity_gaps,
        "records": rows,
        "summary": {
            "records": len(rows),
            "join_declared_completed": sum(row["join_declared_completed"] for row in rows),
            "cleanup_unresolved": sum(row["cleanup_evidence"] == "unresolved" for row in rows),
            "records_with_conflicts": sum(bool(row["conflicts"]) for row in rows),
            "records_with_uncertainty": sum(bool(row["uncertainty"]) for row in rows),
            "final_info_observed": sum(row["declared_final_info"] is not None for row in rows),
        },
    }


def example() -> dict[str, Any]:
    """Return synthetic observations, never native evidence."""
    return {
        "schema_version": 1,
        "source_repository": "ml-explore/mlx-swift-lm",
        "source_commit": SOURCE_COMMIT,
        "resolved_mlx_commit": None,
        "declared_backend": "unknown",
        "records": [
            {"generation_id": "early-stop", "api": "generateTask",
             "consumer_end": "early_break", "producer_task_retained": True,
             "producer_task_join": "not_observed",
             "final_info": {"stop_reason": "cancelled", "generation_token_count": 1},
             "mlx_default_stream_sync": "not_observed"},
            {"generation_id": "joined-limit", "api": "generateTokensTask",
             "consumer_end": "exhausted", "producer_task_retained": True,
             "producer_task_join": "completed",
             "final_info": {"stop_reason": "length", "generation_token_count": 7},
             "mlx_default_stream_sync": "unknown"},
        ],
    }


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError("duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(_: str) -> Any:
    raise EvidenceError("nonfinite JSON value")


def _read(path: str) -> Any:
    if path == "-":
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    else:
        target = Path(path)
        if not target.is_file():
            raise EvidenceError("input must be a regular file")
        with target.open("rb") as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise EvidenceError("input exceeds bounded size")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=_nonfinite)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, "Invalid command line; use --help.\n")


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description=__doc__)
    parser.add_argument("input", nargs="?", help="UTF-8 JSON file, or -/omitted for stdin")
    parser.add_argument("--example", action="store_true", help="print synthetic input only")
    args = parser.parse_args(argv)
    if args.example:
        if args.input is not None:
            parser.error("--example takes no input")
        print(json.dumps(example(), indent=2))
        return 0
    try:
        result = audit(_read(args.input or "-"))
    except (OSError, ValueError, UnicodeError, RecursionError):
        print("Invalid evidence record; use --example and the bundled schema.", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
