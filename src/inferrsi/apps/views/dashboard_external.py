"""Explicit, hash-bound external records; never reinterpret a campaign verdict."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path


def external_record(root: Path, reference: object, candidate_id: str) -> tuple[dict, dict]:
    from inferrsi.harness.records.evidence import STAGES, sanitized_text

    from .dashboard_data import _explicit_ref, _number
    from .dashboard_experiments import external_dimensions

    ref = _explicit_ref(root, reference, "external_record")
    if ref["state"] != "present":
        return {}, ref
    try:
        raw = (root / ref["path"]).read_bytes()
        if len(raw) > 2 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != ref["sha256"]:
            raise ValueError("changed or oversized")
        data = json.loads(raw)
        if data.get("schema_version") != 1 or data.get("kind") != "external_optimization_record":
            raise ValueError("schema")
        if not all(isinstance(data.get(key), str) and data[key]
                   for key in ("backend", "protocol")):
            raise ValueError("backend and protocol required")
        if data.get("candidate_id") != candidate_id:
            raise ValueError("candidate identity")
        sources = data.get("source_refs", [])
        if not isinstance(sources, list) or not sources or len(sources) > 100:
            raise ValueError("source refs")
        sources = [_explicit_ref(root, source, "external_source") for source in sources]
        if any(source["state"] != "present" for source in sources):
            raise ValueError("missing source")
        if not isinstance(data.get("metrics", []), list) or not isinstance(
            data.get("events", []), list
        ):
            raise ValueError("collections")
        metrics = []
        for m in data.get("metrics", [])[:100]:
            if not isinstance(m, dict):
                raise ValueError("metric")
            samples = m.get("samples", [])
            if not isinstance(samples, list) or len(samples) > 2:
                raise ValueError("samples")
            samples = [_number(v) for v in samples]
            if any(v is None or v <= 0 for v in samples):
                raise ValueError("samples")
            aggregate = _number(m.get("aggregate"))
            for key in ("baseline", "aggregate", "target"):
                if m.get(key) is not None and (_number(m[key]) is None or _number(m[key]) <= 0):
                    raise ValueError("positive metric required")
            if m.get("aggregation") == "two_round_median":
                if (len(samples) != 2 or aggregate is None or not math.isclose(
                    aggregate, samples[0] / 2 + samples[1] / 2,
                    rel_tol=1e-9, abs_tol=1e-12
                )):
                    raise ValueError("two round aggregate")
            metrics.append(
                {
                    "plot": external_dimensions(m),
                    "name": sanitized_text(m.get("name")),
                    "unit": sanitized_text(m.get("unit")),
                    "samples": samples,
                    "aggregate": aggregate,
                    "aggregation": sanitized_text(m.get("aggregation")),
                    "baseline": _number(m.get("baseline")),
                    "target": _number(m.get("target")),
                }
            )
        events = []
        for i, e in enumerate(data.get("events", [])[:1000], 1):
            if e.get("stage") not in STAGES:
                raise ValueError("stage")
            time = e.get("time")
            if time is not None and (
                not isinstance(time, str) or not re.fullmatch(r"[0-9TtZz:+.\-]{10,40}", time)
            ):
                raise ValueError("time")
            events.append(
                {
                    "line": i,
                    "event_id": e.get("id") if isinstance(e.get("id"), str)
                    and e["id"] and sanitized_text(e["id"]) == e["id"] else None,
                    "workload": sanitized_text(e.get("workload"), "") or None,
                    "scope": sanitized_text(e.get("scope"), "") or None,
                    "metric": sanitized_text(e.get("metric"), "") or None,
                    "category": sanitized_text(e.get("category"), "") or None,
                    "time": time,
                    "phase": None,
                    "type": "external.record",
                    "stage": e["stage"],
                    "side": None,
                    "trial": None,
                    "tool": None,
                    "details": {"summary": sanitized_text(e.get("summary"), "", 1500)},
                    "source": "events",
                    "refs": [ref, *sources],
                }
            )
        verdict = data.get("performance_verdict")
        quality = data.get("quality", {})
        if quality.get("correct") is not None or quality.get("total") is not None:
            correct, total = quality.get("correct"), quality.get("total")
            if type(correct) is not int or type(total) is not int or not 0 <= correct <= total:
                raise ValueError("quality counts")
            if total <= 0:
                raise ValueError("quality total")
        environment = data.get("environment", {})
        required = ("hardware", "runtime", "model", "workload", "protocol", "source")
        identity_complete = data.get("backend") == "ascend" and all(
            isinstance(environment.get(k), str) and re.fullmatch(r"[0-9a-f]{64}", environment[k])
            for k in required
        )
        return {
            "backend": sanitized_text(data.get("backend")),
            "protocol": sanitized_text(data.get("protocol")),
            "metrics": metrics,
            "events": events,
            "source_refs": sources,
            "performance_verdict": verdict
            if verdict in ("PASS", "FAIL", "INCONCLUSIVE")
            else "not_recorded",
            "quality_verdict": quality.get("verdict")
            if quality.get("verdict") in ("PASS", "FAIL", "INCONCLUSIVE", "NOT_RUN")
            else "not_recorded",
            "quality_correct": _number(quality.get("correct")),
            "quality_total": _number(quality.get("total")),
            "state": data.get("state")
            if data.get("state") in ("running", "completed", "failed", "crashed", "cancelled")
            else "not_recorded",
            "note": sanitized_text(data.get("note"), "", 2000),
            "identity_state": "recorded" if identity_complete else "incomplete",
            "comparison_state": "protocol_specific",
            "provenance": "Caller-adapted records; hashes check bytes, not experimental validity.",
        }, ref
    except (ValueError, TypeError, AttributeError, KeyError, OSError):
        return {}, {**ref, "state": "missing", "missing_reason": "corrupt"}


def metric_chart(rows: list[dict]) -> str:
    """Plot absolute metrics in separate axes, never rank distinct protocols."""
    from html import escape

    items = [(r, m) for r in rows for m in r["external"]["metrics"]][:100]
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" '
        f'height="{len(items) * 100 + 30}" role="img" aria-label="Protocol measurements">'
    ]
    for i, (row, metric) in enumerate(items):
        y = i * 100 + 25
        samples = metric["samples"]
        roles = [("Parent", "#a0aab7", metric["baseline"]),
                 ("R1", "#5794f2", samples[0] if samples else None),
                 ("R2", "#ff9830", samples[1] if len(samples) > 1 else None),
                 ("Aggregate", "#73bf69", metric["aggregate"])]
        values = [value for _, _, value in roles]
        numbers = [v for v in values + [metric["target"]] if v is not None and v > 0]
        if not numbers:
            continue
        maximum = max(numbers)
        label = escape(f"{row['title']} · {metric['name']} ({metric['unit']})")
        parts.append(f'<text x="10" y="{y}" fill="#e2e6eb">{label}</text>')
        for j, (label, colour, v) in enumerate(roles):
            if v is None or v <= 0:
                continue
            x = 280 + 650 * v / maximum
            parts.append(
                f'<text x="10" y="{y + 16 + j * 16}" fill="{colour}">{label}: {v:.4f}</text>'
                f'<line x1="280" y1="{y + 12 + j * 16}" x2="{x}" '
                f'y2="{y + 12 + j * 16}" stroke="{colour}" stroke-width="5"/>'
            )
        if metric["target"] is not None and metric["target"] > 0:
            x = 280 + 650 * metric["target"] / maximum
            parts.append(
                f'<line x1="{x}" x2="{x}" y1="{y}" y2="{y + 70}" '
                'stroke="#fff" stroke-dasharray="3 3"/>'
            )
    return "".join(parts) + "</svg>"
