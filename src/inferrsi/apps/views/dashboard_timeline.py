"""Render measured candidate results and recorded stages on one time axis."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from html import escape

from inferrsi.harness.records.evidence import STAGES

_NAMES = {
    "diagnosis": "Diagnosis", "knowledge": "Knowledge", "search": "Candidate search",
    "execution": "Execution", "validation": "Validation", "review": "Review",
}
_COLORS = {
    "diagnosis": "#9d8bff", "knowledge": "#5794f2", "search": "#56c5ce",
    "execution": "#73bf69", "validation": "#ff9830", "review": "#e5a8e5",
}


def _instant(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.timestamp()
    except (ValueError, OverflowError, OSError):
        return None


def temporal_chart(view: dict) -> tuple[str, str]:
    """Use only timestamped events; a result point requires a terminal event."""
    rows = view["candidates"]
    events = []
    terminals = []
    untimed_results = 0
    for row in rows:
        timed = [(event, _instant(event.get("time"))) for event in row["events"]]
        events.extend((row, event, stamp) for event, stamp in timed
                      if stamp is not None and event.get("stage") in STAGES)
        terminal = [(event, stamp) for event, stamp in timed
                    if stamp is not None and event.get("phase") in ("complete", "crashed")]
        if terminal:
            terminals.append((row, max(stamp for _, stamp in terminal)))
        elif (row["improvement_pct"] is not None
              or row["outcome"] in ("failed", "quality_failed", "cancelled")
              or row["decision"] == "rolled_back"):
            untimed_results += 1
    stamps = [stamp for _, _, stamp in events] + [stamp for _, stamp in terminals]
    if not stamps:
        return "", "No timestamped events recorded; a time axis cannot be drawn."
    first, last = min(stamps), max(stamps)
    if first == last:
        first, last = first - 1, last + 1

    comparable = view["overview"]["comparison_state"] == "comparable"
    measured = [(row, stamp) for row, stamp in terminals
                if comparable and row["improvement_pct"] is not None]
    values = [row["improvement_pct"] for row, _ in measured]
    target = view["overview"]["target_improvement_pct"]
    if target is not None:
        values.append(target)
    bands = [row["noise_band_pct"] for row, _ in measured]
    noise = bands[0] if bands and bands[0] is not None and all(
        band is not None and math.isclose(band, bands[0], rel_tol=1e-9, abs_tol=1e-9)
        for band in bands
    ) else None
    if noise is not None:
        values.extend((-noise, noise))
    values.append(0.0)
    if any(not math.isfinite(value) or abs(value) > 1_000_000 for value in values):
        return "", "Recorded values exceed the supported time-chart scale."
    low, high = min(values), max(values)
    pad = max((high - low) * 0.12, 1.0)
    low, high = low - pad, high + pad
    left, right, top, bottom = 140, 925, 40, 220
    def x(stamp: float) -> float:
        return left + (stamp - first) / (last - first) * (right - left)

    def y(value: float) -> float:
        return bottom - (value - low) / (high - low) * (bottom - top)

    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 435" role="img" '
        'aria-labelledby="temporal-title temporal-desc">',
        '<title id="temporal-title">Candidate results and stage events over time</title>',
        '<desc id="temporal-desc">Results use terminal event timestamps. Stage dots are '
        'events, not durations. Crosses in the no-value row have no numeric measurement.</desc>',
        '<rect width="960" height="435" fill="#181b1f"/>',
    ]

    def text(px: float, py: float, label: str, color: str = "#aab2bf", size: int = 10) -> None:
        svg.append(f'<text x="{px:.1f}" y="{py:.1f}" fill="{color}" '
                   f'font-size="{size}">{escape(label)}</text>')

    if noise is not None:
        svg.append(f'<rect data-kind="noise-band" x="{left}" y="{y(noise):.1f}" '
                   f'width="{right-left}" height="{y(-noise)-y(noise):.1f}" '
                   'fill="#ff9830" fill-opacity="0.12"/>')
        text(left + 5, y(noise) + 12, f"Noise ±{noise:.1f}%", "#ffb76b")
    for index in range(5):
        tick = low + (high - low) * index / 4
        py = y(tick)
        svg.append(f'<line x1="{left}" x2="{right}" y1="{py:.1f}" y2="{py:.1f}" '
                   'stroke="#343a45"/>')
        text(76, py + 4, f"{tick:+.1f}%")
    if target is not None:
        py = y(target)
        svg.append(f'<line data-kind="target-line" x1="{left}" x2="{right}" '
                   f'y1="{py:.1f}" y2="{py:.1f}" stroke="#f2c96d" '
                   'stroke-dasharray="5 4"/>')
        text(left + 5, py - 5, f"Target {target:+.1f}%", "#f2c96d")
    text(12, 26, "Gain vs baseline")
    text(12, 246, "No numeric result")
    text(12, 280, "Stage events")
    for index, stage in enumerate(STAGES):
        py = 294 + index * 18
        text(12, py + 4, _NAMES[stage])
        svg.append(f'<line x1="{left}" x2="{right}" y1="{py}" y2="{py}" '
                   'stroke="#343a45"/>')
    for row, event, stamp in events:
        py = 294 + STAGES.index(event["stage"]) * 18
        label = f'{row["title"]}: {_NAMES[event["stage"]]} · {event["time"]}'
        svg.append(f'<circle data-kind="stage-event" cx="{x(stamp):.1f}" cy="{py}" r="3" '
                   f'fill="{_COLORS[event["stage"]]}"><title>{escape(label)}</title></circle>')
    for row, stamp in terminals:
        gain, outcome = row["improvement_pct"], row["outcome"]
        if gain is not None and not comparable:
            continue
        if gain is None and outcome not in ("failed", "quality_failed", "cancelled") \
                and row["decision"] != "rolled_back":
            continue
        px, py = x(stamp), y(gain) if gain is not None else 242
        label = f'{row["title"]}: {outcome.replace("_", " ")}'
        label += f' {gain:+.1f}%' if gain is not None else ' · no numeric result'
        svg.append(f'<g data-kind="marker-{escape(outcome, quote=True)}">'
                   f'<title>{escape(label)}</title>')
        if outcome == "failed":
            svg.append(f'<path d="M {px-5:.1f} {py-5:.1f} l 10 10 m -10 0 l 10 -10" '
                       'stroke="#f2495c" stroke-width="2"/>')
        elif outcome == "quality_failed":
            svg.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="6" fill="none" '
                       'stroke="#f2495c" stroke-width="2" stroke-dasharray="3 2"/>')
        elif outcome == "noise":
            svg.append(f'<path d="M {px:.1f} {py-6:.1f} l 6 6 l -6 6 l -6 -6 z" '
                       'fill="#ff9830"/>')
        else:
            color = {"improved": "#73bf69", "regressed": "#f2495c"}.get(outcome, "#8e98a6")
            svg.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="{color}"/>')
        if row["decision"] == "rolled_back":
            svg.append(f'<rect data-kind="marker-rollback" x="{px-9:.1f}" y="{py-9:.1f}" '
                       'width="18" height="18" '
                       'fill="none" stroke="#cf9fff" stroke-width="2"/>')
        svg.append('</g>')
        text(min(px + 8, right - 110), max(py - 8, top + 8), row["title"][:24], "#d8dce3")
    for index in range(3):
        stamp = first + (last - first) * index / 2
        px = x(stamp)
        svg.append(f'<line x1="{px:.1f}" x2="{px:.1f}" y1="394" y2="399" '
                   'stroke="#8e98a6"/>')
        try:
            label = datetime.fromtimestamp(stamp, timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
        except (ValueError, OverflowError, OSError):
            return "", "Recorded timestamps exceed the supported time-chart range."
        text(max(left, min(px - 60, right - 120)), 416, label)
    svg.append('</svg>')
    note = "Terminal events place results; stage dots are events, not durations."
    if untimed_results:
        note += f" {untimed_results} result(s) have no recorded terminal timestamp."
    if not comparable:
        note += " Unverified or incompatible candidate measurements are not plotted together."
    elif measured and noise is None:
        note += " No common noise band recorded."
    return "".join(svg), note
