"""Absolute, evidence-linked experiment projection shared by both dashboard layouts.

Narrative is annotation, never a numeric source. Private native comparison
signatures are consumed here and never serialized into the dashboard.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

DIMENSIONS = ("workload", "metric", "unit", "scope", "statistic", "direction")
CONFIG_FIELDS = ("model", "model_revision", "shape", "batch", "precision", "hardware", "protocol")


def stable_id(*parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:24]


def timestamp(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value if parsed.tzinfo is not None else None
    except ValueError:
        return None


def external_dimensions(metric: dict) -> dict:
    """Map optional v1 fields explicitly; old name/unit/aggregation stay readable."""
    from inferrsi.harness.records.evidence import sanitized_text

    from .dashboard_data import _number

    def label(value: object) -> str | None:
        return value if (isinstance(value, str) and value.strip()
                         and sanitized_text(value) == value) else None

    config = metric.get("configuration")
    config = config if isinstance(config, dict) else {}
    # Keys are a closed vocabulary; unknown configuration keys prohibit joining.
    allowed = (*CONFIG_FIELDS, "server_profile", "runtime", "measurement_protocol")
    reasons = [f"missing configuration: {key}" for key in CONFIG_FIELDS
               if config.get(key) is None or config.get(key) == ""]
    if set(config) - set(allowed):
        reasons.append("unsupported configuration fields")
    cleaned = {}
    for key in allowed:
        if key in config:
            value = config[key]
            if key != "batch" and label(value) is not None:
                cleaned[key] = value
            elif key == "batch" and type(value) is int and value > 0:
                cleaned[key] = value
            else:
                reasons.append(f"unknown configuration: {key}")
    return {
        "measurement_id": label(metric.get("id")),
        "metric": label(metric.get("name")), "unit": label(metric.get("unit")),
        "statistic": label(metric.get("aggregation")),
        "workload": label(metric.get("workload")),
        "scope": label(metric.get("scope")),
        "direction": metric.get("direction")
        if metric.get("direction") in ("minimize", "maximize") else None,
        "sample_count": metric.get("sample_count")
        if type(metric.get("sample_count")) is int and metric["sample_count"] > 0 else None,
        "order": _number(metric.get("order")), "timestamp": timestamp(metric.get("timestamp")),
        "configuration": cleaned, "comparison_reasons": reasons,
        "references": reference_specs(metric.get("references", [])),
    }


def reference_specs(entries: object) -> list[dict]:
    from inferrsi.harness.records.evidence import sanitized_text

    from .dashboard_data import _number

    if not isinstance(entries, list):
        return []
    result = []
    for entry in entries[:100]:
        if not isinstance(entry, dict):
            continue
        result.append({
            "id": sanitized_text(entry.get("id")), "role": sanitized_text(entry.get("role")),
            "value": _number(entry.get("value")), "unit": sanitized_text(entry.get("unit")),
            "provenance": sanitized_text(entry.get("provenance"), "", 1000),
            "frozen": entry.get("frozen") is True,
            "definition": sanitized_text(entry.get("definition"), "absolute"),
            "relative_to": sanitized_text(entry.get("relative_to"), ""),
        })
    return result


def references_for(point: dict, specs: list[dict]) -> list[dict]:
    """Convert only explicitly defined frozen targets; preserve rejected references."""
    from .dashboard_data import _number

    result = []
    for spec in specs:
        item = {**spec, "value": None, "reason": None, "formula": "absolute",
                "original_value": spec["value"], "refs": point["refs"],
                "applicability": {key: point.get(key) for key in DIMENSIONS},
                "configuration": point.get("configuration", {})}
        role, definition, value = spec["role"], spec["definition"], spec["value"]
        if role not in ("local_baseline", "external_reference", "frozen_target"):
            item["reason"] = "unknown reference role"
        elif not spec["provenance"] or spec["unit"] != point["unit"]:
            item["reason"] = "missing provenance or incompatible unit"
        elif point["direction"] not in ("minimize", "maximize"):
            item["reason"] = "unknown optimization direction"
        elif role == "frozen_target" and not spec["frozen"]:
            item["reason"] = "target freeze not recorded"
        elif value is None or value < 0:
            item["reason"] = "invalid reference value"
        elif definition == "absolute":
            item["value"] = value
        elif role != "frozen_target":
            item["reason"] = "only frozen targets support conversion"
        else:
            bases = [s for s in specs if s["id"] == spec["relative_to"]
                     and s["role"] in ("local_baseline", "external_reference")
                     and s["definition"] == "absolute" and s["unit"] == point["unit"]
                     and s["provenance"] and s["value"] is not None and s["value"] > 0]
            if len(bases) != 1:
                item["reason"] = "missing or ambiguous conversion reference"
            elif definition == "improvement_pct":
                lower = point["direction"] == "minimize"
                if lower and value > 100:
                    item["reason"] = "invalid improvement percentage"
                else:
                    item["value"] = _number(bases[0]["value"] * (1 + (-value if lower else value)
                                                                            / 100))
                    item["formula"] = "B × (1 − p/100)" if lower else "B × (1 + p/100)"
            elif definition == "inverse_latency_ratio" and point["direction"] == "minimize":
                if value <= 0:
                    item["reason"] = "invalid inverse latency ratio"
                else:
                    item["value"] = _number(bases[0]["value"] / value)
                    item["formula"] = "B / r"
            else:
                item["reason"] = "unsupported target definition or direction"
        if item["value"] is None and item["reason"] is None:
            item["reason"] = "non-finite conversion"
        result.append(item)
    return result


def project_experiments(campaign_id: str, rows: list[dict], story: dict) -> dict:
    from .dashboard_data import _number

    points, events = [], []
    series_keys: dict[str, object] = {}
    by_candidate: dict[str, list[dict]] = {}
    for row in rows:
        artifacts = row["artifacts"]
        external = row.get("external")
        source = artifacts.get("external_record" if external else "evaluation", {})
        source_record = source.get("path") or artifacts.get("candidate_metadata", {}).get("path")
        row["experiment_id"] = stable_id(campaign_id, row["candidate_id"],
                                         row["run_id"] or source_record)
        by_candidate.setdefault(row["candidate_id"], []).append(row)
        common = {
            "experiment_id": row["experiment_id"], "candidate_id": row["candidate_id"],
            "run_id": row["run_id"], "source_record": source_record,
            "title": row["title"], "round": row["round"],
            "description": row["optimization"]["summary"],
            "quality": external["quality_verdict"] if external else row["quality"],
            "verdict": row["verdict"], "state": row["state"], "outcome": row["outcome"],
            "refs": list(artifacts.values()),
        }
        native_measurements = row.pop("_plot_measurements", [])
        if external:
            measurements = [
                {**m.get("plot", {}), "value": m["aggregate"],
                 "locator": f"/metrics/{index}/aggregate", "legacy_baseline": m["baseline"],
                 "legacy_target": m["target"]}
                for index, m in enumerate(external["metrics"])
            ]
        else:
            measurements = native_measurements
        ids = [m.get("measurement_id") for m in measurements]
        linked = []
        for m in measurements:
            explicit = m.get("measurement_id")
            locator = explicit if explicit and ids.count(explicit) == 1 else (
                f'{source.get("sha256", "unavailable")}#{m["locator"]}')
            point = {**common, **m, "id": stable_id(campaign_id, row["experiment_id"], locator),
                     "measurement_id": locator, "timestamp": m.get("timestamp"),
                     "order": m.get("order"), "configuration": m.get("configuration", {})}
            # An explicit order is a separate axis; never mix it with round numbers.
            reasons = list(m.get("comparison_reasons", []))
            for key in DIMENSIONS:
                if point.get(key) in (None, "", "not_recorded", "Not recorded"):
                    point[key] = None
                    reasons.append(f"missing dimension: {key}")
            point["value"] = _number(point.get("value"))
            point["axis_key"] = stable_id(*(point.get(key) for key in DIMENSIONS))
            point["plot_reasons"] = [f"missing axis: {key}" for key in DIMENSIONS
                                     if point.get(key) is None]
            if point["value"] is None:
                point["plot_reasons"].append("no plottable measurement")
            if all(point.get(k) is None for k in ("round", "order", "timestamp")):
                point["plot_reasons"].append("position not recorded")
            native = row.get("_plot_comparison_signature") if not external else None
            if not external and native is None:
                reasons.append("native comparison evidence incomplete")
            point["comparison_reasons"] = reasons
            point["series_id"] = None
            if not reasons:
                series_keys[point["id"]] = (point["axis_key"], json.dumps(
                    point["configuration"], sort_keys=True), native)
            specs = point.pop("references", [])
            for legacy in ("baseline", "target"):
                value = point.get(f"legacy_{legacy}")
                if value is not None:
                    specs.append({"id": f"legacy-{legacy}", "role": f"legacy_{legacy}",
                                  "unit": point["unit"], "value": value,
                                  "definition": "absolute", "frozen": False, "relative_to": "",
                                  "provenance": "Legacy reference; role not recorded"})
            point["references"] = references_for(point, specs)
            point["target_gaps"] = [
                {"reference_id": ref["id"], "gap": _number(
                    point["value"] - ref["value"] if point["direction"] == "minimize"
                    else ref["value"] - point["value"])}
                for ref in point["references"] if ref["role"] == "frozen_target"
                and ref["value"] is not None and point["value"] is not None
            ]
            points.append(point)
            linked.append(point)
        base_event = {**common, "experiment_ids": [row["experiment_id"]],
                      "workloads": sorted({p["workload"] for p in linked if p["workload"]}
                                          | {e["workload"] for e in row["events"]
                                             if e.get("workload")}),
                      "metrics": sorted({p["metric"] for p in linked if p["metric"]}
                                        | {e["metric"] for e in row["events"] if e.get("metric")}),
                      "scopes": sorted({p["scope"] for p in linked if p["scope"]}
                                       | {e["scope"] for e in row["events"] if e.get("scope")}),
                      "order": None, "timestamp": None, "description_kind": "recorded"}
        events.append({**base_event, "id": stable_id(row["experiment_id"], "state"),
                       "category": "run_state", "description": row["state"],
                       "narrative_category": None})
        event_ids = [e.get("event_id") for e in row["events"]]
        for event in row["events"]:
            if event.get("source") != "events":
                continue
            explicit_event_id = event.get("event_id")
            event_locator = (explicit_event_id if explicit_event_id
                             and event_ids.count(explicit_event_id) == 1 else
                             f'{source.get("sha256", "unavailable")}#/events/{event["line"] - 1}'
                             if external else f'events:{event.get("line")}')
            # Retain recorded events, including failures with no measurement.
            events.append({**base_event,
                           "id": stable_id(row["experiment_id"], "event", event_locator),
                           "timestamp": timestamp(event.get("time")),
                           "description_kind": "narrative" if external else "recorded",
                           "category": event.get("category") or event.get("phase")
                           or event.get("type"), "narrative_category": None,
                           "description": event.get("details", {}).get("summary")
                           or event.get("phase") or event.get("type"),
                           "workloads": [event["workload"]] if event.get("workload")
                           else base_event["workloads"],
                           "metrics": [event["metric"]] if event.get("metric")
                           else base_event["metrics"],
                           "scopes": [event["scope"]] if event.get("scope")
                           else base_event["scopes"], "refs": event.get("refs", [])})
    # Assign opaque equivalence classes without exporting hashes of private host values.
    groups: dict[object, str] = {}
    for point in sorted(points, key=lambda p: p["id"]):
        key = series_keys.get(point["id"])
        if key is not None:
            groups.setdefault(key, f"series-{len(groups) + 1}")
            point["series_id"] = groups[key]
    axis_series: dict[str, set[str]] = {}
    for point in points:
        if point["series_id"] is not None:
            axis_series.setdefault(point["axis_key"], set()).add(point["series_id"])
    for point in points:
        peers = axis_series.get(point["axis_key"], set())
        point["group_note"] = ("different recorded configuration; separate series"
                               if point["series_id"] is not None and len(peers) > 1 else None)
    for category in ("successes", "failures"):
        for index, entry in enumerate(story.get("summary", {}).get(category, [])):
            matches = [row for link in entry["links"] if link["ref"].startswith("candidate:")
                       for row in by_candidate.get(link["ref"][10:], [])]
            linked_ids = sorted({row["experiment_id"] for row in matches})
            positions = {row["round"] for row in matches}
            linked = [p for p in points if p["experiment_id"] in linked_ids]
            events.append({
                "id": stable_id(campaign_id, story.get("versions", [])[-1:], category, index),
                "category": category,
                "narrative_category": category, "description": entry["text"],
                "description_kind": "narrative",
                "round": next(iter(positions)) if len(positions) == 1 else None,
                "order": None, "timestamp": None, "experiment_ids": linked_ids,
                "workloads": sorted({p["workload"] for p in linked if p["workload"]}),
                "metrics": sorted({p["metric"] for p in linked if p["metric"]}),
                "scopes": sorted({p["scope"] for p in linked if p["scope"]}),
                "refs": entry["links"], "cause_stage": entry.get("cause_stage"),
                "quality": None, "verdict": None,
            })
    return {"schema_version": 1, "mode": "absolute", "points": points, "events": events}


def native_measurements(lock: dict, evaluation: dict, events: list[dict]) -> list[dict]:
    """The native adapter reads locked scope and the evaluator's absolute median."""
    from inferrsi.harness.records.evidence import sanitized_text

    from .dashboard_data import _number

    measured = evaluation.get("candidate", {})
    baseline = evaluation.get("baseline", {})
    measured = measured if isinstance(measured, dict) else {}
    baseline = baseline if isinstance(baseline, dict) else {}
    samples = measured.get("values")
    count = len(samples) if (isinstance(samples, list) and samples
                            and all(_number(v) is not None for v in samples)) else None
    unit = sanitized_text(evaluation.get("metric_unit") or lock.get("metric_unit"))
    specs = [{"id": "paired-baseline", "role": "local_baseline", "unit": unit,
              "value": _number(baseline.get("median")), "definition": "absolute",
              "provenance": "evaluation.json: baseline.median (paired native control)",
              "relative_to": "", "frozen": False}]
    target = _number(lock.get("min_improvement_pct"))
    if target is not None:
        specs.append({"id": "locked-target", "role": "frozen_target", "unit": unit,
                      "value": target, "definition": "improvement_pct", "frozen": True,
                      "provenance": "run.lock.json: min_improvement_pct",
                      "relative_to": "paired-baseline"})
    return [{
        "measurement_id": "candidate.median", "locator": "/candidate/median",
        "workload": sanitized_text(lock.get("workload_id")),
        "metric": sanitized_text(evaluation.get("metric_key") or lock.get("metric_key")),
        "unit": unit, "scope": sanitized_text(lock.get("comparison_scope")),
        "direction": evaluation.get("direction")
        if evaluation.get("direction") in ("minimize", "maximize") else None,
        "statistic": "median", "value": _number(measured.get("median")),
        "sample_count": count, "order": None,
        "timestamp": next((timestamp(e.get("time")) for e in events
                           if e.get("source") == "events" and e.get("side") == "candidate"
                           and e.get("phase") == "measurement"
                           and timestamp(e.get("time"))), None),
        "configuration": {"repetitions": lock.get("repetitions")
                          if type(lock.get("repetitions")) is int else None,
                          "required_trial_checks": [sanitized_text(v) for v in
                                                    lock.get("required_trial_checks", [])]
                          if isinstance(lock.get("required_trial_checks", []), list) else None},
        "comparison_reasons": [], "references": specs,
    }]
