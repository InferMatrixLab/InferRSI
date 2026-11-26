"""intake/v1 CLI: evaluate, answer and summarize confirmation records.

The contract lives in ``inferrsi.apps.cli.intake_contract``. This module loads the
versioned per-task spec and the record file, applies the pure contract
functions and writes the record back. It starts nothing and measures nothing;
``execution`` stays ``not started`` until an existing operation is authorized.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from importlib.resources import files
from pathlib import Path

from . import intake_contract as intake


def _spec_root() -> Path:
    return Path(str(files("inferrsi").joinpath("knowledge", "data", "skill_library", "tasks")))


def spec_path(task: str) -> Path:
    return _spec_root() / task / "intake.json"


def load_spec(task: str) -> dict:
    path = spec_path(task)
    if not path.is_file():
        raise intake.IntakeError("unknown_task", f"No intake spec is packaged for {task}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise intake.IntakeError("invalid_spec", f"{task}/intake.json: {exc}") from exc
    return intake.load_spec(data)


def read_record(path: Path) -> dict:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise intake.IntakeError(
            "unreadable_record", f"cannot read {path}: {exc.strerror or exc}") from exc
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise intake.IntakeError("invalid_record", f"{path}: {exc}") from exc
    if not isinstance(record, dict):
        raise intake.IntakeError("invalid_record", f"{path}: record must be an object")
    return record


def _payload(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False, indent=2) + "\n"


def write_record(path: Path, record: dict) -> str:
    """Write the record atomically; return the sha256 of the written bytes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = _payload(record)
    descriptor, temp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def frozen_values(path: Path) -> dict:
    """Acceptance values stated by a frozen gate task file, keyed by spec path."""
    from . import task_input

    preview = task_input.preview(path)
    if not preview["valid"]:
        first = preview["errors"][0]
        raise intake.IntakeError(
            "invalid_frozen", f"frozen gate record: {first['field']} {first['message']}")
    acceptance = preview["task"]["acceptance"]
    # ``reference`` names the gate record itself and is path-normalized by the task
    # contract, so it is not compared; ``task_input.frozen_gate`` makes the same choice.
    return {f"acceptance.{name}": value for name, value in acceptance.items()
            if name != "reference" and preview["sources"][f"acceptance.{name}"] == "yaml"}


def parse_sets(items: list[str]) -> dict:
    values = {}
    for item in items:
        path, separator, value = item.partition("=")
        if not separator or not path.strip():
            raise intake.IntakeError("invalid_set", f"--set expects PATH=VALUE, got {item!r}")
        values[path.strip()] = value
    return values


def _persist(path: Path, record: dict, view: dict) -> None:
    for path_key, field in record["fields"].items():
        field["status"] = view["fields"][path_key]["status"]
    record["open_questions"] = view["questions"]
    record["blockers"] = view["blockers"]
    record["conflicts"] = view["conflicts"]
    record["allowed_next"] = view["allowed_next"]
    record["complete"] = view["complete"]
    write_record(path, record)


def _evaluate_and_save(path: Path, record: dict, spec: dict, frozen_path: Path | None,
                       *, selecting_reference: bool) -> dict:
    frozen = frozen_values(frozen_path) if frozen_path else None
    reference = intake.selected_reference(record)
    if frozen and reference and Path(reference).resolve() == frozen_path.resolve():
        snapshot = {"reference": reference, "values": frozen}
        if selecting_reference:
            record["selected_gate"] = snapshot
        if record.get("selected_gate") == snapshot:
            # Preserve disagreements for the frozen-gate comparison.
            matching = {}
            for field in spec["fields"]:
                key = field["path"]
                entry = record["fields"].get(key, {})
                if key in frozen and entry.get("status") != "conflicting":
                    if entry.get("value") in (None, frozen[key]):
                        matching[key] = frozen[key]
            record = intake.set_fields(record, spec, matching, source="frozen_gate")
        else:
            # The file is new or changed since the selection. Re-open the reference
            # question and persist the revocation before handing off to campaign start.
            record.pop("selected_gate", None)
            record["fields"][intake.REFERENCE] = {
                "value": reference, "source": "repo_inspection", "status": "assumed",
            }
            record["revision"] += 1
    view = intake.evaluate(record, spec, frozen=frozen)
    _persist(path, record, view)
    return view


def evaluate_command(args) -> dict:
    record_path = Path(args.record)
    existing = record_path.is_file()
    if existing:
        record = read_record(record_path)
    else:
        if not args.task:
            raise intake.IntakeError(
                "missing_task", "the record does not exist yet; pass --task")
        record = intake.new_record(args.task, record_id="intake-" + uuid.uuid4().hex[:12])
    if args.task and args.task != record["task"]:
        raise intake.IntakeError(
            "task_mismatch", f"the record already records {record['task']}, not {args.task}")
    spec = load_spec(record["task"])
    record = intake.reconcile_record(record, spec)
    values = parse_sets(args.set)
    selecting = intake.REFERENCE in values and args.source in ("prompt", "grilling_brief")
    if existing and selecting and intake.selected_reference(record) != values[intake.REFERENCE]:
        raise intake.IntakeError("user_answer_required",
                                 "Use the acceptance reference question to record the user's reply")
    if values:
        record = intake.set_fields(record, spec, values, source=args.source)
    return _evaluate_and_save(record_path, record, spec, args.frozen,
                              selecting_reference=selecting and not existing)


def answer_command(args) -> dict:
    record_path = Path(args.record)
    record = read_record(record_path)
    spec = load_spec(record["task"])
    record = intake.answer(record, spec, question_id=args.question,
                           value=args.value, unknown=bool(args.unknown))
    return _evaluate_and_save(record_path, record, spec, args.frozen,
                              selecting_reference=args.question == f"q:{intake.REFERENCE}")


def summary_command(args) -> dict:
    record = read_record(Path(args.record))
    spec = load_spec(record["task"])
    frozen = frozen_values(args.frozen) if args.frozen else None
    return intake.summary(record, spec, frozen=frozen)


def campaign_gate(path: Path, *, expected_task: str = "task-performance",
                  frozen: dict | None = None) -> tuple[dict, dict]:
    """Evaluate a record for ``campaign start``; return the gate and the record it read.

    Never starts or measures anything. The caller retains the returned record, so the
    bytes kept next to the campaign are the ones this gate evaluated.
    """
    record = read_record(Path(path))
    if record.get("task") != expected_task:
        raise intake.IntakeError(
            "task_mismatch", f"{path} records {record.get('task')}, not {expected_task}")
    spec = load_spec(expected_task)
    view = intake.evaluate(record, spec, frozen=frozen)
    return {
        "status": "ready" if view["complete"] else "blocked",
        "task": expected_task,
        "record": str(path),
        "revision": record["revision"],
        "complete": view["complete"],
        "questions": view["questions"],
        "blockers": view["blockers"],
        "conflicts": view["conflicts"],
        "allowed_next": view["allowed_next"],
        "execution": "not started",
    }, record


def attach_record(session_dir: Path, record: dict, gate: dict) -> dict:
    """Retain the gated record in the campaign directory and name its digest."""
    digest = write_record(Path(session_dir) / "intake.json", record)
    return {"intake": {
        "record": "intake.json",
        "task": record["task"],
        "revision": record["revision"],
        "sha256": digest,
        "gate": gate["status"],
    }}


def _render_questions(view: dict) -> list[str]:
    lines = []
    if view["questions"]:
        lines.append("Ask the user the following questions using the host question-card tool. "
                     "Wait for their reply before measurement or candidate work. "
                     "Use numbered text when the tool is unavailable.")
        lines.append("questions:")
        for question in view["questions"]:
            lines.append(f"  {question['id']}  {question['question']}")
            for option in question["options"]:
                hint = f"  ({option['hint']})" if option.get("hint") else ""
                lines.append(f"      - {option['value']}{hint}")
            lines.append("      - unknown  (record as unknown; dependent stages stay blocked)")
    return lines


def render(view: dict) -> str:
    lines = [f"task: {view['task']}  revision: {view['revision']}  "
             f"complete: {'true' if view['complete'] else 'false'}"]
    lines.extend(_render_questions(view))
    if view["conflicts"]:
        lines.append("conflicts:")
        for item in view["conflicts"]:
            lines.append(f"  {item['field']}: record {item.get('record_value')!r} vs "
                         f"frozen {item.get('frozen_value')!r}")
    if view["blockers"]:
        lines.append("blocked stages:")
        for blocker in view["blockers"]:
            fields = ", ".join(
                f"{item['field']} ({item['status']})" for item in blocker["blocked_by"])
            lines.append(f"  {blocker['stage']}: {fields}")
    lines.append("allowed next: " + ", ".join(view["allowed_next"]))
    return "\n".join(lines)


def render_summary(view: dict) -> str:
    lines = [f"task: {view['task']}  revision: {view['revision']}  "
             f"complete: {'true' if view['complete'] else 'false'}"]
    for label, values in (("confirmed", view["confirmed"]), ("proposed", view["proposed"])):
        if values:
            lines.append(f"{label}:")
            for path, value in values.items():
                lines.append(f"  {path} = {json.dumps(value, ensure_ascii=False)}")
    if view["unknown"]:
        lines.append("unknown:")
        lines.extend(f"  {path}" for path in view["unknown"])
    if view["conflicts"]:
        lines.append("conflicts:")
        for item in view["conflicts"]:
            lines.append(f"  {item['field']}: record {item.get('record_value')!r} vs "
                         f"frozen {item.get('frozen_value')!r}")
    if view["blockers"]:
        lines.append("blocked stages:")
        for blocker in view["blockers"]:
            lines.append(f"  {blocker['stage']}")
    lines.append("allowed next: " + ", ".join(view["allowed_next"]))
    return "\n".join(lines)


def command(args) -> int:
    try:
        if args.intake_action == "evaluate":
            result = evaluate_command(args)
        elif args.intake_action == "answer":
            result = answer_command(args)
        else:
            result = summary_command(args)
    except intake.IntakeError as exc:
        print(json.dumps({"error": exc.code, "message": str(exc), "execution": "not started"},
                         ensure_ascii=False, indent=2))
        return 2
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    else:
        print(render_summary(result) if args.intake_action == "summary" else render(result))
    return 0
