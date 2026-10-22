#!/usr/bin/env python3
"""Render a campaign gain summary figure from a JSON specification.

Two layouts answer two different campaign shapes:

``chain``
    Ordered steps that accumulate on each other. Each step is measured against
    the original baseline, so the plotted line is the running gain and the
    height of a step is what that step added. This is the "gain over time"
    figure a finished RSI campaign publishes.

``branch``
    Independent trials that each start from the same baseline. Every row shows
    its own gain, so a trial that produced no gain or lost ground is as visible
    as the best result.

Both layouts use only the standard library and write SVG, so a committed figure
reproduces without a plotting dependency. ``spec_from_evaluation`` builds a
spec from one recorded run, which is what the report generator uses at the end
of an experiment.

Specification shape (see ``evidence/_template/results/summary-chart.example.json``)::

    {
      "title": "Engine end-to-end throughput",
      "layout": "chain",                    # chain (default when points) or branch
      "phases": ["Bring-up", "Kernels"],    # chain only: labelled stage bands
      "unit": "frames/s",
      "baseline": {"label": "main snapshot", "metrics": {"C16": 513.3, "C32": 540.2}},
      "metrics": [{"key": "C16", "label": "C16"}, {"key": "C32", "label": "C32"}],
      "label_metric": "C32",
      "points": [                            # chain only: ordered accumulating steps
        {"phase": "Bring-up", "label": "async scheduling",
         "values": {"C16": 620.0, "C32": 651.0}, "note": "whole pipeline"},
      ],
      "references": [{"label": "peer target", "metric": "C32", "value": 2544.1}],
      "trials": [                            # branch only: independent screens
        {"group": "Kernel", "label": "fused quantization",
         "values": {"C16": 826.0, "C32": 857.7}, "status": "open", "note": "single screen"}
      ]
    }

A chain specification needs an explicit baseline step, either as
``points[0]`` with ``"baseline": true`` or through ``baseline.metrics`` alone;
the renderer always draws the baseline at 1.00x so a step can be read against
the starting point.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from xml.sax.saxutils import escape

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
INK_3 = "#8a8984"
BAND = "#f1f1ee"
GRID = "#e4e3df"
AXIS = "#52514e"
REFERENCE = "#52514e"

# Fixed hue order. A campaign with more series than slots is split into
# separate figures rather than given generated hues.
SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6")

# Conventional dispositions. A spec may add or override entries; an unknown
# status renders plainly instead of failing the render.
STATUS_STYLES = {
    "gain": {"mark": "", "strong": True},
    "open": {"mark": "", "strong": False},
    "flat": {"mark": "×", "strong": False},
    "regressed": {"mark": "×", "strong": False},
}

FONT = "system-ui,-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif"

ROW_HEIGHT = 26.0
HEADER_HEIGHT = 118.0
FOOTER_HEIGHT = 62.0
PLOT_WIDTH = 860.0
GROUP_SIZE = 9.6
MARGIN = 24.0


class SpecError(ValueError):
    """The specification cannot be rendered as written."""


def _text_width(text: str, size: float) -> float:
    """Approximate advance width of one line in the UI stack."""
    return len(text) * size * 0.58


def _number(value: object, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpecError(f"{where} must be a number, got {value!r}")
    if not math.isfinite(value):
        raise SpecError(f"{where} must be finite, got {value!r}")
    return float(value)


def _finite(values: dict[str, list[float]], where: str) -> dict[str, list[float]]:
    """Reject ratios that overflow, so a broken scale fails instead of crashing."""
    for key, items in values.items():
        if any(not math.isfinite(value) for value in items):
            raise SpecError(f"{where} for {key} is not finite; check the metric scale")
    return values


def _text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpecError(f"{where} must be a non-empty string, got {value!r}")
    return value.strip()


def _metric_keys(spec: dict) -> list[str]:
    metrics = spec.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        raise SpecError("metrics must be a non-empty list")
    keys = []
    for index, metric in enumerate(metrics):
        if not isinstance(metric, dict):
            raise SpecError(f"metrics[{index}] must be an object")
        key = _text(metric.get("key"), f"metrics[{index}].key")
        if key in keys:
            raise SpecError(f"duplicate metric key: {key}")
        keys.append(key)
    if len(keys) > len(SERIES):
        raise SpecError(f"at most {len(SERIES)} metrics fit one figure; got {len(keys)}")
    return keys


def _baseline(spec: dict, keys: list[str]) -> dict[str, float]:
    baseline = spec.get("baseline")
    if not isinstance(baseline, dict):
        raise SpecError("baseline must be an object with a metrics map")
    values = baseline.get("metrics")
    if not isinstance(values, dict):
        raise SpecError("baseline.metrics must be an object")
    resolved = {}
    for key in keys:
        if key not in values:
            raise SpecError(f"baseline.metrics is missing metric: {key}")
        number = _number(values[key], f"baseline.metrics.{key}")
        if number <= 0:
            raise SpecError(f"baseline.metrics.{key} must be positive, got {number}")
        resolved[key] = number
    return resolved


def _statuses(spec: dict) -> dict[str, dict]:
    styles = {name: dict(style) for name, style in STATUS_STYLES.items()}
    overrides = spec.get("statuses", {})
    if not isinstance(overrides, dict):
        raise SpecError("statuses must be an object")
    for name, style in overrides.items():
        if not isinstance(style, dict):
            raise SpecError(f"statuses.{name} must be an object")
        merged = styles.setdefault(name, {"mark": "", "strong": False})
        if "mark" in style:
            merged["mark"] = str(style["mark"])
        if "strong" in style:
            merged["strong"] = bool(style["strong"])
    return styles


def _trials(spec: dict, keys: list[str]) -> list[dict]:
    trials = spec.get("trials")
    if not isinstance(trials, list) or not trials:
        raise SpecError("trials must be a non-empty list")
    seen: set[tuple[str, str]] = set()
    resolved = []
    for index, trial in enumerate(trials):
        if not isinstance(trial, dict):
            raise SpecError(f"trials[{index}] must be an object")
        group = _text(trial.get("group"), f"trials[{index}].group")
        label = _text(trial.get("label"), f"trials[{index}].label")
        if (group, label) in seen:
            raise SpecError(f"duplicate trial in group {group!r}: {label!r}")
        seen.add((group, label))
        values = trial.get("values")
        if not isinstance(values, dict):
            raise SpecError(f"trials[{index}].values must be an object")
        numbers = {}
        for key in keys:
            if key not in values:
                raise SpecError(f"trials[{index}].values is missing metric: {key}")
            numbers[key] = _number(values[key], f"trials[{index}].values.{key}")
        status = str(trial.get("status", "open"))
        note = str(trial.get("note", "")).strip()
        resolved.append(
            {"group": group, "label": label, "values": numbers, "status": status, "note": note}
        )
    return resolved


def _references(spec: dict, keys: list[str]) -> list[dict]:
    references = spec.get("references", [])
    if not isinstance(references, list):
        raise SpecError("references must be a list")
    resolved = []
    for index, reference in enumerate(references):
        if not isinstance(reference, dict):
            raise SpecError(f"references[{index}] must be an object")
        metric = _text(reference.get("metric"), f"references[{index}].metric")
        if metric not in keys:
            raise SpecError(f"references[{index}].metric is not a declared metric: {metric}")
        resolved.append(
            {
                "label": _text(reference.get("label"), f"references[{index}].label"),
                "metric": metric,
                "value": _number(reference.get("value"), f"references[{index}].value"),
            }
        )
    return resolved


def _ordered(trials: list[dict], keys: list[str], spec: dict) -> list[dict]:
    groups: list[str] = []
    for trial in trials:
        if trial["group"] not in groups:
            groups.append(trial["group"])
    order = {group: index for index, group in enumerate(groups)}
    sort = spec.get("sort", "gain")
    if sort not in {"gain", "given"}:
        raise SpecError(f"sort must be 'gain' or 'given', got {sort!r}")
    if sort == "given":
        return sorted(trials, key=lambda trial: order[trial["group"]])
    label_metric = _label_metric(spec, keys)
    return sorted(
        trials,
        key=lambda trial: (order[trial["group"]], trial["values"][label_metric]),
    )


def _label_metric(spec: dict, keys: list[str]) -> str:
    label_metric = spec.get("label_metric", keys[-1])
    if label_metric not in keys:
        raise SpecError(f"label_metric is not a declared metric: {label_metric}")
    return label_metric


def _status_text(trial: dict) -> str:
    if trial["note"]:
        return f"{trial['status']} — {trial['note']}"
    return trial["status"]


def _format_value(value: float) -> str:
    return f"{value:,.0f}" if abs(value - round(value)) < 0.05 else f"{value:,.1f}"


def _svg_text(x: float, y: float, text: str, size: float, **attrs: object) -> str:
    pieces = [
        f'x="{x:.1f}"',
        f'y="{y:.1f}"',
        f'font-size="{size:.1f}"',
        f'font-family="{FONT}"',
    ]
    for name, value in attrs.items():
        key = name.replace("_", "-")
        if isinstance(value, bool):
            continue
        pieces.append(f'{key}="{value}"')
    return f"<text {' '.join(pieces)}>{escape(text)}</text>"


def _fit_rotated(text: str, room: float) -> str:
    """Shorten a rotated label so its height stays inside ``room`` points."""
    size, spacing = 10.2, 0.60
    if _text_width(text, size) * spacing <= room:
        return text
    keep = max(3, int(room / (size * spacing)) - 1)
    return text if len(text) <= keep else text[: keep - 1].rstrip() + "…"


def build_svg(spec: dict) -> str:
    """Return the complete SVG document for one specification."""
    layout = str(spec.get("layout", "branch" if spec.get("trials") else "chain"))
    if layout == "chain":
        return _build_chain(spec)
    if layout == "branch":
        return _build_branch(spec)
    raise SpecError(f"layout must be 'chain' or 'branch', got {layout!r}")

def _points(spec: dict, keys: list[str]) -> list[dict]:
    points = spec.get("points")
    if not isinstance(points, list) or not points:
        raise SpecError("a chain layout needs a non-empty points list")
    resolved = []
    for index, point in enumerate(points):
        if not isinstance(point, dict):
            raise SpecError(f"points[{index}] must be an object")
        values = point.get("values")
        if not isinstance(values, dict):
            raise SpecError(f"points[{index}].values must be an object")
        numbers = {}
        for key in keys:
            if key not in values:
                raise SpecError(f"points[{index}].values is missing metric: {key}")
            numbers[key] = _number(values[key], f"points[{index}].values.{key}")
        resolved.append(
            {
                "phase": str(point.get("phase", "")).strip(),
                "label": _text(point.get("label"), f"points[{index}].label"),
                "values": numbers,
                "note": str(point.get("note", "")).strip(),
                "baseline": bool(point.get("baseline", False)),
            }
        )
    if sum(1 for point in resolved if point["baseline"]) > 1:
        raise SpecError("at most one point may be marked baseline")
    return resolved


def _phase_spans(points: list[dict], phases: list[str]) -> list[tuple[str, int, int]]:
    """Group consecutive points into phase bands; a named order wins when given."""
    if phases:
        unknown = {point["phase"] for point in points} - set(phases)
        if unknown:
            raise SpecError(f"phases listed by a point but not declared: {sorted(unknown)}")
        spans = []
        for phase in phases:
            indexes = [index for index, point in enumerate(points) if point["phase"] == phase]
            if indexes:
                spans.append((phase, min(indexes), max(indexes)))
        return spans
    spans = []
    for index, point in enumerate(points):
        if spans and spans[-1][0] == point["phase"]:
            name, start, _ = spans[-1]
            spans[-1] = (name, start, index)
        else:
            spans.append((point["phase"], index, index))
    return spans


CHAIN_WIDTH = 1040.0
CHAIN_LEFT = 96.0
CHAIN_RIGHT = 240.0
CHAIN_TOP_BAND = 34.0
CHAIN_PLOT_HEIGHT = 400.0


def _build_chain(spec: dict) -> str:
    """Ordered accumulating steps on a multiple-of-baseline axis."""
    keys = _metric_keys(spec)
    baseline = _baseline(spec, keys)
    points = _points(spec, keys)
    references = _references(spec, keys)
    label_metric = _label_metric(spec, keys)
    unit = str(spec.get("unit", "")).strip()
    axis = spec.get("axis", {}) if isinstance(spec.get("axis", {}), dict) else {}
    phases = [str(item) for item in spec.get("phases", [])]

    multiples = _finite(
        {key: [point["values"][key] / baseline[key] for point in points] for key in keys},
        "the measured multiple",
    )
    reference_multiples = [
        reference["value"] / baseline[reference["metric"]] for reference in references
    ]
    if any(not math.isfinite(value) for value in reference_multiples):
        raise SpecError("a reference value is not finite against its baseline")
    lowest = min([1.0, *[min(values) for values in multiples.values()], *reference_multiples])
    highest = max([1.0, *[max(values) for values in multiples.values()], *reference_multiples])
    step = float(axis.get("step", 0.5))
    floor = max(0.0, math.floor(lowest / step) * step)
    ceiling = math.ceil(highest / step) * step
    if ceiling <= floor:
        raise SpecError("the chain has no vertical span; check the recorded values")

    spans = _phase_spans(points, phases)
    span = CHAIN_WIDTH - CHAIN_LEFT - CHAIN_RIGHT
    slot = span / (len(points) - 1) if len(points) > 1 else 0.0

    header_lines = [str(spec.get("title", "Campaign gain summary"))]
    subtitle = spec.get("subtitle", [])
    if isinstance(subtitle, str):
        subtitle = [subtitle]
    control = spec.get("baseline", {}).get("label")
    if control:
        header_lines.append(f"baseline: {control}")
    header_lines.extend(str(line) for line in subtitle)
    plot_top = 40.0 + 18.0 * len(header_lines) + CHAIN_TOP_BAND
    plot_bottom = plot_top + CHAIN_PLOT_HEIGHT

    label_rows = [_point_label(point, label_metric, unit) for point in points]
    label_w = max(_text_width(entry[0], 9.0) for entry in label_rows) + 16.0
    height = plot_bottom + 78.0

    def x_of(index: int) -> float:
        return CHAIN_LEFT + index * slot

    def y_of(multiple: float) -> float:
        return plot_bottom - (multiple - floor) / (ceiling - floor) * CHAIN_PLOT_HEIGHT

    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CHAIN_WIDTH + label_w:.0f}" '
        f'height="{height:.0f}" viewBox="0 0 {CHAIN_WIDTH + label_w:.0f} {height:.0f}" '
        f'role="img">',
        f"<title>{escape(header_lines[0])}</title>",
        f'<rect width="{CHAIN_WIDTH + label_w:.0f}" height="{height:.0f}" fill="{SURFACE}"/>',
        _svg_text(MARGIN, 38.0, header_lines[0], 16.5, fill=INK, font_weight="bold"),
    ]
    line_y = 62.0
    for line in header_lines[1:]:
        parts.append(_svg_text(MARGIN, line_y, line, 9.4, fill=INK_2))
        line_y += 16.0

    # phase bands behind the plot, labelled above it
    for position, (name, start, end) in enumerate(spans):
        left = x_of(start) - (slot / 2 if len(points) > 1 else 60.0)
        right = x_of(end) + (slot / 2 if len(points) > 1 else 60.0)
        left = max(CHAIN_LEFT - 30.0, left)
        right = min(CHAIN_WIDTH - CHAIN_RIGHT + 30.0, right)
        if position % 2 == 0:
            parts.append(
                f'<rect x="{left:.1f}" y="{plot_top:.1f}" width="{right - left:.1f}" '
                f'height="{CHAIN_PLOT_HEIGHT:.1f}" fill="{BAND}"/>'
            )
        parts.append(
            _svg_text(
                (left + right) / 2,
                plot_top - 12.0,
                name,
                10.4,
                fill=INK_2,
                font_weight="bold",
                text_anchor="middle",
            )
        )

    legend = "   ".join(metric_label(spec, key) for key in keys)
    swatch_x = CHAIN_WIDTH - CHAIN_RIGHT - _text_width(legend, 9.4) - 12.0 * len(keys)
    for slot_index, key in enumerate(keys):
        parts.append(
            f'<circle cx="{swatch_x + 12.0 * slot_index:.1f}" cy="34.0" '
            f'r="4" fill="{SERIES[slot_index]}"/>'
        )
    parts.append(_svg_text(swatch_x + 12.0 * len(keys), 37.0, legend, 9.4, fill=INK_2))

    # horizontal gridlines with a multiple label on the left
    tick = floor
    while tick <= ceiling + 1e-9:
        y = y_of(tick)
        parts.append(
            f'<line x1="{CHAIN_LEFT - 12.0:.1f}" y1="{y:.1f}" '
            f'x2="{CHAIN_WIDTH - CHAIN_RIGHT + 12.0:.1f}" y2="{y:.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        parts.append(
            _svg_text(
                CHAIN_LEFT - 18.0,
                y,
                f"{tick:.2f}×".rstrip("0").rstrip(".") + "×" if False else _multiple_label(tick),
                8.6,
                fill=INK_3,
                text_anchor="end",
                dominant_baseline="middle",
            )
        )
        tick += step

    # one polyline per metric, with a marker and its running gain above each point
    for slot_index, key in enumerate(keys):
        path = " ".join(
            f"{x_of(index):.1f},{y_of(value):.1f}" for index, value in enumerate(multiples[key])
        )
        parts.append(
            f'<polyline points="{path}" fill="none" stroke="{SERIES[slot_index]}" '
            f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        )
        for index, value in enumerate(multiples[key]):
            x, y = x_of(index), y_of(value)
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.2" fill="{SERIES[slot_index]}" '
                f'stroke="{SURFACE}" stroke-width="1.4"/>'
            )

    # reference lines continue past the last step as a dashed projection
    for index, reference in enumerate(references):
        y = y_of(reference_multiples[index])
        parts.append(
            f'<line x1="{CHAIN_LEFT - 12.0:.1f}" y1="{y:.1f}" x2="{x_of(len(points) - 1):.1f}" '
            f'y2="{y:.1f}" stroke="{REFERENCE}" stroke-width="1.4" stroke-dasharray="6 4"/>'
        )
        parts.append(
            _svg_text(
                x_of(len(points) - 1) + 10.0,
                y,
                reference["label"],
                8.8,
                fill=INK_2,
                font_style="italic",
                dominant_baseline="middle",
            )
        )

    # direct labels: gain multiple above the line, step name below
    for index, point in enumerate(points):
        x = x_of(index)
        value = multiples[label_metric][index]
        y = y_of(value)
        parts.append(
            _svg_text(
                x,
                y - 14.0,
                f"{value:.2f}×",
                10.6,
                fill=INK,
                font_weight="bold",
                text_anchor="middle",
            )
        )
        parts.append(
            _svg_text(
                x,
                plot_bottom + 22.0,
                point["label"],
                9.0,
                fill=INK_2,
                text_anchor="middle",
            )
        )
        note = _point_note(point, label_rows[index])
        if note:
            parts.append(
                _svg_text(
                    x,
                    plot_bottom + 38.0,
                    note,
                    8.2,
                    fill=INK_3,
                    text_anchor="middle",
                )
            )
        parts.append(
            _svg_text(
                x, plot_bottom + 54.0, f"T+{index}", 8.4, fill=INK_3, text_anchor="middle"
            )
        )

    axis_label = str(axis.get("label", "")).strip()
    if axis_label:
        parts.append(
            _svg_text(
                (CHAIN_LEFT + CHAIN_WIDTH - CHAIN_RIGHT) / 2,
                plot_bottom + 74.0,
                axis_label,
                9.6,
                fill=INK_2,
                text_anchor="middle",
            )
        )
    y_label = str(axis.get("y_label", "")).strip()
    if y_label:
        pivot = MARGIN - 4.0
        parts.append(
            _svg_text(
                pivot,
                (plot_top + plot_bottom) / 2,
                y_label,
                9.4,
                fill=INK_2,
                text_anchor="middle",
                transform=f"rotate(-90 {pivot:.1f} {(plot_top + plot_bottom) / 2:.1f})",
            )
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _multiple_label(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{text}×"


def _point_label(point: dict, label_metric: str, unit: str) -> tuple[str, str]:
    """Return the step name and its absolute measurement for the axis footer."""
    absolute = point["values"][label_metric]
    text = f"{absolute:,.0f}" if abs(absolute - round(absolute)) < 0.05 else f"{absolute:,.1f}"
    return (point["label"], f"{text} {unit}".strip())


def _point_note(point: dict, label_row: tuple[str, str]) -> str:
    detail = label_row[1]
    if point["note"]:
        return f"{point['note']} · {detail}" if detail else point["note"]
    return detail


def _build_branch(spec: dict) -> str:
    """Independent trials on one signed gain axis."""
    keys = _metric_keys(spec)
    baseline = _baseline(spec, keys)
    statuses = _statuses(spec)
    trials = _ordered(_trials(spec, keys), keys, spec)
    references = _references(spec, keys)
    label_metric = _label_metric(spec, keys)
    unit = str(spec.get("unit", "")).strip()
    tick = float(spec.get("axis", {}).get("tick", 50))

    gains = _finite(
        {
            key: [(trial["values"][key] / baseline[key] - 1.0) * 100.0 for trial in trials]
            for key in keys
        },
        "the measured gain",
    )
    reference_gains = [
        (reference["value"] / baseline[reference["metric"]] - 1.0) * 100.0
        for reference in references
    ]

    low = min([0.0, *[min(values) for values in gains.values()], *reference_gains])
    high = max([0.0, *[max(values) for values in gains.values()], *reference_gains])
    x_min = math.floor(low / tick) * tick
    x_max = math.ceil(high / tick) * tick
    if x_max <= x_min:
        raise SpecError("every trial sits at zero gain; the figure would have no span")

    legend = "  ".join(metric_label(spec, key) for key in keys)
    control = spec.get("baseline", {}).get("label")
    header_lines = [str(spec.get("title", "Campaign gain summary"))]
    subtitle = spec.get("subtitle", [])
    if isinstance(subtitle, str):
        subtitle = [subtitle]
    if control:
        header_lines.append(f"baseline: {control}")
    header_lines.extend(str(line) for line in subtitle)
    plot_top = 40.0 + 18.0 * len(header_lines) + CHAIN_TOP_BAND
    plot_bottom = plot_top + CHAIN_PLOT_HEIGHT

    group_w = max(_text_width(trial["group"], GROUP_SIZE) for trial in trials) + 14.0
    label_w = max(
        [_text_width(line, 9.8) for line in header_lines[1:]]
        + [_text_width(trial["label"], 9.8) for trial in trials]
    ) + 18.0
    value_texts = []
    for index, trial in enumerate(trials):
        gain = gains[label_metric][index]
        text = f"{gain:+.1f}%   {_format_value(trial['values'][label_metric])}"
        if unit:
            text = f"{text} {unit}"
        losses = [
            f"{metric_label(spec, key)} {gains[key][index]:+.1f}%"
            for key in keys
            if key != label_metric and gains[key][index] < 0
        ]
        value_texts.append(text + ("  (" + ", ".join(losses) + ")" if losses else ""))
    value_w = max(_text_width(text, 9.4) for text in value_texts) + 26.0
    note_texts = [_status_text(trial) for trial in trials]
    note_w = max(_text_width(text, 8.4) for text in note_texts) + 20.0

    plot_x = MARGIN + group_w + label_w
    plot_right = plot_x + PLOT_WIDTH
    value_x = plot_right + 10.0
    note_x = value_x + value_w
    width = note_x + note_w + MARGIN
    height = HEADER_HEIGHT + len(trials) * ROW_HEIGHT + FOOTER_HEIGHT

    def x_of(gain: float) -> float:
        span = x_max - x_min
        return plot_x + (gain - x_min) / span * PLOT_WIDTH

    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" role="img">',
        f"<title>{escape(header_lines[0])}</title>",
        f'<rect width="{width:.0f}" height="{height:.0f}" fill="{SURFACE}"/>',
        _svg_text(MARGIN, 40.0, header_lines[0], 16.5, fill=INK, font_weight="bold"),
    ]

    line_y = 66.0
    for line in header_lines[1:]:
        parts.append(_svg_text(MARGIN, line_y, line, 9.4, fill=INK_2))
        line_y += 15.0

    plot_top = HEADER_HEIGHT
    plot_bottom = plot_top + len(trials) * ROW_HEIGHT

    groups: list[tuple[str, int, int]] = []
    for index, trial in enumerate(trials):
        if groups and groups[-1][0] == trial["group"]:
            name, start, _ = groups[-1]
            groups[-1] = (name, start, index)
        else:
            groups.append((trial["group"], index, index))

    for position, (name, start, end) in enumerate(groups):
        top = plot_top + start * ROW_HEIGHT
        bottom = plot_top + (end + 1) * ROW_HEIGHT
        if position % 2 == 0:
            parts.append(
                f'<rect x="{plot_x:.1f}" y="{top:.1f}" width="{PLOT_WIDTH:.1f}" '
                f'height="{bottom - top:.1f}" fill="{BAND}"/>'
            )
        parts.append(
            _svg_text(
                MARGIN,
                top + ROW_HEIGHT / 2,
                name,
                GROUP_SIZE,
                fill=INK_2,
                font_weight="bold",
                dominant_baseline="middle",
            )
        )

    gain_ticks = []
    current = x_min
    while current <= x_max + 1e-9:
        gain_ticks.append(current)
        current += tick
    for gain in gain_ticks:
        x = x_of(gain)
        parts.append(
            f'<line x1="{x:.1f}" y1="{plot_top:.1f}" x2="{x:.1f}" y2="{plot_bottom:.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        parts.append(
            _svg_text(
                x,
                plot_top - 8.0,
                f"{gain:+.0f}%" if gain else "0%",
                8.2,
                fill=INK_3,
                text_anchor="middle",
            )
        )

    zero_x = x_of(0.0)
    parts.append(
        f'<line x1="{zero_x:.1f}" y1="{plot_top:.1f}" x2="{zero_x:.1f}" y2="{plot_bottom:.1f}" '
        f'stroke="{AXIS}" stroke-width="1.1"/>'
    )

    # Two references close together stagger downwards instead of overprinting.
    reference_offsets = [0] * len(references)
    for index in range(1, len(references)):
        previous = x_of(reference_gains[index - 1])
        if x_of(reference_gains[index]) - previous < 180.0:
            reference_offsets[index] = reference_offsets[index - 1] + 1

    for index, reference in enumerate(references):
        gain = reference_gains[index]
        x = x_of(gain)
        parts.append(
            f'<line x1="{x:.1f}" y1="{plot_top:.1f}" x2="{x:.1f}" y2="{plot_bottom:.1f}" '
            f'stroke="{REFERENCE}" stroke-width="1.5" stroke-dasharray="5 3"/>'
        )
        parts.append(
            _svg_text(
                x + 4.0,
                plot_bottom + 16.0 + 12.0 * reference_offsets[index],
                reference["label"],
                8.6,
                fill=INK_2,
                font_style="italic",
            )
        )

    for index, trial in enumerate(trials):
        center = plot_top + index * ROW_HEIGHT + ROW_HEIGHT / 2
        style = statuses.get(trial["status"], {"mark": "", "strong": False})
        xs = [x_of(gains[key][index]) for key in keys]
        if len(xs) > 1:
            parts.append(
                f'<line x1="{min(xs):.1f}" y1="{center:.1f}" x2="{max(xs):.1f}" '
                f'y2="{center:.1f}" stroke="{GRID}" stroke-width="4" stroke-linecap="round"/>'
            )
        for slot, key in enumerate(keys):
            parts.append(
                f'<circle cx="{x_of(gains[key][index]):.1f}" cy="{center:.1f}" r="'
                f"{4.6 if key == label_metric else 3.8:.1f}\" fill=\"{SERIES[slot]}\" "
                f'stroke="{SURFACE}" stroke-width="1.2"/>'
            )
        value_text = value_texts[index] + (f"  {style['mark']}" if style["mark"] else "")
        parts.append(
            _svg_text(
                value_x,
                center,
                value_text,
                9.4,
                fill=INK,
                dominant_baseline="middle",
                font_weight="bold" if style["strong"] else "normal",
            )
        )
        parts.append(
            _svg_text(
                note_x,
                center,
                note_texts[index],
                8.4,
                fill=INK_2,
                dominant_baseline="middle",
            )
        )
        parts.append(
            _svg_text(
                plot_x - 12.0,
                center,
                trial["label"],
                9.8,
                fill=INK,
                text_anchor="end",
                dominant_baseline="middle",
            )
        )

    swatch_x = plot_right - _text_width(legend, 9.4) - 12.0 * len(keys)
    for slot, key in enumerate(keys):
        parts.append(
            f'<circle cx="{swatch_x + 12.0 * slot:.1f}" cy="{plot_top - 27.0:.1f}" r="4" '
            f'fill="{SERIES[slot]}"/>'
        )
    parts.append(
        _svg_text(
            swatch_x + 12.0 * len(keys),
            plot_top - 24.0,
            legend,
            9.4,
            fill=INK_2,
        )
    )
    axis_label = str(spec.get("axis", {}).get("label", "")).strip()
    if axis_label:
        parts.append(
            _svg_text(
                (plot_x + plot_right) / 2,
                plot_bottom + 34.0,
                axis_label,
                9.6,
                fill=INK_2,
                text_anchor="middle",
            )
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def spec_from_evaluation(evaluation: dict, *, title: str | None = None) -> dict:
    """Build a one-step chain specification from one recorded evaluation.

    A single run has one baseline and one candidate, so the figure shows the
    recorded pair as a two-point chain: the baseline at 1.00x and the measured
    candidate. Nothing is inferred beyond the evaluation's own numbers.
    """
    if not isinstance(evaluation, dict):
        raise SpecError("evaluation must be an object")
    before = evaluation.get("baseline") or {}
    after = evaluation.get("candidate") or {}
    baseline_value = before.get("median")
    candidate_value = after.get("median")
    numbers = (baseline_value, candidate_value)
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in numbers):
        raise SpecError("evaluation has no paired medians to plot")
    if not baseline_value:
        raise SpecError("baseline median is zero; a ratio figure is undefined")
    unit = str(evaluation.get("metric_unit", "")).strip()
    direction = str(evaluation.get("direction", "minimize"))
    key = str(evaluation.get("metric_key", "metric")).split(".")[-1]
    label = f"{key} ({unit})" if unit else key
    verdict = str(evaluation.get("verdict", "INCONCLUSIVE"))
    improvement = evaluation.get("improvement_pct")
    note = f"verdict {verdict}"
    if isinstance(improvement, (int, float)):
        note = f"{improvement:+.1f}% · {note}"
    return {
        "title": title or f"Recorded experiment: {key}",
        "layout": "chain",
        "phases": ["Baseline", "Candidate"],
        "unit": unit,
        "baseline": {"label": "recorded baseline trials", "metrics": {label: baseline_value}},
        "metrics": [{"key": label, "label": label}],
        "label_metric": label,
        "axis": {
            "step": 0.25,
            "label": f"Paired trials, {'higher' if direction == 'maximize' else 'lower'} is better",
            "y_label": "Measured value vs baseline",
        },
        "subtitle": [
            evaluation.get("measurement_method", "Alternating AB/BA sequential trials."),
            "Descriptive only; statistical significance "
            f"{evaluation.get('statistical_significance', 'not established')}.",
        ],
        "points": [
            {
                "phase": "Baseline",
                "label": "baseline",
                "values": {label: baseline_value},
                "baseline": True,
                "note": "recorded",
            },
            {
                "phase": "Candidate",
                "label": "candidate",
                "values": {label: candidate_value},
                "note": note,
            },
        ],
    }


def write_chart(spec: dict, destination) -> Path:
    """Render ``spec`` to ``destination`` and return the written path."""
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_svg(spec), encoding="utf-8")
    return path


def metric_label(spec: dict, key: str) -> str:
    for metric in spec.get("metrics", []):
        if metric.get("key") == key:
            return str(metric.get("label", key))
    return key


def build_markdown(spec: dict) -> str:
    """Return a Markdown table carrying the same values as the figure.

    A branch spec lists independent trials; a chain spec lists ordered steps and
    their running multiple, which is what the line figure plots.
    """
    keys = _metric_keys(spec)
    baseline = _baseline(spec, keys)
    label_metric = _label_metric(spec, keys)
    unit = str(spec.get("unit", "")).strip()
    unit_note = f" ({unit})" if unit else ""
    layout = str(spec.get("layout", "branch" if spec.get("trials") else "chain"))
    if layout == "chain":
        rows = [
            (
                [point["phase"], point["label"]]
                + [_format_value(point["values"][key]) for key in keys]
                + [
                    f"{point['values'][key] / baseline[key]:.2f}\u00d7" for key in keys
                ]
                + [point["note"]]
            )
            for point in _points(spec, keys)
        ]
        head = ["Stage", "Step"]
    else:
        rows = [
            (
                [trial["group"], trial["label"]]
                + [_format_value(trial["values"][key]) for key in keys]
                + [
                    f"{(trial['values'][key] / baseline[key] - 1.0) * 100.0:+.1f}%"
                    for key in keys
                ]
                + [_status_text(trial)]
            )
            for trial in _ordered(_trials(spec, keys), keys, spec)
        ]
        head = ["Group", "Trial"]
    changed = "gain" if layout == "branch" else "multiple"
    head += [f"{metric_label(spec, key)}{unit_note}" for key in keys]
    head += [f"{metric_label(spec, key)} {changed}" for key in keys]
    head.append("Note" if layout == "chain" else "Disposition")
    lines = [
        "| " + " | ".join(head) + " |",
        "| " + " | ".join("---" for _ in head) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |")
    caption = str(spec.get("title", "")).strip()
    if caption:
        lines.insert(0, f"**{caption}**")
        lines.insert(1, "")
    control = spec.get("baseline", {}).get("label", "baseline")
    note = f"Values are measured against the {control}"
    if layout == "chain":
        note += "; the multiple is the running gain at that step."
    else:
        note += f"; the {metric_label(spec, label_metric)} gain orders each group."
    lines += ["", note]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a campaign gain summary figure from a JSON specification."
    )
    parser.add_argument("spec", type=Path, help="JSON campaign specification")
    parser.add_argument("-o", "--output", type=Path, help="SVG destination")
    parser.add_argument("--markdown", type=Path, help="also write a Markdown table here")
    arguments = parser.parse_args(argv)

    try:
        spec = json.loads(arguments.spec.read_text(encoding="utf-8"))
        if not isinstance(spec, dict):
            raise SpecError("specification must be a JSON object")
        svg = build_svg(spec)
        table = build_markdown(spec) if arguments.markdown else None
    except SpecError as error:
        print(f"specification error: {error}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as error:
        print(f"invalid JSON: {error}", file=sys.stderr)
        return 2

    destination = arguments.output or arguments.spec.with_suffix(".svg")
    destination.write_text(svg, encoding="utf-8")
    print(destination)
    if table is not None:
        arguments.markdown.write_text(table, encoding="utf-8")
        print(arguments.markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
