"""Saved-request CLI over the existing Apps ports and explicit host configuration."""

import json
from pathlib import Path

from ...contracts.json_v1 import encode


def add_parser(commands) -> None:
    evaluate = commands.add_parser("evaluate", help="Prepare, execute or assess a saved request")
    actions = evaluate.add_subparsers(dest="evaluate_action", required=True)
    descriptions = {
        "prepare": "Freeze and archive the configured evaluation task",
        "execute": "Execute or replay the original saved attempt",
        "assess": "Assess a fixed record using retained evidence only",
    }
    for action, description in descriptions.items():
        command = actions.add_parser(action, help=description, description=description)
        command.add_argument("--request", required=True, help="@<saved request JSON file>")
        command.add_argument("--output-id", required=True)
        command.add_argument("--workspace", type=Path, required=True,
                             help="Existing absolute directory authorized for Apps output")
        command.add_argument("--storage-config", type=Path, required=True)
        command.add_argument("--runtime-config", type=Path, required=action != "assess",
                             help="Trusted local B/H configuration; separate from the request")
        command.add_argument("--prepared-ref", help="@<full PreparedRef JSON file>")
        command.add_argument("--record-ref", help="@<full RecordRef JSON file>")
        command.add_argument("--scope")
        command.add_argument("--primary-claim")
        if action == "execute":
            command.add_argument("--capture-evidence", action="store_true",
                                 help="Retain the configured frozen P1 task's evidence")


def _object_file(path: Path) -> dict:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate JSON object key")
            value[key] = item
        return value

    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        encode(value)
    except RecursionError as error:
        raise ValueError("JSON input nesting is too deep") from error
    return value


def _request_file(value: str) -> dict:
    if not value.startswith("@") or len(value) == 1:
        raise ValueError("Requests and references require @<JSON file>")
    return _object_file(Path(value[1:]))


def _absolute(value) -> Path:
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError("Runtime paths must be explicit absolute local paths")
    path = Path(value)
    if not path.is_absolute() or path.anchor.startswith(("\\\\", "//")):
        raise ValueError("Runtime paths must be explicit absolute local paths")
    return path


def _runtime(path: Path) -> dict:
    value = _object_file(path)
    if (type(value.get("schema_version")) is not int or value["schema_version"] != 1
            or not value.keys() <= {"schema_version", "benchmark", "target"}):
        raise ValueError("Unsupported evaluate runtime configuration")
    return value


def _prepare_ports(config: dict) -> dict:
    from ...benchmark import preparation

    task = config.get("benchmark")
    if not isinstance(task, dict) or task.keys() != {"protocol", "worker_role", "resources"}:
        raise ValueError("prepare requires a configured frozen Benchmark task")
    sources = task["resources"]
    if not isinstance(sources, dict) or not sources:
        raise ValueError("Expected role-keyed read-only Benchmark resources")
    sources = {role: _absolute(path) for role, path in sources.items()}
    protocol = _object_file(_absolute(task["protocol"]))
    service = preparation.PreparationService(
        protocol, resources=lambda role: sources[role].open("rb"), worker_role=task["worker_role"],
    )
    return {"prepare_benchmark": service.prepare, "encode_prepared": preparation.encode,
            "validate_prepared": preparation.validate_prepared}


def _execute_ports(config: dict, storage: dict, *, capture_evidence: bool = False) -> dict:
    from ...harness.executor import LocalCpuTarget, execute_attempt
    from ...harness.records import RunStore
    from ..storage.artifact_reader import ArtifactReader

    target = config.get("target")
    required = {"target_id", "config_revision", "work_root"}
    optional = {"controller_root", "target_root", "module_root"}
    if not isinstance(target, dict) or not required <= target.keys() <= required | optional:
        raise ValueError("execute requires a configured local CPU target")
    values = dict(target)
    values["work_root"] = _absolute(values["work_root"])
    for key in optional:
        if key in values and values[key] is not None:
            values[key] = _absolute(values[key])
    target = LocalCpuTarget(**values)
    reader = ArtifactReader(storage)
    mount = next((item for item in storage["mounts"]
                  if item["namespace"] == storage["harness_namespace"]), None)
    if mount is None or mount["kind"] != "harness_sqlite":
        raise ValueError("execute requires the configured Harness SQLite mount")
    capture = None
    if capture_evidence:
        from ..handoff.production_capture import PreparedCapture

        capture = PreparedCapture(storage)

    def execute(spec):
        # Opening a writable Store is an execution effect. Defer it until Apps
        # has verified the saved request/preparation, and preserve PublicError.
        return execute_attempt(
            RunStore.from_mount(mount), target, spec,
            artifact_reader=reader, evidence_capture=capture,
        )

    return {"execute_harness": execute}


def _assess_ports() -> dict:
    from ...benchmark import assessment

    return {"assess_benchmark": assessment.assess,
            "encode_assessment": assessment.encode,
            "validate_assessment": assessment.validate_assessment}


def _check_options(args, request: dict, storage: dict) -> None:
    for name in ("prepared_ref", "record_ref"):
        option = getattr(args, name)
        if option is not None and (
            name not in request or encode(_request_file(option)) != encode(request[name])
        ):
            raise ValueError(f"--{name.replace('_', '-')} disagrees with the saved request")
    if args.primary_claim is not None and (
        args.evaluate_action != "assess" or args.primary_claim != request.get("primary_claim_id")
    ):
        raise ValueError("--primary-claim disagrees with the saved request")
    if args.scope is not None:
        if args.evaluate_action == "prepare":
            nested = request.get("request")
            scope = nested.get("validation_scope") if isinstance(nested, dict) else None
        elif args.evaluate_action == "assess":
            scope = request.get("primary_scope")
        else:
            from ..storage.archive import read_prepared

            ref = request.get("prepared_ref")
            if not isinstance(ref, dict):
                raise ValueError("execute requires a saved PreparedRef")
            scope = read_prepared(storage, ref).get("validation_scope")
        if args.scope != scope:
            raise ValueError("--scope disagrees with the saved request")


def dispatch(args) -> int:
    """Print the same result as Python, including committed refs on publication failure."""
    from ...harness.api import PublicError
    from .. import api
    from ..storage.archive import validate_output_id

    try:
        validate_output_id(args.output_id)
        workspace = _absolute(str(args.workspace))
        if not workspace.is_dir() or workspace.resolve() != workspace:
            raise ValueError("--workspace requires an existing absolute authorized directory")
        request = _request_file(args.request)
        storage = _object_file(args.storage_config)
        _check_options(args, request, storage)
        if args.evaluate_action == "prepare":
            ports = _prepare_ports(_runtime(args.runtime_config))
        elif args.evaluate_action == "execute":
            ports = _execute_ports(_runtime(args.runtime_config), storage,
                                   capture_evidence=args.capture_evidence)
        else:
            # Offline assessment ignores target/worker configuration entirely.
            ports = _assess_ports()
        output = getattr(api, args.evaluate_action)(
            request, workspace=args.workspace, storage_config=storage,
            output_id=args.output_id, **ports,
        )
    except PublicError as error:
        raise ValueError(str(error)) from error
    print(encode(output.result).decode("utf-8"))
    return output.result["exit_code"]
