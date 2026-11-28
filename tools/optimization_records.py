"""Prepare and validate public projections of one InferRSI result-delivery bundle."""

from __future__ import annotations

import hashlib
import json
import math
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

if __package__:
    from .evidence_archives import normalize_manifest
else:
    from evidence_archives import normalize_manifest

REPOSITORY = "InferMatrixLab/InferRSI"
RECORD_ID = r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}"
SOURCE_SCHEMA = "inferrsi.campaign-delivery"
SOURCE_NAMESPACE = "inferrsi.harness.optimization"
ARTIFACTS = {
    "model_config": "model-config.json",
    "execution": "trace/01-execution.json",
    "result": "trace/02-result.json",
    "prompt": "prompt.md",
}
OMISSIONS = {"unavailable", "withheld", "redacted"}
VERDICTS = {"PASS", "FAIL", "INCONCLUSIVE"}
EXECUTION_STATES = {
    "initialized", "ready", "running", "searching", "evaluating", "pending", "completed",
    "failed", "blocked", "interrupted", "rejected", "stopped", "cancelled", "timed_out",
    "timeout", "skipped", "not_run", "incomplete", "active", "prepared", "diagnosis",
    "diagnosed", "finalizing", "settled", "error", "aborted", "paused", "needs_baseline",
}
OUTCOMES = {"improved", "baseline_retained", "no_valid_candidate", "undetermined"}
STOP_CODES = {"fixed_round_budget_completed", "budget_exhausted", "early_stop"}
PHASES = {"baseline", "search", "final", "round"}
ATTEMPT_OUTCOMES = {"retained", "not_retained", "interrupted", "rejected"}
COMPLETION_STATES = {"completed", "incomplete"}
ASSESSMENT_STATES = {"assessed", "not_assessed"}
PROVENANCE_KINDS = {"retained_observation", "cached_state"}
VERIFICATION_STATES = {"verified", "unverified"}
GAP_CODES = {
    "ASSESSMENT_UNAVAILABLE", "EVIDENCE_UNVERIFIED", "GOAL_NOT_RECORDED", "NOT_RECORDED",
    "USAGE_COVERAGE", "identity_incomplete",
}
IDENTITY_FIELDS = {"agent_tool", "agent_version", "inferrsi_version", "inferrsi_commit"}
PUBLIC_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,127}(?:/[A-Za-z0-9][A-Za-z0-9_.+-]{0,127})?")
PUBLIC_ARCHIVE = re.compile(
    r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/releases/download/"
    r"[A-Za-z0-9_+.-]+/[A-Za-z0-9_+.-]+"
)
SECRET = re.compile(r"(?i)(?:gh[oprsu]_[A-Za-z0-9_]{8,}|github_pat_\w+|sk-[\w-]{8,})")
PRIVATE_LINE = re.compile(
    r"(?im)^(?:.*\b(?:authorization|api[ _-]?key|password|passwd|secret|token|"
    r"cookie|bearer)\s*(?:[:=]|\s).*)$"
)
PRIVATE_ADDRESS = re.compile(
    r"(?i)(?<![\w.-])(?:[a-z0-9-]+\.)+[a-z]{2,63}\b|"
    r"(?<![\w:])(?:[a-f0-9]{0,4}:){2,}[a-f0-9:.%]*(?![\w:])"
)
PRIVATE_KEY = re.compile(r"(?s)-----BEGIN [^-\n]*PRIVATE KEY-----.*?(?:-----END [^-\n]+-----|\Z)")
NETWORK_PATH = re.compile(r"(?<![\w\\])\\\\[^\s<>\"']+")
COMMIT = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def unique_fields(pairs):
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ValueError("Duplicate JSON object field")
    return fields


def require_fields(value, fields, description):
    if not isinstance(value, dict) or value.keys() != fields:
        raise ValueError(f"Invalid {description} fields")


def regular(path, *, directory=False):
    info = path.lstat()
    check = stat.S_ISDIR if directory else stat.S_ISREG
    if not check(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("Record paths must be regular files or directories without links")
    return path


def read_object(path):
    value = json.loads(regular(path).read_bytes())
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def utc(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + (
            "+00:00" if value.endswith("Z") else ""
        ))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (ValueError, OverflowError):
        return None


def iso(value):
    return value.isoformat().replace("+00:00", "Z") if value else None


def choice(value, options):
    return value if isinstance(value, str) and value in options else None


def valid_choice(value, options):
    return value is None or choice(value, options) is not None


def public_id(value):
    if not isinstance(value, str) or not PUBLIC_ID.fullmatch(value) or SECRET.search(value):
        return None
    # Require a public identifier, not a host, even within a namespaced model ID.
    if PRIVATE_ADDRESS.search(value) or re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", value):
        return None
    return value


def positive_int(value):
    return value if type(value) is int and value > 0 else None


def number(value):
    try:
        if type(value) in (int, float) and math.isfinite(value):
            return value
    except OverflowError:
        pass
    return None


def sanitize_prompt(text):
    from inferrsi.harness.records.evidence import sanitized_text

    text = PRIVATE_KEY.sub("[redacted-key]", text)
    text = PRIVATE_LINE.sub("[redacted-credential-line]", text)
    text = NETWORK_PATH.sub("[redacted-path]", text)
    text = sanitized_text(text, "", None)
    text = SECRET.sub("[redacted-credential]", text)
    return PRIVATE_ADDRESS.sub("[redacted-address]", text)


def config_snapshot(facts):
    agent = facts.get("agent_model") or {}
    model = facts.get("optimized_model") or {}
    return {
        "agent_model": {
            "id": public_id(agent.get("id")),
            "reasoning": choice(agent.get("reasoning"), {
                "minimal", "none", "low", "medium", "high", "xhigh", "max", "ultra", "adaptive",
            }),
            "temperature": number(agent.get("temperature")),
            "top_p": number(agent.get("top_p")),
            "top_k": positive_int(agent.get("top_k")),
        },
        "optimized_model": {
            **{key: public_id(model.get(key)) for key in ("id", "revision", "dtype",
                                                         "quantization", "backend")},
            **{key: positive_int(model.get(key)) for key in ("tp", "pp", "max_model_len")},
        },
    }


OMISSION_FIELDS = IDENTITY_FIELDS | {"raw_evidence", "metrics", "run_start"} | {
    f"{group}.{key}" for group, fields in config_snapshot({}).items() for key in fields
}


def execution_trace(result):
    execution = result["execution"]
    attempts = []
    for row in result["rounds"] or []:
        attempts.append({
            "ordinal": len(attempts) + 1,
            "phase": choice(row.get("phase"), PHASES)
            or ("search" if row.get("round") is not None else None),
            "status": choice(row.get("execution_state", row.get("status")), EXECUTION_STATES),
            "outcome": choice(row.get("selection_decision"), ATTEMPT_OUTCOMES),
            "verdict": choice(row.get("verdict"), VERDICTS),
        })
    # Native exports can retain prior final attempts separately from search rounds.
    for row in result.get("final_attempts", []):
        attempts.append({
            "ordinal": len(attempts) + 1,
            "phase": "final",
            "status": choice(row.get("execution_state", row.get("status")), EXECUTION_STATES),
            "outcome": None,
            "verdict": choice(row.get("verdict"), VERDICTS),
        })
    return {
        "namespace": execution["namespace"],
        "status": choice(execution.get("state"), EXECUTION_STATES),
        "started_at": iso(utc(execution.get("started_at"))),
        "ended_at": iso(utc(execution.get("ended_at"))),
        "completion": choice(result["completion"].get("status"), COMPLETION_STATES),
        "stop_code": choice(execution.get("stop_reason"), STOP_CODES),
        "attempts": attempts if result["rounds"] is not None or attempts else None,
    }


def metric_projection(metric):
    counts = metric.get("sample_counts") or {}
    comparison = metric.get("comparability") or {}
    return {
        **{key: public_id(metric.get(key)) for key in ("name", "unit", "statistic", "scope")},
        "phase": choice(metric.get("phase"), PHASES),
        "baseline": number(metric.get("baseline")),
        "candidate": number(metric.get("candidate")),
        "sample_counts": {
            key: counts[key] if type(counts.get(key)) is int and counts[key] >= 0 else None
            for key in ("baseline", "candidate")
        },
        "comparable": comparison.get("comparable")
        if type(comparison.get("comparable")) is bool else None,
    }


def result_trace(result, share_metrics):
    assessment = result["acceptance"]
    provenance = assessment.get("assessment_provenance") or {}
    final = result["final"] or {}
    execution = final.get("execution") or {}
    return {
        "outcome": choice(result["outcome"].get("kind"), OUTCOMES),
        "final_status": choice(execution.get("status", final.get("status")), EXECUTION_STATES),
        "assessment": choice(assessment.get("status"), ASSESSMENT_STATES),
        "verdict": choice(assessment.get("verdict"), VERDICTS),
        "provenance": choice(provenance.get("kind"), PROVENANCE_KINDS),
        "verification": choice(provenance.get("verification"), VERIFICATION_STATES),
        "delivery_accepted": assessment.get("delivery_accepted") is True,
        "gap_codes": sorted({choice(gap.get("code"), GAP_CODES) or "OTHER_SOURCE_GAP"
                             for gap in result["gaps"]}),
        "metrics": ([metric_projection(metric) for metric in result["metrics"]]
                    if share_metrics and result["metrics"] is not None else None),
    }


def archive_reference(delivery_dir, path):
    index = read_object(delivery_dir / "artifacts.json")
    matches = [item for item in index["artifacts"] if (
        item["id"] == index.get("archive_authority_ref")
        and item["location_kind"] == "source"
        and item["location"] == "results/artifacts.json"
        and item.get("integrity") == "verified"
    )]
    raw = regular(path).read_bytes()
    if len(matches) != 1 or sha256(raw) != matches[0]["sha256"]:
        raise ValueError("Archive manifest must match the verified source authority")
    archive = normalize_manifest(json.loads(raw))["archive"]
    if not PUBLIC_ARCHIVE.fullmatch(archive["url"]):
        raise ValueError("An approved public GitHub Release asset is required")
    return {key: archive[key] for key in ("id", "url", "sha256")}


def publish_files(parent, name, files):
    """Atomically expose the complete directory and preserve a colliding destination."""
    from inferrsi.apps.storage.archive import publish_directory

    regular(parent, directory=True)
    destination = parent / name
    with TemporaryDirectory(prefix=".record-", dir=parent) as temporary:
        staging = Path(temporary)
        for relative, content in files.items():
            path = staging / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        publish_directory(staging, destination)
    return destination


def prepare_record(delivery_dir, output_root, *, facts, prompt=None, omit_prompt=False,
                   acceptance_issue=None, archive_manifest=None):
    from inferrsi.apps.delivery import read_bundle

    result = read_bundle(delivery_dir)
    if result["execution"].get("namespace") != SOURCE_NAMESPACE:
        raise ValueError("Select a v1 result-delivery bundle from a native campaign")
    if acceptance_issue is not None and positive_int(acceptance_issue) is None:
        raise ValueError("Expected a public InferRSI acceptance issue number")
    if omit_prompt and prompt is not None:
        raise ValueError("Choose a prompt file or withhold the prompt")
    revision = facts.get("inferrsi_commit")
    if not isinstance(revision, str) or not COMMIT.fullmatch(revision):
        revision = None
    identity = {
        "agent_tool": public_id(facts.get("agent_tool")),
        "agent_version": public_id(facts.get("agent_version")),
        "inferrsi_version": public_id(facts.get("inferrsi_version")),
        "inferrsi_commit": revision,
    }
    archive = archive_reference(delivery_dir, archive_manifest) if archive_manifest else None
    config = config_snapshot(facts)
    execution = execution_trace(result)
    outcome = result_trace(result, acceptance_issue is not None)
    files = {
        ARTIFACTS["model_config"]: json_bytes(config),
        ARTIFACTS["execution"]: json_bytes(execution),
        ARTIFACTS["result"]: json_bytes(outcome),
    }
    if prompt and (content := sanitize_prompt(prompt)).strip():
        files[ARTIFACTS["prompt"]] = content.encode("utf-8")
    unavailable = {key: "unavailable" for key, value in identity.items() if value is None}
    for group, fields in config.items():
        unavailable.update({f"{group}.{key}": "unavailable" for key, value in fields.items()
                            if value is None})
    if not archive:
        unavailable["raw_evidence"] = "unavailable"
    if outcome["metrics"] is None:
        unavailable["metrics"] = "withheld" if result["metrics"] is not None else "unavailable"
    captured = datetime.now(timezone.utc)
    started = utc(result["execution"].get("started_at"))
    if started is None:
        unavailable["run_start"] = "unavailable"
    artifacts = [
        {"role": role, "path": name, "sha256": sha256(files[name]), "availability": "included"}
        if name in files else {
            "role": role, "path": None, "sha256": None,
            "availability": "withheld" if omit_prompt else "unavailable",
        }
        for role, name in ARTIFACTS.items()
    ]
    stamp = (started or captured).strftime("%Y%m%dT%H%M%SZ")
    for _ in range(8):
        record_id = f"{stamp}-{uuid4().hex[:12]}"
        manifest = {
            "schema_version": 1, "record_id": record_id, "captured_at": iso(captured),
            "run_started_at": iso(started), "timestamp_basis": "run_start" if started
            else "first_capture",
            **identity, "run_facts_provenance": "user_reported",
            "execution_status": execution["status"], "assessment_verdict": outcome["verdict"],
            "source_format": SOURCE_SCHEMA, "source_version": 1,
            "acceptance_issue": acceptance_issue, "archive": archive, "artifacts": artifacts,
            "omissions": unavailable,
        }
        if (output_root / record_id).exists():
            continue
        try:
            return publish_files(
                output_root, record_id, {**files, "record.json": json_bytes(manifest)}
            )
        except FileExistsError:
            continue
    raise ValueError("Unable to allocate an unused record ID")


def validate_config(config):
    require_fields(config, {"agent_model", "optimized_model"}, "model config")
    if any(not isinstance(group, dict) for group in config.values()):
        raise ValueError("Invalid model config group")
    if config != config_snapshot(config):
        raise ValueError("Invalid model config fields or values")


def validate_execution(execution):
    require_fields(execution, {
        "namespace", "status", "started_at", "ended_at", "completion", "stop_code", "attempts",
    }, "execution trace")
    if (execution["namespace"] != SOURCE_NAMESPACE
            or not valid_choice(execution["status"], EXECUTION_STATES)
            or not valid_choice(execution["completion"], COMPLETION_STATES)
            or not valid_choice(execution["stop_code"], STOP_CODES)
            or any(execution[key] is not None and utc(execution[key]) is None
                   for key in ("started_at", "ended_at"))):
        raise ValueError("Invalid execution trace values")
    attempts = execution["attempts"]
    if attempts is None:
        return
    if not isinstance(attempts, list):
        raise ValueError("Invalid execution attempts")
    for ordinal, attempt in enumerate(attempts, 1):
        require_fields(attempt, {"ordinal", "phase", "status", "outcome", "verdict"}, "attempt")
        if (positive_int(attempt["ordinal"]) != ordinal
                or not valid_choice(attempt["phase"], PHASES)
                or not valid_choice(attempt["status"], EXECUTION_STATES)
                or not valid_choice(attempt["outcome"], ATTEMPT_OUTCOMES)
                or not valid_choice(attempt["verdict"], VERDICTS)):
            raise ValueError("Invalid execution attempt values")


def validate_result(result):
    require_fields(result, {
        "outcome", "final_status", "assessment", "verdict", "provenance", "verification",
        "delivery_accepted", "gap_codes", "metrics",
    }, "result trace")
    if (not valid_choice(result["outcome"], OUTCOMES)
            or not valid_choice(result["final_status"], EXECUTION_STATES)
            or not valid_choice(result["assessment"], ASSESSMENT_STATES)
            or not valid_choice(result["verdict"], VERDICTS)
            or not valid_choice(result["provenance"], PROVENANCE_KINDS)
            or not valid_choice(result["verification"], VERIFICATION_STATES)
            or type(result["delivery_accepted"]) is not bool):
        raise ValueError("Invalid result trace values")
    gap_codes = result["gap_codes"]
    if not isinstance(gap_codes, list) or any(
        choice(value, GAP_CODES | {"OTHER_SOURCE_GAP"}) is None for value in gap_codes
    ):
        raise ValueError("Invalid result gap codes")
    metrics = result["metrics"]
    if metrics is None:
        return
    if not isinstance(metrics, list):
        raise ValueError("Invalid result metrics")
    for metric in metrics:
        if not isinstance(metric, dict) or not isinstance(metric.get("sample_counts"), dict):
            raise ValueError("Invalid result metric")
        projected = metric_projection({
            **metric, "comparability": {"comparable": metric.get("comparable")},
        })
        if metric != projected:
            raise ValueError("Invalid result metric fields or values")


PROJECTION_VALIDATORS = {
    "model_config": validate_config,
    "execution": validate_execution,
    "result": validate_result,
}


def load_record(directory):
    """Return the exact validated public bytes for staging, or fail without copying anything."""
    regular(directory, directory=True)
    record_id = directory.name
    if not re.fullmatch(RECORD_ID, record_id):
        raise ValueError("Invalid record directory name")
    manifest_bytes = regular(directory / "record.json").read_bytes()
    manifest = json.loads(manifest_bytes, object_pairs_hook=unique_fields)
    require_fields(manifest, IDENTITY_FIELDS | {
        "schema_version", "record_id", "captured_at", "run_started_at", "timestamp_basis",
        "run_facts_provenance", "execution_status", "assessment_verdict", "source_format",
        "source_version", "acceptance_issue", "archive", "artifacts", "omissions",
    }, "record manifest")
    if (type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1
            or manifest["record_id"] != record_id or manifest["source_format"] != SOURCE_SCHEMA
            or type(manifest["source_version"]) is not int or manifest["source_version"] != 1):
        raise ValueError("Invalid record manifest identity or version")
    captured, started = utc(manifest["captured_at"]), utc(manifest["run_started_at"])
    purpose = "run_start" if started else "first_capture"
    if (captured is None or (manifest["run_started_at"] is not None and started is None)
            or manifest["timestamp_basis"] != purpose
            or not record_id.startswith((started or captured).strftime("%Y%m%dT%H%M%SZ") + "-")):
        raise ValueError("Invalid record timestamp basis")
    omissions = manifest["omissions"]
    if (not isinstance(omissions, dict) or not omissions.keys() <= OMISSION_FIELDS
            or any(choice(value, OMISSIONS) is None for value in omissions.values())):
        raise ValueError("Invalid record omissions")
    for key in IDENTITY_FIELDS:
        value = manifest[key]
        if ((value is None and key not in omissions)
                or (value is not None and public_id(value) is None)):
            raise ValueError("Invalid or undocumented run provenance")
    revision = manifest["inferrsi_commit"]
    if revision is not None and not COMMIT.fullmatch(revision):
        raise ValueError("Invalid InferRSI commit")
    if manifest["run_facts_provenance"] != "user_reported":
        raise ValueError("Invalid run facts provenance")
    issue = manifest["acceptance_issue"]
    if issue is not None and positive_int(issue) is None:
        raise ValueError("Invalid acceptance issue reference")
    if (archive := manifest["archive"]) is not None:
        if (not isinstance(archive, dict)
                or set(archive) != {"id", "url", "sha256"}
                or public_id(archive["id"]) is None
                or not isinstance(archive["url"], str)
                or not PUBLIC_ARCHIVE.fullmatch(archive["url"])
                or not isinstance(archive["sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", archive["sha256"])):
            raise ValueError("Invalid public archive reference")
    if not valid_choice(manifest["execution_status"], EXECUTION_STATES):
        raise ValueError("Invalid execution status")
    if not valid_choice(manifest["assessment_verdict"], VERDICTS):
        raise ValueError("Invalid recorded verdict")
    entries = manifest["artifacts"]
    if not isinstance(entries, list):
        raise ValueError("Invalid record artifacts")
    for row in entries:
        require_fields(row, {"role", "path", "sha256", "availability"}, "artifact")
    if [row["role"] for row in entries] != list(ARTIFACTS):
        raise ValueError("Artifact roles are missing, out of order, or duplicated")
    regular(directory / "trace", directory=True)
    files = {"record.json": manifest_bytes}
    for row in entries:
        role, relative = row["role"], row["path"]
        if role == "prompt" and relative is None:
            if choice(row["availability"], OMISSIONS) is None or row["sha256"] is not None:
                raise ValueError("A missing prompt requires an explicit gap")
            continue
        if relative != ARTIFACTS[role] or row["availability"] != "included":
            raise ValueError("Unexpected artifact path or availability")
        raw = regular(directory / relative).read_bytes()
        if sha256(raw) != row["sha256"]:
            raise ValueError("Record artifact SHA-256 mismatch")
        if role == "prompt":
            raw.decode("utf-8")
        else:
            projection = json.loads(raw, object_pairs_hook=unique_fields)
            PROJECTION_VALIDATORS[role](projection)
            if role == "result" and projection["metrics"] is not None and issue is None:
                raise ValueError("Result metrics require a public acceptance issue")
        files[relative] = raw
    children = {child.name for child in directory.iterdir()}
    trace_files = {f"trace/{child.name}" for child in (directory / "trace").iterdir()}
    if (children - {"trace"}) | trace_files != set(files):
        raise ValueError("The record contains unlisted files or directories")
    return manifest, files
