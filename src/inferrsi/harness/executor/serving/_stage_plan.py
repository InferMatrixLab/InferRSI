"""Validate stage descriptors against complete service protocols before admission."""

from ...records import service_io
from ._plan import validate_service_settings


def stage_id(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Each evaluation stage needs a nonempty stage_id")
    return value


def service_stage_descriptor(row, previous, protocol, *, appended=False):
    keys = {
        "stage_id",
        "evaluation_config",
        "switch_timeout_seconds",
        "first_round_timeout_seconds",
    }
    if not appended:
        keys.add("after_completed_rounds")
    if not isinstance(row, dict) or set(row) != keys:
        raise ValueError("Invalid stage descriptor fields")
    stage_id(row["stage_id"])
    if not all(service_io.positive_number(row[k]) for k in keys if k.endswith("_seconds")):
        raise ValueError("Stage timeouts must be positive and finite")
    config_path = service_io.safe_path(protocol, row["evaluation_config"])
    settings = service_io.read(config_path)
    validate_service_settings(settings, staged=True)
    if "staged_evaluation" in settings or any(
        settings["conditions"][key] != previous["conditions"][key]
        for key in ("model", "precision", "topology")
    ):
        raise ValueError("Stage cannot nest transitions or change model, precision or topology")
    if appended:
        # Keep existing gates, workload definitions and their scoring order intact.
        variable = {"staged_evaluation", "protocol_id", "scenarios", "objectives", "ranking"}
        if (
            any(
                settings.get(k) != previous.get(k)
                for k in previous.keys() | settings.keys()
                if k not in variable
            )
            or any(
                item not in settings[k] for k in ("scenarios", "objectives") for item in previous[k]
            )
            or settings["ranking"][: len(previous["ranking"])] != previous["ranking"]
            or any(
                obj["gain"] for obj in settings["objectives"] if obj not in previous["objectives"]
            )
            or all(len(settings[k]) == len(previous[k]) for k in ("scenarios", "objectives"))
        ):
            raise ValueError(
                "Appended stage must extend and preserve all existing acceptance gates"
            )
    return {
        **row,
        "evaluation_config": config_path.relative_to(protocol).as_posix(),
        "settings": settings,
    }


def stages(settings, protocol, limit):
    config = settings.get("staged_evaluation")
    if "staged_evaluation" not in settings:
        return []
    if not isinstance(config, dict) or set(config) != {
        "initial_stage_id",
        "formal_stage_id",
        "transitions",
    }:
        raise ValueError("Invalid staged_evaluation configuration")
    initial = stage_id(config["initial_stage_id"])
    if not isinstance(config["transitions"], list) or not config["transitions"]:
        raise ValueError("A staged campaign requires a formal transition")
    seen = {initial}
    rows = []
    last = 0
    for row in config["transitions"]:
        item = service_stage_descriptor(row, settings, protocol)
        boundary = item["after_completed_rounds"]
        if type(boundary) is not int or not last < boundary < limit or item["stage_id"] in seen:
            raise ValueError("Stage IDs must be unique and each stage must have a candidate round")
        rows.append(item)
        seen.add(item["stage_id"])
        last = boundary
    if rows[-1]["stage_id"] != config["formal_stage_id"]:
        raise ValueError("Last transition must enter formal_stage_id")
    return rows
