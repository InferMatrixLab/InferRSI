#!/usr/bin/env python3
"""Render a campaign gain summary figure from a JSON specification.

The figure answers one question for a whole campaign: which trial moved the
measured quantity, by how much, and what happened to the ones that did not.
Every trial sits on one gain axis, so a screen that produced no gain or lost
ground is as visible as the best result.

Values are always drawn as gain against the baseline, never as an absolute
curve, because trials branch off one baseline rather than accumulate. The
renderer uses only the standard library and writes SVG, so a committed figure
reproduces without a plotting dependency.

Specification shape (see ``evidence/_template/results/summary-chart.example.json``)::

    {
      "title": "Engine end-to-end throughput",
      "subtitle": ["one line of scope", "one line of caution"],
      "unit": "frames/s",
      "baseline": {"label": "main snapshot", "metrics": {"C16": 513.3, "C32": 540.2}},
      "metrics": [{"key": "C16", "label": "C16"}, {"key": "C32", "label": "C32"}],
      "label_metric": "C32",
      "sort": "gain",
      "references": [{"label": "peer target", "metric": "C32", "value": 2544.1}],
      "statuses": {"flat": {"mark": "x"}},
      "trials": [
        {"group": "Kernel", "label": "fused quantization",
         "values": {"C16": 826.0, "C32": 857.7}, "status": "open", "note": "single screen"}
      ]
    }
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
    return float(value)


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
    keys = _metric_keys(spec)
    baseline = _baseline(spec, keys)
    statuses = _statuses(spec)
    trials = _ordered(_trials(spec, keys), keys, spec)
    references = _references(spec, keys)
    label_metric = _label_metric(spec, keys)
    unit = str(spec.get("unit", "")).strip()
    tick = float(spec.get("axis", {}).get("tick", 50))

    gains = {
        key: [(trial["values"][key] / baseline[key] - 1.0) * 100.0 for trial in trials]
        for key in keys
    }
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


def metric_label(spec: dict, key: str) -> str:
    for metric in spec.get("metrics", []):
        if metric.get("key") == key:
            return str(metric.get("label", key))
    return key


def build_markdown(spec: dict) -> str:
    """Return a Markdown table carrying the same values as the figure."""
    keys = _metric_keys(spec)
    baseline = _baseline(spec, keys)
    trials = _ordered(_trials(spec, keys), keys, spec)
    label_metric = _label_metric(spec, keys)
    unit = str(spec.get("unit", "")).strip()
    unit_note = f" ({unit})" if unit else ""
    head = ["Trial", *[f"{metric_label(spec, key)}{unit_note}" for key in keys]]
    head += [f"{metric_label(spec, key)} gain" for key in keys]
    head += ["Disposition"]
    lines = [
        "| " + " | ".join(head) + " |",
        "| " + " | ".join("---" for _ in head) + " |",
    ]
    for trial in trials:
        row = [f"{trial['group']}: {trial['label']}"]
        row += [_format_value(trial["values"][key]) for key in keys]
        row += [
            f"{(trial['values'][key] / baseline[key] - 1.0) * 100.0:+.1f}%" for key in keys
        ]
        row.append(_status_text(trial))
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |")
    caption = str(spec.get("title", "")).strip()
    if caption:
        lines.insert(0, f"**{caption}**")
        lines.insert(1, "")
    note = f"Gain is measured against the {spec.get('baseline', {}).get('label', 'baseline')}"
    note += f"; the {metric_label(spec, label_metric)} label orders each row."
    lines += ["", note]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
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
