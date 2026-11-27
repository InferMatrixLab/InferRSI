"""intake/v1: host-independent task intake records for missing-field confirmation.

A card, a numbered text fallback and an optional check-in interview all write the
same record. The record separates what the user stated (``confirmed``), what a
card answer proposes (``proposed``), what stays unknown (``unknown``) and what
conflicts (``conflicting``). ``evaluate`` selects the questions that unblock the
next stage, derives ``allowed_next`` and never authenticates acceptance
thresholds: a proposal kept in a record does not freeze a gate.

The contract performs no I/O. Mapped numeric values use the task-input validator. Callers in
``inferrsi.apps.cli.task_intake`` load the versioned spec and record, then call these
pure functions. ``source`` is declared by the caller and is not authenticated.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math

from ...harness.evaluator import validate_quality_unit
from . import task_input

SCHEMA_VERSION = 1
QUALITY_UNIT = "protocol.quality_unit"

STAGES = (
    "read_only_preparation",
    "baseline_measurement",
    "candidate_search",
    "service_execution",
    "device_execution",
)
BLOCKING_STAGES = STAGES[1:]

MAP_TARGETS = ("task-input/v1", "campaign-protocol", "session-protocol",
               "summary-only", "day0-spec")

STATUSES = ("confirmed", "proposed", "assumed", "unknown", "conflicting",
            "stale", "superseded")
SETTLED = ("confirmed", "proposed")
BLOCKING = ("unknown", "assumed", "conflicting", "stale", "superseded")

ACCEPTANCE = "acceptance."
AUTHORITATIVE = ("issue", "frozen_gate")
REFERENCE = "acceptance.reference"

_QUESTION = "q:"
BRIEF_QUESTION_PREFIX = "q:task_brief:"


class IntakeError(ValueError):
    """A record, spec or answer is rejected; ``code`` names the recorded reason."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _field_paths(spec: dict) -> dict[str, dict]:
    return {field["path"]: field for field in spec["fields"]}


def validate_spec(spec: object) -> list[dict]:
    """Return field-level problems in a packaged intake spec, in spec order."""
    problems: list[dict] = []

    def bad(path: str, message: str) -> None:
        problems.append({"field": path, "message": message})

    if not isinstance(spec, dict):
        return [{"field": "$", "message": "must be an object"}]
    if spec.get("schema_version") != SCHEMA_VERSION:
        bad("schema_version", f"must be {SCHEMA_VERSION}")
    if not isinstance(spec.get("task"), str) or not spec["task"].strip():
        bad("task", "must be a non-empty string")
    fields = spec.get("fields")
    if not isinstance(fields, list) or not fields:
        bad("fields", "must be a non-empty array")
        return problems
    seen: set[str] = set()
    for index, field in enumerate(fields):
        where = f"fields[{index}]"
        if not isinstance(field, dict):
            bad(where, "must be an object")
            continue
        path = field.get("path")
        if not isinstance(path, str) or not path.strip():
            bad(f"{where}.path", "must be a non-empty string")
        elif path in seen:
            bad(f"{where}.path", f"duplicates {path}")
        else:
            seen.add(path)
        if field.get("maps_to") not in MAP_TARGETS:
            bad(f"{where}.maps_to", f"must be one of {', '.join(MAP_TARGETS)}")
        if (field.get("maps_to") == "task-input/v1" and field.get("type") in ("integer", "number")
                and isinstance(path, str) and path not in task_input.BY_PATH):
            bad(f"{where}.path", f"{path} is not a task-input/v1 field")
        if not isinstance(field.get("question"), str) or not field["question"].strip():
            bad(f"{where}.question", "must be a non-empty string")
        batch = field.get("batch", 1)
        if type(batch) is not int or batch < 1:
            bad(f"{where}.batch", "must be a positive integer")
        required = field.get("required_before", [])
        if not isinstance(required, list) or any(
            stage not in BLOCKING_STAGES for stage in required
        ):
            bad(f"{where}.required_before",
                f"must list stages from {', '.join(BLOCKING_STAGES)}")
        depends = field.get("depends_on", [])
        if not isinstance(depends, list) or any(not isinstance(dep, str) for dep in depends):
            bad(f"{where}.depends_on", "must be an array of field paths")
        options = field.get("options", [])
        if not isinstance(options, list) or any(
            not isinstance(option, dict) or "value" not in option for option in options
        ):
            bad(f"{where}.options", "must be an array of {value, hint} objects")
        if "user_choice" in field and type(field["user_choice"]) is not bool:
            bad(f"{where}.user_choice", "must be a boolean")
        when = field.get("required_when")
        if when is not None and (
            not isinstance(when, dict) or not isinstance(when.get("field"), str)
            or "equals" not in when
        ):
            bad(f"{where}.required_when", "must be {field, equals}")
    for field in fields:
        if not isinstance(field, dict):
            continue
        when = field.get("required_when")
        if isinstance(when, dict) and when.get("field") not in seen:
            bad(f"{field.get('path', '?')}.required_when",
                f"names unknown field {when.get('field')}")
        for dep in field.get("depends_on", []) if isinstance(field.get("depends_on"), list) else ():
            if dep not in seen:
                bad(f"{field.get('path', '?')}.depends_on", f"names unknown field {dep}")
    return problems


def load_spec(spec: object) -> dict:
    """Validate and return the spec; raise ``IntakeError('invalid_spec')``."""
    problems = validate_spec(spec)
    if problems:
        first = problems[0]
        raise IntakeError("invalid_spec", f"{first['field']}: {first['message']}")
    return spec


def new_record(task: str, *, record_id: str, primary_source: str = "prompt") -> dict:
    """An empty intake record for ``task`` with a confirmed primary task."""
    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": record_id,
        "revision": 1,
        "task": task,
        "primary_task": {"value": task, "source": primary_source, "status": "confirmed"},
        "phase": "intake",
        "fields": {},
        "open_questions": [],
        "blockers": [],
        "conflicts": [],
        "allowed_next": ["read_only_preparation"],
        "execution": "not started",
    }


def validate_record(record: object, spec: dict) -> list[dict]:
    """Return field-level problems in a record against its spec."""
    problems: list[dict] = []

    def bad(field: str, message: str) -> None:
        problems.append({"field": field, "message": message})

    if not isinstance(record, dict):
        return [{"field": "$", "message": "must be an object"}]
    if record.get("schema_version") != SCHEMA_VERSION:
        bad("schema_version", f"must be {SCHEMA_VERSION}")
    if record.get("task") != spec["task"]:
        bad("task", f"must equal the spec task {spec['task']}")
    revision = record.get("revision")
    if type(revision) is not int or revision < 1:
        bad("revision", "must be a positive integer")
    if not isinstance(record.get("open_questions", []), list):
        bad("open_questions", "must be a list of issued questions")
    primary = record.get("primary_task")
    if not isinstance(primary, dict) or primary.get("status") not in STATUSES:
        bad("primary_task", "must carry a value, source and known status")
    elif primary.get("value") != record.get("task"):
        bad("primary_task.value", f"must be {record.get('task')}")
    fields = record.get("fields")
    if not isinstance(fields, dict):
        bad("fields", "must be an object")
        return problems
    snapshot = record.get("selected_gate")
    if snapshot is not None and not (
        isinstance(snapshot, dict) and isinstance(snapshot.get("reference"), str)
        and isinstance(snapshot.get("values"), dict)
    ):
        bad("selected_gate", "must contain the selected reference and its acceptance values")
    known = _field_paths(spec)
    for path, entry in fields.items():
        if path not in known:
            bad(path, "is not a field of this task spec")
            continue
        if not isinstance(entry, dict):
            bad(path, "must be an object")
            continue
        if entry.get("status") not in STATUSES:
            bad(path, f"status must be one of {', '.join(STATUSES)}")
        if not isinstance(entry.get("source"), str):
            bad(path, "source must be a string")
        value = entry.get("value")
        # Reconciliation can reopen an old textual placeholder, including a blank unit.
        if entry.get("status") in SETTLED and not (path == QUALITY_UNIT and isinstance(value, str)):
            try:
                _typed_value(known[path], value)
            except IntakeError as exc:
                bad(path, str(exc))
        if type(entry.get("asked", False)) is not bool:
            bad(path, "asked must be a boolean")
    return problems


def _check(record: dict, spec: dict) -> None:
    problems = validate_record(record, spec)
    if problems:
        first = problems[0]
        raise IntakeError("invalid_record", f"{first['field']}: {first['message']}")


def _entry(record: dict, path: str) -> dict:
    return record["fields"].get(path) or {"value": None, "source": "unknown",
                                          "status": "unknown", "asked": False}


def _settled(record: dict, path: str) -> bool:
    return _entry(record, path).get("status") in SETTLED


def _typed_value(field: dict, value: object) -> object:
    kind = field.get("type", "text")
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise IntakeError("invalid_value", f"{field['path']} must be a finite number")
        try:
            number = float(value)
        except (OverflowError, ValueError) as exc:
            raise IntakeError("invalid_value", f"{field['path']} must be a finite number") from exc
        if not math.isfinite(number):
            raise IntakeError("invalid_value", f"{field['path']} must be a finite number")
        return number
    if kind == "integer":
        if type(value) is int:
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                pass
        raise IntakeError("invalid_value", f"{field['path']} must be an integer")
    if kind == "choice":
        allowed = [option["value"] for option in field.get("options", [])]
        if value not in allowed:
            raise IntakeError(
                "invalid_value", f"{field['path']} must be one of {', '.join(allowed)}")
        return value
    if not isinstance(value, str) or not value.strip():
        raise IntakeError("invalid_value", f"{field['path']} must be a non-empty string")
    return value


def _coerce(field: dict, value: object) -> object:
    typed = _typed_value(field, value)
    if field["path"] == QUALITY_UNIT:
        try:
            validate_quality_unit(typed)
        except ValueError as error:
            raise IntakeError("invalid_value", f"{field['path']} must specify a unit") from error
    if field["maps_to"] == "task-input/v1" and field.get("type") in ("integer", "number"):
        mapped = task_input.BY_PATH[field["path"]]
        problem = task_input.field_value_problem(mapped, typed)
        if problem:
            raise IntakeError("invalid_value", f"{mapped.path} {problem}")
    return typed


def _card_source(path: str, source: str) -> bool:
    # Older settled answers retain their field-only provenance.
    return source.split(":", 3)[:3] == ["answer", "q", path]


def _user_source(path: str, source: str) -> bool:
    return source in ("prompt", "grilling_brief") or _card_source(path, source)


def selected_reference(record: dict) -> str | None:
    entry = _entry(record, REFERENCE)
    if entry["status"] == "confirmed" and _user_source(REFERENCE, entry.get("source", "")):
        return entry["value"]
    return None


def _status_for(field: dict, source: str, *, bound: bool = False) -> str:
    path = field["path"]
    from_user = _user_source(path, source)
    if path == REFERENCE:
        return "confirmed" if from_user else "assumed"
    if path.startswith(ACCEPTANCE):
        if bound:
            return "confirmed"
        return "proposed" if from_user else "assumed"
    if field.get("user_choice") and not from_user:
        return "assumed"
    return "confirmed"


def _bound_value(record: dict, path: str, entry: dict) -> bool:
    reference = selected_reference(record)
    if not reference or entry.get("authority_reference") != reference:
        return False
    snapshot = record.get("selected_gate")
    if isinstance(snapshot, dict) and snapshot.get("reference") == reference:
        return (entry["source"] == "frozen_gate"
                and snapshot["values"].get(path) == entry.get("value"))
    return entry["source"] == "issue"


def _bound_service_quality(record: dict) -> dict | None:
    launch = record.get("campaign_launch", {})
    if not isinstance(launch, dict):
        raise IntakeError("invalid_record", "campaign_launch must be an object")
    if launch.get("evaluation_mode") != "service_reuse":
        return None
    try:
        quality = launch["evaluation_settings"]["quality"]
        if (quality["mode"] not in ("absolute", "baseline_comparison")
                or quality["direction"] not in ("maximize", "minimize")
                or not isinstance(quality["key"], str)
                or not isinstance(quality.get("threshold" if quality["mode"] == "absolute"
                                              else "tolerance"), (int, float))):
            raise ValueError
    except (TypeError, KeyError, ValueError) as exc:
        raise IntakeError("invalid_record", "Invalid bound service quality conditions") from exc
    return quality


def reconcile_record(record: dict, spec: dict) -> dict:
    """Recheck provenance, including older records that trusted the source label alone."""
    _check(record, spec)
    updated = copy.deepcopy(record)
    fields = _field_paths(spec)
    reopened = False
    for path, entry in updated["fields"].items():
        if entry["status"] in ("confirmed", "proposed", "assumed"):
            field = fields[path]
            if path == QUALITY_UNIT or field.get("type") in ("integer", "number"):
                try:
                    _coerce(field, entry.get("value"))
                except IntakeError:
                    updated["fields"][path] = {"value": None, "status": "unknown",
                                               "source": entry["source"],
                                               "rejected_value": entry.get("value")}
                    reopened = True
                    continue
            bound = _bound_value(record, path, entry)
            entry["status"] = _status_for(field, entry["source"], bound=bound)
    quality = _bound_service_quality(updated)
    comparator = _entry(updated, "protocol.quality_comparator")
    if quality and quality["mode"] == "baseline_comparison" and comparator["status"] in SETTLED:
        expected = "at_least" if quality["direction"] == "maximize" else "at_most"
        if comparator["value"] != expected:
            updated["fields"]["protocol.quality_comparator"] = {
                "value": None, "source": comparator["source"], "status": "conflicting",
                "candidates": [{"value": comparator["value"], "source": comparator["source"]},
                               {"value": expected, "source": "service quality direction"}],
            }
            reopened = True
    if reopened:
        _bump(updated, updated["revision"] + 1)
    return updated


def _bump(record: dict, next_revision: int) -> None:
    record.pop("brief_decision", None)
    record.pop("campaign_launch", None)
    record["revision"] = next_revision


def _rank(status: str) -> int:
    return {"confirmed": 2, "proposed": 1}.get(status, 0)


def set_fields(record: dict, spec: dict, values: dict, *, source: str) -> dict:
    """Merge stated values into a copy of ``record``; raise on invalid fields/values."""
    if source.startswith("answer:"):
        raise IntakeError("invalid_source", "Use intake answer to record a user reply")
    if not isinstance(values, dict):
        raise IntakeError("invalid_record", "values must be a mapping")
    updated = reconcile_record(record, spec)
    fields = _field_paths(spec)
    reference = selected_reference(updated)
    changed = False
    revision = updated["revision"]
    for path, raw in values.items():
        if path not in fields:
            raise IntakeError("invalid_field", f"{path} is not a field of {spec['task']}")
        value = _coerce(fields[path], raw)
        entry = {"value": value, "source": source}
        if path.startswith(ACCEPTANCE) and path != REFERENCE and source in AUTHORITATIVE:
            entry["authority_reference"] = (values.get(REFERENCE) if source == "issue"
                                            else reference)
        bound = _bound_value(updated, path, entry)
        if not bound:
            entry.pop("authority_reference", None)
        status = _status_for(fields[path], source, bound=bound)
        entry["status"] = status
        current = updated["fields"].get(path)
        if (current and current["status"] == "unknown" and current.get("asked")
                and status == "assumed"):
            continue
        if current is not None and not current.get("candidates") and (
            current.get("value") == value
        ):
            if _rank(status) <= _rank(current.get("status", "unknown")):
                continue
            updated["fields"][path] = entry
            changed = True
            continue
        if (current is not None and current.get("status") == "conflicting"
                and isinstance(current.get("candidates"), list)):
            if all(item["value"] != value for item in current["candidates"]):
                current["candidates"].append({"value": value, "source": source})
                changed = True
            continue
        if (current is not None and current.get("status") not in (None, "unknown")
                and current.get("value") is not None and current.get("value") != value):
            disagrees_with_answer = bound and _card_source(path, current["source"])
            if _rank(status) > _rank(current["status"]) and not disagrees_with_answer:
                updated["fields"][path] = entry
                changed = True
            elif _rank(status) < _rank(current["status"]):
                continue
            else:
                updated["fields"][path] = {"value": None, "source": source,
                                           "status": "conflicting",
                                           "candidates": [
                                               {"value": current["value"],
                                                "source": current.get("source", "unknown")},
                                               {"value": value, "source": source},
                                           ]}
                changed = True
            continue
        if current is not None and current.get("asked") and status != "assumed":
            entry["asked"] = True
        updated["fields"][path] = entry
        changed = True
    if changed:
        _bump(updated, revision + 1)
    return updated


def _applicable(record: dict, field: dict) -> bool:
    for dep in field.get("depends_on", []):
        if not _settled(record, dep):
            return False
    when = field.get("required_when")
    if isinstance(when, dict):
        entry = _entry(record, when["field"])
        if entry.get("value") != when.get("equals"):
            return False
    return True


def _question(record: dict, field: dict) -> dict:
    snapshot = {"__primary_task__": record["primary_task"]["value"]}
    dependencies = list(field.get("depends_on", []))
    when = field.get("required_when")
    if isinstance(when, dict):
        dependencies.append(when["field"])
    for dep in dependencies:
        snapshot[dep] = _entry(record, dep).get("value")
    options = field.get("options", [])
    entry = _entry(record, field["path"])
    if entry["status"] == "assumed":
        suggestion = {"value": entry["value"], "hint": f"suggested by {entry['source']}"}
        options = [suggestion, *(item for item in options if item["value"] != entry["value"])]
        snapshot["__suggestion__"] = entry["value"]
    if entry.get("status") == "conflicting" and isinstance(entry.get("candidates"), list):
        options = [{"value": item["value"], "hint": f"from {item['source']}"}
                   for item in entry["candidates"]]
    card = {
        "field": field["path"],
        "batch": field.get("batch", 1),
        "question": field["question"],
        "options": options,
        "fallback": "unknown",
        "depends_on": snapshot,
    }
    # Keep a batch sibling's token across unrelated edits. A reissued card gets
    # the new revision even if a previous set of choices eventually comes back.
    issued = record["revision"]
    for prior in record.get("open_questions", []):
        if isinstance(prior, dict) and all(prior.get(key) == value for key, value in card.items()):
            issued = prior.get("issued_revision", issued)
            break
    identity = _canonical([record["record_id"], issued, card])
    digest = hashlib.sha256(identity.encode()).hexdigest()
    return {**card, "id": f"{_QUESTION}{field['path']}:{digest}", "issued_revision": issued}


def _frozen_conflicts(record: dict, spec: dict, frozen: dict | None) -> list[dict]:
    if not frozen:
        return []
    conflicts = []
    for field in spec["fields"]:
        path = field["path"]
        if not path.startswith(ACCEPTANCE) or path not in frozen:
            continue
        entry = _entry(record, path)
        if entry.get("value") is None:
            continue
        if _canonical(entry["value"]) != _canonical(frozen[path]):
            conflicts.append({
                "field": path,
                "message": "record value disagrees with the frozen gate record",
                "record_value": entry["value"],
                "frozen_value": frozen[path],
            })
    return conflicts


def _service_quality_line(quality: dict, unit: str) -> str:
    metric = quality["key"]
    higher = quality["direction"] == "maximize"
    direction = "higher is better" if higher else "lower is better"
    operator = ">=" if higher else "<="
    if quality["mode"] == "absolute":
        limit = str(quality["threshold"]).removesuffix(".0")
        return f"{metric} {operator} {limit} {unit} (absolute threshold; {direction})"
    tolerance = str(quality["tolerance"]).removesuffix(".0")
    sign = "-" if higher else "+"
    if unit in ("%", "percent"):
        unit = "percentage point" if quality["tolerance"] == 1 else "percentage points"
    return (f"{metric} {operator} baseline {metric} {sign} {tolerance} {unit} "
            f"(baseline comparison; {direction}; reference: retained baseline score "
            "for the current comparison epoch)")


def _performance_brief(record: dict, spec: dict) -> dict:
    values = {field["path"]: _coerce(field, record["fields"][field["path"]]["value"])
              for field in spec["fields"] if _applicable(record, field)}
    metric = values["acceptance.metric_key"]
    target = str(values["protocol.target_value"]).removesuffix(".0")
    if values["protocol.target_kind"] == "relative_improvement_pct":
        performance = f"{metric}: improve by at least {target}% over the pinned baseline"
    else:
        comparison = "<=" if values["acceptance.direction"] == "minimize" else ">="
        performance = f"{metric} {comparison} {target} {values['acceptance.metric_unit']}"
    operators = {"at_least": ">=", "at_most": "<=", "equal": "="}
    operator = operators[values["protocol.quality_comparator"]]
    limit = str(values["protocol.quality_limit"]).removesuffix(".0")
    quality = (f"{values['protocol.quality_metric']} {operator} "
               f"{limit} {values['protocol.quality_unit']}")
    brief = {"record_id": record["record_id"], "revision": record["revision"],
             "task": record["task"], "performance_target": performance, "quality_gate": quality,
             "benchmark": values["protocol.quality_benchmark"], "conditions": values}
    snapshot = record.get("selected_gate")
    if snapshot and "sha256" in snapshot:
        brief["frozen_gate_sha256"] = snapshot["sha256"]
    if "campaign_launch" in record:
        brief["campaign_launch"] = record["campaign_launch"]
        service_quality = _bound_service_quality(record)
        if service_quality:
            brief["quality_gate"] = _service_quality_line(
                service_quality, values["protocol.quality_unit"])
            values["protocol.quality_mode"] = service_quality["mode"]
            values["protocol.quality_direction"] = service_quality["direction"]
            if service_quality["mode"] == "baseline_comparison":
                values["protocol.quality_baseline_tolerance"] = values.pop("protocol.quality_limit")
                values["protocol.quality_reference"] = (
                    "retained baseline score for the current comparison epoch")
    elif values["protocol.comparison"] == "service_reuse":
        brief["quality_gate_status"] = "provisional"
        brief["quality_gate"] = (
            f"Provisional service quality inputs: {values['protocol.quality_metric']}, "
            f"{limit} {values['protocol.quality_unit']}. Prepare the executable plan to show "
            "whether this value is an absolute threshold or a tolerance against the baseline.")
    brief["id"] = BRIEF_QUESTION_PREFIX + hashlib.sha256(_canonical(brief).encode()).hexdigest()
    return brief


def _brief_question(brief: dict) -> dict:
    return {"id": brief["id"], "field": "task_brief",
            "question": "After reviewing the complete task brief, do you approve this revision?",
            "options": [{"value": "approve", "hint": "accept the brief as shown"},
                        {"value": "revise", "hint": "request changes and keep execution blocked"}],
            "fallback": "unknown"}


def evaluate(record: dict, spec: dict, *, frozen: dict | None = None) -> dict:
    """Return the questions, blockers, conflicts and allowed next steps.

    Questions are the fields of the lowest missing ``batch`` that still apply;
    a conflicting field is asked before anything else so the user can resolve
    it. A field answered with ``unknown`` is not asked again: it blocks its
    stage until a later source states it.
    """
    record = reconcile_record(record, spec)
    fields = _field_paths(spec)
    conflicts = _frozen_conflicts(record, spec, frozen)
    question_fields = []
    for field in spec["fields"]:
        if not _applicable(record, field):
            continue
        entry = _entry(record, field["path"])
        if entry.get("status") == "conflicting":
            question_fields.append(field)
    if not question_fields:
        missing = []
        for field in spec["fields"]:
            if not _applicable(record, field):
                continue
            entry = _entry(record, field["path"])
            if entry["status"] == "assumed" or (
                entry["status"] == "unknown" and not entry.get("asked")
            ):
                missing.append(field)
        if missing:
            lowest = min(field.get("batch", 1) for field in missing)
            question_fields = [field for field in missing if field.get("batch", 1) == lowest]
    questions = [_question(record, field) for field in question_fields]
    blockers = []
    for stage in BLOCKING_STAGES:
        blocked_by = []
        for path, entry in ((path, _entry(record, path)) for path in fields):
            field = fields[path]
            if stage not in field.get("required_before", []):
                continue
            if not _applicable(record, field):
                continue
            status = entry.get("status")
            if status in BLOCKING or (
                stage == "candidate_search" and path.startswith(ACCEPTANCE)
                and status != "confirmed"
            ):
                blocked_by.append({"field": path, "status": status})
        if blocked_by:
            blockers.append({"stage": stage, "blocked_by": blocked_by})
    if conflicts:
        entries = [{"field": item["field"], "status": "conflicting"} for item in conflicts]
        existing = next((item for item in blockers if item["stage"] == "candidate_search"),
                        None)
        if existing is None:
            blockers.append({"stage": "candidate_search", "blocked_by": entries})
        else:
            existing["blocked_by"].extend(entries)
    brief = None
    review = "not_required"
    if spec["task"] == "task-performance":
        review = "collecting_inputs"
        if not blockers and not conflicts:
            brief = _performance_brief(record, spec)
            decision = record.get("brief_decision")
            review = "awaiting_confirmation"
            if decision == {"question": brief["id"], "value": "approve"}:
                review = "approved"
            elif decision == {"question": brief["id"], "value": "revise"}:
                review = "changes_requested"
            else:
                questions = [_brief_question(brief)]
        if review != "approved":
            for stage in ("baseline_measurement", "candidate_search"):
                blocker = next((item for item in blockers if item["stage"] == stage), None)
                if blocker is None:
                    blocker = {"stage": stage, "blocked_by": []}
                    blockers.append(blocker)
                blocker["blocked_by"].append({"field": "task_brief", "status": review})
    blocked_stages = {item["stage"] for item in blockers}
    allowed_next = ["read_only_preparation"] + [
        stage for stage in ("baseline_measurement", "candidate_search")
        if stage not in blocked_stages
    ]
    complete = not blockers and not conflicts
    return {
        "schema_version": SCHEMA_VERSION,
        "task": spec["task"],
        "record_id": record["record_id"],
        "revision": record["revision"],
        "phase": record["phase"],
        "primary_task": record["primary_task"],
        "questions": questions,
        "needs_user_input": bool(questions) or review == "changes_requested",
        "brief_review": review,
        "task_brief": brief,
        "blockers": blockers,
        "conflicts": conflicts,
        "allowed_next": allowed_next,
        "complete": complete,
        "execution": "not started",
        "fields": {
            path: {"value": entry.get("value"), "source": entry.get("source"),
                   "status": entry.get("status")}
            for path, entry in record["fields"].items()
        },
    }


def answer(record: dict, spec: dict, *, question_id: str, value: object = None,
           unknown: bool = False) -> dict:
    """Apply one answer to a copy of ``record``.

    The question must be one ``evaluate`` previously recorded in
    ``record["open_questions"]``; its dependency snapshot must still hold and
    the field must still be open. A duplicate, stale or inapplicable delivery
    is rejected, so a late reply to a superseded question changes nothing.
    """
    record = reconcile_record(record, spec)
    open_questions = record.get("open_questions")
    if not isinstance(open_questions, list):
        raise IntakeError("invalid_record",
                          "open_questions must be recorded by evaluate before answering")
    question = next((item for item in open_questions
                     if isinstance(item, dict) and item.get("id") == question_id), None)
    if question is None:
        answered = any(entry.get("source") == f"answer:{question_id}"
                       for entry in record["fields"].values())
        if answered:
            raise IntakeError("already_answered",
                              f"{question_id} was already recorded; re-evaluate for "
                              "current questions")
        prefix, separator, remainder = question_id.partition(":")
        if prefix + separator == _QUESTION and remainder.partition(":")[0] in _field_paths(spec):
            raise IntakeError("stale_answer",
                              f"{question_id} is not open in the current record; re-evaluate")
        raise IntakeError("unknown_question",
                          f"No recorded open question {question_id}; run evaluate first")
    if question_id.startswith(BRIEF_QUESTION_PREFIX):
        view = evaluate(record, spec)
        if (view["brief_review"] != "awaiting_confirmation"
                or view["task_brief"]["id"] != question_id):
            raise IntakeError("stale_answer", "Present the current task brief before answering")
        if unknown:
            value = "revise"
        if value not in ("approve", "revise"):
            raise IntakeError("invalid_value", "Reply to the task brief with approve or revise")
        record["brief_decision"] = {"question": question_id, "value": value}
        record["open_questions"] = []
        return record
    fields = _field_paths(spec)
    field = fields.get(question.get("field"))
    if field is None:
        raise IntakeError("unknown_question",
                          f"{question_id} names a field outside {spec['task']}; re-evaluate")
    if _question(record, field)["id"] != question_id:
        raise IntakeError("stale_answer",
                          f"{question_id} was asked before its dependencies changed; "
                          "re-evaluate")
    if not _applicable(record, field) or _entry(record, field["path"]).get("status") not in (
        "unknown", "conflicting", "assumed",
    ):
        raise IntakeError("stale_answer",
                          f"{question_id} no longer applies; re-evaluate")
    updated = copy.deepcopy(record)
    if unknown:
        updated["fields"][field["path"]] = {
            "value": None, "source": f"answer:{question_id}",
            "status": "unknown", "asked": True,
        }
        _bump(updated, updated["revision"] + 1)
    else:
        source = f"answer:{question_id}"
        updated["fields"][field["path"]] = {
            "value": _coerce(field, value), "source": source,
            "status": _status_for(field, source), "asked": True,
        }
        _bump(updated, updated["revision"] + 1)
    updated["open_questions"] = [
        item for item in updated["open_questions"] if item.get("id") != question_id]
    return updated


def summary(record: dict, spec: dict, *, frozen: dict | None = None) -> dict:
    """A readable confirmation summary: sources, proposals, unknowns and next steps."""
    view = evaluate(record, spec, frozen=frozen)
    confirmed, proposed, unknown = {}, {}, []
    for field in spec["fields"]:
        path = field["path"]
        entry = view["fields"].get(path, {})
        status = entry.get("status", "unknown")
        if status == "confirmed":
            confirmed[path] = entry.get("value")
        elif status in ("proposed", "assumed"):
            proposed[path] = entry.get("value")
        elif status in ("unknown", "conflicting", "stale", "superseded"):
            unknown.append(path)
    conditions = (view["task_brief"] or {}).get("conditions", {})
    if "protocol.quality_baseline_tolerance" in conditions:
        for values in (confirmed, proposed):
            if "protocol.quality_limit" in values:
                values["protocol.quality_baseline_tolerance"] = values.pop("protocol.quality_limit")
    return {
        "schema_version": SCHEMA_VERSION,
        "task": spec["task"],
        "record_id": record["record_id"],
        "revision": view["revision"],
        "primary_task": record["primary_task"],
        "phase": record["phase"],
        "task_brief": view["task_brief"],
        "brief_review": view["brief_review"],
        "confirmed": confirmed,
        "proposed": proposed,
        "unknown": unknown,
        "conflicts": view["conflicts"],
        "blockers": view["blockers"],
        "allowed_next": view["allowed_next"],
        "complete": view["complete"],
        "execution": "not started",
    }
