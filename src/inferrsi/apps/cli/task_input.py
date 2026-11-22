"""Shared YAML task contract v1: read-only validation, normalization and preview.

The CLI and Agents read the same task file through this module. It parses the YAML,
reports format and value errors by field, resolves YAML paths against the task file's
directory, merges explicit CLI values over YAML values and built-in defaults, and lists
the fields a full plan or run still needs. It reads one file and writes nothing: no
subprocess, probe, install or workspace file. PyYAML is a core dependency and is imported
only when a task file is parsed, so importing the CLI never loads it.

``plan --task`` and ``run --task`` call ``preview`` with ``supplied_overrides`` before any
probe, then copy a complete task onto their arguments with ``arguments_from``. Both
helpers are pure. ``frozen_gate`` also reads the local frozen gate record named by
``acceptance.reference`` and compares its acceptance fields with the task; it writes
nothing either.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shlex
from dataclasses import dataclass
from importlib.resources import files
from typing import Any
from urllib.parse import urlsplit

from ...knowledge.catalog import BACKENDS, REPO_TYPES

SCHEMA_VERSION = 1
MAX_BYTES = 64 * 1024
MAX_MINUTES = 7 * 24 * 60
SECTIONS = ("optimization", "environment", "acceptance")
PLANES = ("harness", "model", "infra")
MODES = ("config", "code", "semantic")
DIRECTIONS = ("minimize", "maximize")
RESOURCE = "task-input/v1"
# Kept in step with schema.json; tests compare the two.
# ``(?!\n)`` keeps a trailing newline out under jsonschema's ``re.search`` too.
DOTTED_KEY = r"^[^.\s]([^.]*[^.\s])?(\.[^.\s]([^.]*[^.\s])?)*(?!\n)$"
DEVICE_ID = r"^[^,\s]+(?!\n)$"
DOCUMENT = "$"
_URL_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")


@dataclass(frozen=True)
class Field:
    """One task field: its type, CLI flag and role in a full plan/run."""

    section: str
    name: str
    kind: str
    flag: str | None = None
    dest: str | None = None
    required: bool = False
    acceptance: bool = False
    default: Any = None
    choices: tuple[str, ...] = ()
    help: str = ""

    @property
    def path(self) -> str:
        return f"{self.section}.{self.name}"


FIELDS = (
    Field("optimization", "repository", "path", "--repo", "repo", required=True,
          help="Prepared target Git checkout"),
    Field("optimization", "candidate_repository", "path", "--candidate-repo", "candidate_repo",
          help="Candidate checkout; defaults to the baseline checkout"),
    Field("optimization", "model", "text", "--model", "model", required=True,
          help="Model identity/path recorded in the experiment"),
    Field("optimization", "model_revision", "revision", "--model-revision", "model_revision"),
    Field("optimization", "framework", "choice", "--repo-type", "repo_type", required=True,
          choices=REPO_TYPES),
    Field("optimization", "workload", "text", "--workload-id", "workload_id", required=True,
          help="Caller-declared fixed workload identity"),
    Field("optimization", "scenario", "text", "--scenario", "scenario",
          default="external_benchmark", help="Caller-declared scenario label"),
    Field("optimization", "mode", "choice", "--mode", "mode", default="config", choices=MODES),
    Field("optimization", "objective", "text", required=True),
    Field("optimization", "plane", "choice", required=True, choices=PLANES),
    Field("environment", "backend", "choice", "--backend", "backend", required=True,
          choices=BACKENDS),
    Field("environment", "device_ids", "ids", "--device-ids", "device_ids", default=(),
          help="Comma-separated caller-assigned device IDs"),
    Field("environment", "device_model", "text", "--device-model", "device_model",
          help="Expected CUDA device model or Apple Silicon chip"),
    Field("environment", "python", "python", "--python", "python",
          help="Prepared Python runtime used for target package inspection"),
    Field("environment", "baseline_command", "command", "--baseline-command",
          "baseline_command", required=True,
          help="Quoted argv command; {result} is replaced with a fresh output path"),
    Field("environment", "candidate_command", "command", "--candidate-command",
          "candidate_command", required=True),
    Field("environment", "quality_command", "command", "--validation-command",
          "validation_command", help="Explicit quality/correctness command"),
    Field("environment", "repetitions", "count", "--repetitions", "repetitions",
          required=True),
    Field("environment", "max_minutes", "minutes", "--max-minutes", "max_minutes",
          required=True, help="Experiment deadline, at most seven days"),
    Field("environment", "rounds", "count"),
    Field("acceptance", "reference", "reference", required=True),
    Field("acceptance", "baseline_revision", "revision", required=True),
    Field("acceptance", "metric_key", "key", "--metric-key", "metric_key", required=True,
          acceptance=True, help="Flat or dotted key in benchmark JSON"),
    Field("acceptance", "direction", "choice", "--direction", "direction", required=True,
          acceptance=True, choices=DIRECTIONS),
    Field("acceptance", "metric_unit", "text", "--metric-unit", "metric_unit", required=True,
          acceptance=True),
    Field("acceptance", "min_improvement_pct", "percent", "--min-improvement-pct",
          "min_improvement_pct", required=True, acceptance=True),
    Field("acceptance", "comparison_scope", "text", "--comparison-scope", "comparison_scope",
          acceptance=True, default="external_command"),
    Field("acceptance", "required_trial_checks", "keys", "--require-trial-check",
          "require_trial_check", acceptance=True, default=(),
          help="Required literal-true qualification field; repeatable"),
    Field("acceptance", "constraints", "text"),
)
BY_PATH = {field.path: field for field in FIELDS}


def _printable(text: str) -> str:
    return text.encode("utf-8", "backslashreplace").decode("utf-8")


def _error(field: str, message: str, source: str = "yaml") -> dict[str, str]:
    return {"field": _printable(field), "message": _printable(message), "source": source}


def _type_name(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (list, tuple)):
        return "list"
    if isinstance(value, dict):
        return "mapping"
    return type(value).__name__


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return f"must be a string, not {_type_name(value)}"
    if not re.search(r"\S", value):
        return "must not be empty"
    return None


def _number(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return f"must be a number, not {_type_name(value)}"
    try:
        finite = math.isfinite(float(value))
    except OverflowError:
        finite = False
    return None if finite else "must be a finite number"


def _encodable(value: object) -> bool:
    items = value if isinstance(value, (list, tuple)) else (value,)
    try:
        for item in items:
            if isinstance(item, str):
                item.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _path(value: object) -> str | None:
    """Check a filesystem path or Python selector; the OS rejects an embedded NUL."""
    problem = _text(value)
    if problem is None and "\0" in value:
        problem = "must not contain a NUL character"
    return problem


def _http_url(value: str) -> str | None:
    """Check an ``http(s)://`` reference: a named host and, if given, a port 1-65535."""
    try:
        parts = urlsplit(value)
    except ValueError:
        parts = None
    if parts is None or parts.scheme not in ("http", "https"):
        return "must be an HTTP(S) issue URL or a local plan path"
    if re.search(r"[\s\x00-\x1f\x7f]", value):
        return "must not contain whitespace or control characters in an HTTP(S) URL"
    if not parts.hostname:
        return "must name a host in an HTTP(S) URL"
    # The port text exactly as urlsplit's .port reads it, checked without int()'s leniency.
    # Leading zeroes are allowed; at most five significant digits reach int(), which keeps
    # overlong text clear of Python's integer string conversion limit.
    hostinfo = parts.netloc.rpartition("@")[2]
    _, bracket, rest = hostinfo.partition("[")
    port = (rest.partition("]")[2] if bracket else hostinfo).partition(":")[2]
    digits = port.lstrip("0")
    if port and not (re.fullmatch(r"[0-9]+", port) and 0 < len(digits) <= 5
                     and int(digits) <= 65535):
        return "must use a port from 1 to 65535 in an HTTP(S) URL"
    return None


def _check(field: Field, value: object) -> str | None:
    """Return why ``value`` (never None) is invalid for ``field``, or None."""
    if not _encodable(value):
        return "must be valid Unicode text"
    kind = field.kind
    if kind == "text":
        return _text(value)
    if kind in ("path", "python"):
        return _path(value)
    if kind == "revision":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return "must be a string; quote the revision so YAML does not read it as a number"
        return _text(value)
    if kind == "choice":
        if not isinstance(value, str) or value not in field.choices:
            return "must be one of " + ", ".join(field.choices)
        return None
    if kind == "key":
        problem = _text(value)
        if problem is None and not re.fullmatch(DOTTED_KEY, value):
            problem = "must be a flat or dotted JSON key with nonempty parts"
        return problem
    if kind in ("ids", "keys"):
        if not isinstance(value, (list, tuple)):
            return f"must be a list of strings, not {_type_name(value)}"
        pattern = DEVICE_ID if kind == "ids" else DOTTED_KEY
        for item in value:
            if not isinstance(item, str):
                quote = "; quote device IDs" if kind == "ids" else ""
                return f"items must be strings, not {_type_name(item)}{quote}"
            if not re.fullmatch(pattern, item):
                return ("items must be nonempty IDs without commas or spaces" if kind == "ids"
                        else "items must be dotted JSON keys with nonempty parts")
        if len(set(value)) != len(value):
            return "items must be unique"
        return None
    if kind == "command":
        if isinstance(value, str):
            if not re.search(r"\S", value):
                return "must not be empty"
            if "\0" in value:
                return "argv items must not contain a NUL character"
            try:
                parsed = shlex.split(value, posix=True)
            except ValueError as exc:
                return f"is not a valid quoted argv command: {exc}"
            return None if parsed and parsed[0] else "must name an executable"
        if isinstance(value, (list, tuple)):
            if not value:
                return "must be a nonempty argv list"
            if not all(isinstance(item, str) for item in value):
                return "argv items must be strings"
            if any("\0" in item for item in value):
                return "argv items must not contain a NUL character"
            return None if value[0] else "argv executable cannot be empty"
        return f"must be a quoted argv string or a list of strings, not {_type_name(value)}"
    if kind == "count":
        if isinstance(value, bool) or not isinstance(value, int):
            return f"must be a positive integer, not {_type_name(value)}"
        return None if value >= 1 else "must be a positive integer"
    if kind == "minutes":
        problem = _number(value)
        if problem is None and not 0 < value <= MAX_MINUTES:
            problem = f"must be positive and at most {MAX_MINUTES} minutes (seven days)"
        return problem
    if kind == "percent":
        problem = _number(value)
        if problem is None and value < 0:
            problem = "must be nonnegative"
        return problem
    if kind == "reference":
        problem = _path(value)
        if problem is None and _URL_SCHEME.match(value):
            problem = _http_url(value)
        return problem
    raise AssertionError(f"unknown field kind {kind}")


def validate(data: object) -> list[dict[str, str]]:
    """Return field-level format and value errors for a parsed task document."""
    if not isinstance(data, dict):
        return [_error(DOCUMENT, f"the task file must be a mapping, not {_type_name(data)}")]
    errors = []
    if "schema_version" not in data:
        errors.append(_error("schema_version", "is required; set schema_version: 1"))
    else:
        version = data["schema_version"]
        if isinstance(version, bool) or not isinstance(version, int):
            errors.append(_error(
                "schema_version", f"must be the integer 1, not {_type_name(version)}"))
        elif version != SCHEMA_VERSION:
            errors.append(_error(
                "schema_version", f"version {version} is unsupported; this release reads 1"))
    for key in data:
        if key != "schema_version" and key not in SECTIONS:
            errors.append(_error(str(key), "is not a v1 task key"))
    for section in SECTIONS:
        if section not in data:
            continue
        values = data[section]
        if not isinstance(values, dict):
            errors.append(_error(
                section, f"must be a mapping, not {_type_name(values)}; omit it in a draft"))
            continue
        for name, value in values.items():
            field = BY_PATH.get(f"{section}.{name}")
            if field is None:
                errors.append(_error(f"{section}.{name}", "is not a v1 task field"))
            elif value is not None:
                problem = _check(field, value)
                if problem:
                    errors.append(_error(field.path, problem))
    return errors


def _yaml_problem(exc: Exception) -> str:
    mark = getattr(exc, "problem_mark", None)
    problem = getattr(exc, "problem", None) or str(exc).splitlines()[0]
    if mark is not None:
        return f"invalid YAML at line {mark.line + 1}, column {mark.column + 1}: {problem}"
    return f"invalid YAML: {problem}"


def _key_errors(root: object, yaml: Any) -> list[dict[str, str]]:
    """Reject duplicate, merge and non-string keys before any value is constructed."""
    errors = []
    seen = set()
    pending = [(root, "")]
    while pending:
        node, prefix = pending.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, yaml.SequenceNode):
            pending.extend((item, prefix) for item in node.value)
            continue
        if not isinstance(node, yaml.MappingNode):
            continue
        names = set()
        for key, value in node.value:
            where = prefix or DOCUMENT
            if key.tag == "tag:yaml.org,2002:merge":
                errors.append(_error(where, "YAML merge keys (<<) are not supported"))
                continue
            if not isinstance(key, yaml.ScalarNode) or key.tag != "tag:yaml.org,2002:str":
                errors.append(_error(where, "keys must be plain strings"))
                continue
            path = f"{prefix}.{key.value}" if prefix else key.value
            if key.value in names:
                errors.append(_error(path, "is a duplicate key"))
            names.add(key.value)
            pending.append((value, path))
    return sorted(errors, key=lambda item: item["field"])


def load(path: str | os.PathLike) -> tuple[object, list[dict[str, str]]]:
    """Read one YAML task document with a safe loader; return (data, document errors)."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
    except OSError as exc:
        return None, [_error(DOCUMENT, f"cannot read the task file: {exc.strerror or exc}")]
    return _parse(raw)


def _parse(raw: bytes) -> tuple[object, list[dict[str, str]]]:
    """Parse the bytes of one YAML task document; return (data, document errors)."""
    if len(raw) > MAX_BYTES:
        return None, [_error(DOCUMENT, "the task file exceeds 64 KiB")]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, [_error(DOCUMENT, "the task file must be UTF-8 text")]
    try:
        import yaml
    except ImportError:
        return None, [_error(
            DOCUMENT, "reading a task file requires PyYAML, a core InferRSI dependency; "
            "reinstall InferRSI with its dependencies into this Python",
        )]
    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
        if root is None:
            return None, [_error(DOCUMENT, "the task file is empty; start from the template")]
        errors = _key_errors(root, yaml)
        if errors:
            return None, errors
        return yaml.safe_load(text), []
    except yaml.YAMLError as exc:
        return None, [_error(DOCUMENT, _yaml_problem(exc))]
    except RecursionError:
        return None, [_error(DOCUMENT, "the task file is too deeply nested")]
    except Exception as exc:  # PyYAML value constructors raise ValueError, KeyError, ...
        return None, [_error(DOCUMENT, f"invalid YAML value ({type(exc).__name__}); "
                             "quote values such as dates, revisions and IDs")]


def _resolve(value: str, base: str) -> str:
    return os.path.normpath(os.path.join(base, value))


def _is_path_like(value: str) -> bool:
    return os.sep in value or bool(os.altsep and os.altsep in value)


def _normalize(field: Field, value: Any, base: str) -> Any:
    """Return the normalized form of a valid value; paths resolve lexically against base."""
    kind = field.kind
    if kind == "path":
        return _resolve(value, base)
    if kind == "python":
        return _resolve(value, base) if _is_path_like(value) else value
    if kind == "reference":
        return value if _URL_SCHEME.match(value) else _resolve(value, base)
    if kind == "command":
        return shlex.split(value, posix=True) if isinstance(value, str) else list(value)
    if kind in ("ids", "keys"):
        return list(value)
    if kind == "minutes" or kind == "percent":
        return float(value)
    return value


def _flag_value(field: Field, value: Any) -> Any:
    """Convert an argparse value to the YAML form of the field."""
    if field.kind == "ids" and isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


def _same(field: Field, left: Any, right: Any) -> bool:
    if field.kind == "keys":
        return sorted(left) == sorted(right)
    return left == right


def merge(
    data: object,
    overrides: dict[str, Any] | None = None,
    *,
    base: str,
    cwd: str | None = None,
) -> tuple[dict, dict[str, str], list[dict[str, str]]]:
    """Merge explicit CLI values > YAML values > built-in defaults for optional fields.

    ``overrides`` holds only flags the caller supplied, keyed by argparse dest; a None
    value counts as not supplied. YAML paths
    resolve against ``base`` (the task file's directory) and CLI paths against ``cwd``.
    Acceptance values come from the YAML: a flag that disagrees is a conflict.
    Returns (task, sources, override errors).
    """
    overrides = dict(overrides or {})
    cwd = os.path.abspath(cwd if cwd is not None else os.getcwd())
    sections = data if isinstance(data, dict) else {}
    task: dict[str, dict[str, Any]] = {section: {} for section in SECTIONS}
    sources: dict[str, str] = {}
    errors: list[dict[str, str]] = []
    for field in FIELDS:
        values = sections.get(field.section)
        raw = values.get(field.name) if isinstance(values, dict) else None
        if field.section in sections and not isinstance(values, dict):
            value, source = None, "invalid"
        elif raw is not None and _check(field, raw) is None:
            value, source = _normalize(field, raw, base), "yaml"
        elif raw is not None:
            value, source = None, "invalid"
        elif field.default is not None:
            value, source = _normalize(field, field.default, base), "default"
        else:
            value, source = None, "missing"
        supplied = overrides.pop(field.dest, None) if field.dest else None
        if supplied is not None:  # None means the caller did not supply the flag
            supplied = _flag_value(field, supplied)
            problem = _check(field, supplied)
            if problem:
                errors.append(_error(field.path, f"{field.flag} {problem}", "cli"))
            elif field.acceptance:
                if source == "invalid" or not _same(
                    field, _normalize(field, supplied, cwd), value
                ):
                    errors.append(_error(
                        field.path,
                        f"{field.flag} conflicts with the task file; acceptance fields come "
                        "from the YAML, so change the file instead", "cli",
                    ))
            else:
                value, source = _normalize(field, supplied, cwd), "cli"
        task[field.section][field.name] = value
        sources[field.path] = source
    for dest in sorted(overrides):
        errors.append(_error(dest, "is not a task field override", "cli"))
    return task, sources, errors


def blockers(task: dict, sources: dict[str, str]) -> list[dict[str, str]]:
    """Return the fields a full plan/run still needs, in schema order."""
    found = []
    for field in FIELDS:
        if field.required and task[field.section][field.name] is None:
            reason = ("invalid; fix the reported error" if sources[field.path] == "invalid"
                      else "missing")
            found.append({"field": field.path, "message": f"{reason}; required for plan/run"})
    return found


def _read(path: str | os.PathLike) -> tuple[str, object, list[dict[str, str]]]:
    task_file = os.path.abspath(os.fspath(path))
    data, errors = load(task_file)
    if not errors:
        errors = validate(data)
    return task_file, data, errors


def check(path: str | os.PathLike) -> dict:
    """Validate a task file: format and value errors by field, no normalization."""
    task_file, _, errors = _read(path)
    return {
        "schema_version": SCHEMA_VERSION,
        "task_file": task_file,
        "valid": not errors,
        "errors": errors,
    }


def preview(
    path: str | os.PathLike,
    overrides: dict[str, Any] | None = None,
    *,
    cwd: str | None = None,
) -> dict:
    """Return the effective normalized task, value sources, blockers and errors."""
    task_file, data, errors = _read(path)
    task, sources, override_errors = merge(
        data, overrides, base=os.path.dirname(task_file), cwd=cwd
    )
    errors = errors + override_errors
    missing = blockers(task, sources)
    return {
        "schema_version": SCHEMA_VERSION,
        "task_file": task_file,
        "valid": not errors,
        "complete": not errors and not missing,
        "task": task,
        "sources": sources,
        "blockers": missing,
        "errors": errors,
        "execution": "not started",
    }


def overrides_from(namespace: object) -> dict[str, Any]:
    """Return only the mapped flags present on an argparse namespace."""
    values = vars(namespace)
    return {field.dest: values[field.dest] for field in FIELDS
            if field.dest is not None and field.dest in values}


def supplied_overrides(namespace: object, supplied: object) -> dict[str, Any]:
    """Return the mapped flags whose dest is in ``supplied``, the dests the caller gave.

    ``plan``/``run`` keep parser defaults on their namespace, so a dest missing from
    ``supplied`` holds a default and never becomes an override.
    """
    values = vars(namespace)
    names = set(supplied)
    return {field.dest: values[field.dest] for field in FIELDS
            if field.dest is not None and field.dest in names and field.dest in values}


def arguments_from(task: dict) -> dict[str, Any]:
    """Return {argparse dest: value} for every mapped field of a complete preview task.

    Device IDs are joined with ``,`` (a task ID cannot contain one); commands and trial
    checks are copied as lists. A missing optional value stays None, including
    ``environment.python``, which the caller replaces with its own interpreter.
    """
    values: dict[str, Any] = {}
    for field in FIELDS:
        if field.dest is None:
            continue
        value = task[field.section][field.name]
        if field.kind == "ids":
            value = ",".join(value or ())
        elif isinstance(value, list):
            value = list(value)
        values[field.dest] = value
    return values


def is_url(reference: str) -> bool:
    """Whether a valid ``acceptance.reference`` is an HTTP(S) URL, not a local plan path."""
    return bool(_URL_SCHEME.match(reference))


# The acceptance fields compared with a frozen gate record. ``reference`` names the
# record itself, so it is not compared; the required ones must be stated by the record.
GATE_FIELDS = tuple(field for field in FIELDS
                    if field.section == "acceptance" and field.name != "reference")


def _shown(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def frozen_gate(task: dict, task_file: str | os.PathLike) -> dict:
    """Compare a task's acceptance fields with the frozen gate record it references.

    The local ``acceptance.reference`` must name a regular file, other than the task file,
    holding a valid schema v1 document whose ``acceptance`` section states the agreed gate.
    After the same built-in defaults, each acceptance field except the reference must
    equal the record's. Only that file is read. An HTTP(S) reference is never fetched, so
    its gate stays unverified. Returns the reference, the record's SHA-256, ``status``
    (``agrees``, ``mismatch`` or ``unverified``) and field-level ``problems``.
    """
    reference = task["acceptance"]["reference"]
    result: dict[str, Any] = {
        "reference": reference, "sha256": None, "status": "unverified", "problems": [],
    }

    def unverified(message: str) -> dict:
        result["problems"].append(
            {"field": "acceptance.reference", "message": _printable(message)})
        return result

    if reference is None:
        return unverified("is missing, so no frozen gate record can be read")
    if is_url(reference):
        return unverified(
            "is an HTTP(S) URL, which InferRSI does not fetch, so the frozen gate cannot be "
            "verified; point it at the local frozen gate record the acceptance issue cites")
    if not os.path.isfile(reference):
        return unverified(f"is not an existing local frozen gate record file: {reference}")
    if os.path.realpath(reference) == os.path.realpath(task_file):
        return unverified("names the task file itself, not a separate frozen gate record")
    try:
        with open(reference, "rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
    except OSError as exc:
        return unverified(f"cannot read the frozen gate record: {exc.strerror or exc}")
    data, errors = _parse(raw)
    if not errors:
        errors = validate(data)
    for error in errors:
        unverified(f"frozen gate record {reference}: {error['field']} {error['message']}")
    if errors:
        return result
    if not isinstance(data.get("acceptance"), dict):
        return unverified(f"frozen gate record {reference} has no acceptance section")
    result["sha256"] = hashlib.sha256(raw).hexdigest()
    base = os.path.dirname(reference)
    gate = merge(data, base=base, cwd=base)[0]["acceptance"]
    for field in GATE_FIELDS:
        if field.required and gate[field.name] is None:
            unverified(f"frozen gate record {reference} does not state {field.path}")
    if result["problems"]:
        return result
    for field in GATE_FIELDS:
        mine, frozen = task["acceptance"][field.name], gate[field.name]
        if (mine is None) != (frozen is None) or (
            mine is not None and not _same(field, mine, frozen)
        ):
            result["problems"].append({"field": field.path, "message": _printable(
                f"is {_shown(mine)} in the task but {_shown(frozen)} in the frozen gate "
                f"record {reference}")})
    result["status"] = "mismatch" if result["problems"] else "agrees"
    return result


def _resource(name: str) -> str:
    return files("inferrsi.apps.cli").joinpath(RESOURCE, name).read_text(encoding="utf-8")


def schema_text() -> str:
    """Return the packaged JSON Schema for task files."""
    return _resource("schema.json")


def template_text() -> str:
    """Return the packaged Agent-oriented task template."""
    return _resource("template.yaml")
