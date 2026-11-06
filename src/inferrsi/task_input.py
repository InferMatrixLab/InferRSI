"""Load and normalize the packaged v1 task contract without probing the target."""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit

from .arguments import EXPERIMENT_DEFAULTS, command_argv, make_spec
from .catalog import BACKENDS, REPO_TYPES
from .runspec import MAX_EXPERIMENT_MINUTES, RunSpec

try:
    import yaml
    from yaml.events import AliasEvent, DocumentStartEvent
    from yaml.nodes import MappingNode, ScalarNode, SequenceNode
except ImportError as exc:
    raise ValueError(
        "YAML task input requires PyYAML. Install the standard InferRSI package."
    ) from exc

_MAX_BYTES = 64 * 1024
_INVALID_TEXT = re.compile(r"[\x00\uD800-\uDFFF]")
_SCALAR_TAG = "tag:yaml.org,2002:"
_SCALAR_TAGS = {_SCALAR_TAG + kind for kind in ("str", "null", "int", "float", "bool")}


class _TaskLoader(yaml.SafeLoader):
    # Use a small set of unambiguous scalar spellings instead of YAML 1.1's
    # dates, sexagesimal numbers and implicit yes/no/on/off booleans.
    yaml_implicit_resolvers = {}

    def compose_document(self):
        event = self.peek_event()
        if isinstance(event, DocumentStartEvent) and (event.version or event.tags):
            raise ValueError("YAML directives are unsupported in task files")
        return super().compose_document()

    def compose_node(self, parent, index):
        event = self.peek_event()
        if isinstance(event, AliasEvent) or event.anchor or event.tag:
            mark = event.start_mark
            raise ValueError(
                f"YAML line {mark.line + 1}: anchors, aliases and tags are unsupported"
            )
        return super().compose_node(parent, index)


for _kind, _pattern in {
    "null": r"^(?:null|~)?$",
    "bool": r"^(?:true|false)$",
    "int": r"^[+-]?(?:0|[1-9][0-9]*)$",
    "float": r"^[+-]?(?:[0-9]+[.][0-9]*|[.][0-9]+)(?:[eE][+-]?[0-9]+)?$"
             r"|^[+-]?[0-9]+[eE][+-]?[0-9]+$",
}.items():
    _TaskLoader.add_implicit_resolver(_SCALAR_TAG + _kind, re.compile(_pattern), None)


def _scalar(loader: _TaskLoader, node: ScalarNode, field: str):
    if node.tag not in _SCALAR_TAGS:
        raise ValueError(f"{field}: use a string or a plain numeric, boolean or null value")
    try:
        value = loader.construct_object(node)
    except (ValueError, OverflowError):
        raise ValueError(f"{field}: invalid scalar") from None
    if isinstance(value, str) and _INVALID_TEXT.search(value):
        raise ValueError(f"{field}: contains an invalid Unicode character")
    return value


def _mapping(node, field: str) -> dict:
    if not isinstance(node, MappingNode):
        raise ValueError(f"{field}: expected a mapping")
    result = {}
    for key, value in node.value:
        if (
            not isinstance(key, ScalarNode)
            or key.tag != _SCALAR_TAG + "str"
            or _INVALID_TEXT.search(key.value)
        ):
            raise ValueError(f"{field}: field names must be strings")
        name = key.value
        if name in result:
            prefix = "" if field == "task" else f"{field}."
            raise ValueError(f"{prefix}{name}: duplicate field")
        result[name] = value
    return result


def _read_task(path: Path, schema: dict) -> dict:
    if not path.is_file():
        raise ValueError("task: expected a readable YAML file")
    with path.open("rb") as stream:
        raw = stream.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES:
        raise ValueError("task: YAML exceeds 64 KiB")
    loader = None
    try:
        loader = _TaskLoader(raw.decode("utf-8-sig"))
        root = _mapping(loader.get_single_node(), "task")
        version = root.pop("schema_version", None)
        if not isinstance(version, ScalarNode):
            raise ValueError("schema_version: expected integer 1")
        number = _scalar(loader, version, "schema_version")
        if type(number) is not int or number != schema["schema_version"]:
            raise ValueError("schema_version: expected integer 1")
        result = {}
        for section, node in root.items():
            if section not in schema["sections"]:
                raise ValueError(f"{section}: unknown section")
            values = {}
            for key, field_node in _mapping(node, section).items():
                field = f"{section}.{key}"
                if key not in schema["sections"][section]:
                    raise ValueError(f"{field}: unknown field")
                if isinstance(field_node, SequenceNode):
                    value = [
                        _scalar(loader, item, f"{field}[{index}]")
                        if isinstance(item, ScalarNode) else None
                        for index, item in enumerate(field_node.value)
                    ]
                elif isinstance(field_node, ScalarNode):
                    value = _scalar(loader, field_node, field)
                else:
                    raise ValueError(f"{field}: expected a scalar or list")
                if value is not None:
                    values[key] = value
            result[section] = values
        return result
    except UnicodeError:
        raise ValueError("task: expected UTF-8 YAML") from None
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        raise ValueError(f"task: invalid YAML{location}") from None
    except RecursionError:
        raise ValueError("task: YAML is nested too deeply") from None
    finally:
        if loader is not None:
            loader.dispose()


def _text(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or _INVALID_TEXT.search(value):
        raise ValueError(f"{field}: expected a nonempty string")
    return value.strip()


def _dotted_key(value, field: str) -> str:
    key = _text(value, field)
    if any(not part or part != part.strip() for part in key.split(".")):
        raise ValueError(f"{field}: expected a dotted JSON key")
    return key


def _path(value: str, field: str, base: Path) -> str:
    try:
        return str((base / value).resolve())
    except (OSError, RuntimeError, ValueError):
        raise ValueError(f"{field}: invalid filesystem path") from None


def _normalize(value, rule: dict, field: str, base: Path, *, cli: bool = False):
    kind = rule["type"]
    if kind == "boolean":
        if type(value) is not bool:
            raise ValueError(f"{field}: expected a boolean")
        return value
    if kind == "positive_integer":
        if type(value) is not int or value < 1:
            raise ValueError(f"{field}: expected a positive integer")
        return value
    if kind in ("minutes", "threshold"):
        # Convert only finite JSON-representable numbers. A YAML integer may be huge.
        try:
            number = float(value) if type(value) in (int, float) else math.nan
        except OverflowError:
            number = math.nan
        if kind == "minutes" and not 0 < number <= MAX_EXPERIMENT_MINUTES:
            raise ValueError(f"{field}: expected minutes greater than zero and at most seven days")
        if kind == "threshold" and (not math.isfinite(number) or number < 0):
            raise ValueError(f"{field}: expected a finite nonnegative percentage")
        return number
    if kind in ("argv", "ids", "checks"):
        if cli and kind == "argv":
            try:
                value = list(command_argv(value))
            except ValueError:
                raise ValueError(f"{field}: expected a nonempty quoted argv command") from None
        elif cli and kind == "ids":
            value = [item.strip() for item in value.split(",") if item.strip()]
        if not isinstance(value, list) or any(
            not isinstance(item, str) or _INVALID_TEXT.search(item) for item in value
        ):
            raise ValueError(f"{field}: expected a list of strings")
        if kind == "argv":
            if not value or not value[0].strip():
                raise ValueError(f"{field}: expected a nonempty executable as the first argv item")
            return value
        if kind == "checks":
            value = [_dotted_key(item, field) for item in value]
        else:
            value = [_text(item, field) for item in value]
            if any("," in item for item in value):
                raise ValueError(f"{field}: individual device IDs cannot contain commas")
        if len(value) != len(set(value)):
            raise ValueError(f"{field}: values must be unique")
        return value

    value = _text(value, field)
    if kind in ("choice", "framework", "backend"):
        choices = {"framework": REPO_TYPES, "backend": BACKENDS}.get(kind, rule.get("choices"))
        if value not in choices:
            raise ValueError(f"{field}: expected one of {', '.join(choices)}")
    if kind == "revision":
        if not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", value):
            raise ValueError(f"{field}: expected a full Git object ID")
        return value.lower()
    if kind == "metric":
        return _dotted_key(value, field)
    if kind == "reference" and re.match(r"(?i)https?:", value):
        try:
            url = urlsplit(value)
            valid = (
                url.hostname and url.username is None and url.password is None
                and url.port != 0 and not url.query
            )
            if valid and not any(ord(char) < 32 or char.isspace() for char in value):
                return value
        except ValueError:
            pass
        raise ValueError(f"{field}: expected an HTTP(S) issue URL or local plan path")
    if kind == "reference" and "://" in value:
        raise ValueError(f"{field}: only HTTP(S) issue URLs or local plan paths are supported")
    if kind in ("path", "reference") or (
        kind == "interpreter" and (Path(value).drive or "/" in value or "\\" in value)
    ):
        return _path(value, field, base)
    return value


@dataclass(frozen=True)
class TaskInput:
    task: dict
    missing: tuple[str, ...]
    arguments: dict

    def preview(self) -> dict:
        return {"task": self.task, "complete": not self.missing, "missing": self.missing}

    def execution_args(self, args: argparse.Namespace) -> argparse.Namespace:
        if self.missing:
            raise ValueError("task: required fields for plan/run: " + ", ".join(self.missing))
        reference = self.task["acceptance"]["reference"]
        if not re.match(r"(?i)https?://", reference) and not Path(reference).is_file():
            raise ValueError("acceptance.reference: local plan must be an existing file")
        return argparse.Namespace(**(vars(args) | self.arguments))

    def make_spec(self, args: argparse.Namespace) -> RunSpec:
        try:
            spec = make_spec(args)
        except ValueError as exc:
            # Scalar and argv validation is complete at this point. RunSpec
            # still checks filesystem-dependent invariants before any probe.
            field = {
                "repo": "optimization.repository",
                "candidate_repo": "optimization.candidate_repository",
                "output_dir": "environment.output_directory",
            }.get(str(exc).partition(" ")[0], "task")
            raise ValueError(f"{field}: {exc}") from None
        output = Path(spec.output_dir)
        if any(path.exists() and not path.is_dir() for path in (output, *output.parents)):
            raise ValueError("environment.output_directory: expected a directory path")
        return spec


def normalize_task(path: str | Path, overrides: dict | None = None) -> TaskInput:
    """Normalize YAML and explicitly supplied CLI flags, without probing or writing."""
    schema_resource = files("inferrsi").joinpath("data", "task_input", "schema-v1.json")
    schema = json.loads(schema_resource.read_text(encoding="utf-8"))
    path = Path(path)
    yaml_base = path.absolute().parent
    raw = _read_task(path, schema)
    overrides = overrides or {}
    task = {"schema_version": schema["schema_version"]}
    missing = []
    arguments = {}
    for section, fields in schema["sections"].items():
        normalized = {}
        task[section] = normalized
        for key, rule in fields.items():
            field = f"{section}.{key}"
            flag = rule.get("cli_argument")
            arg = flag[2:].replace("-", "_") if flag else None
            value = raw.get(section, {}).get(key)
            if value is not None:
                value = _normalize(value, rule, field, yaml_base)
            if arg in overrides:
                override = _normalize(overrides[arg], rule, field, Path.cwd(), cli=True)
                if section == "acceptance" and override != value:
                    raise ValueError(f"{field}: {flag} conflicts with the task file")
                value = override
            if value is None:
                if rule.get("required_for_plan_run"):
                    missing.append(field)
                elif arg in EXPERIMENT_DEFAULTS:
                    default = EXPERIMENT_DEFAULTS[arg]
                    value = (
                        _path(default, field, yaml_base) if rule["type"] == "path" and default
                        else [] if rule["type"] in ("ids", "checks")
                        else default
                    )
            if value is not None:
                normalized[key] = value
            if arg:
                arguments[arg] = ",".join(value) if rule["type"] == "ids" else value
    if task["acceptance"].get("require_quality") and "quality_command" not in task["environment"]:
        missing.append("environment.quality_command")
    if task["environment"].get("backend") == "mlx" and task["environment"].get("device_ids"):
        raise ValueError("environment.device_ids: unsupported for the mlx backend")
    return TaskInput(task, tuple(missing), arguments)
