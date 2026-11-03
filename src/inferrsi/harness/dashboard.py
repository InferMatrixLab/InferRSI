"""Export a self-contained, read-only dashboard from recorded evidence."""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
from importlib.resources import files
from pathlib import Path

from ..summary_chart import SpecError, build_svg
from .dashboard_data import _inside, _number, _text, load_dashboard
from .dashboard_timeline import temporal_chart


def _sanitize_spec(value: object, depth: int = 0) -> object:
    if depth > 12:
        raise ValueError("chart specification is too deeply nested")
    if isinstance(value, str):
        return _text(value, "")
    if isinstance(value, list):
        return [_sanitize_spec(item, depth + 1) for item in value[:100]]
    if isinstance(value, dict):
        return {key: _sanitize_spec(item, depth + 1) for key, item in value.items()
                if isinstance(key, str)}
    return value


def _bounded_chain(spec: dict) -> bool:
    """Keep malformed or adversarial chart axes from expanding without bound."""
    metrics, points = spec.get("metrics"), spec.get("points")
    baseline = spec.get("baseline")
    if not isinstance(metrics, list) or not 1 <= len(metrics) <= 7:
        return False
    if not isinstance(points, list) or not 1 <= len(points) <= 100:
        return False
    if not isinstance(baseline, dict) or not isinstance(baseline.get("metrics"), dict):
        return False
    keys = [item.get("key") if isinstance(item, dict) else None for item in metrics]
    if any(not isinstance(key, str) or not key for key in keys):
        return False
    bases = {key: _number(baseline["metrics"].get(key)) for key in keys}
    if any(value is None or value <= 0 for value in bases.values()):
        return False
    ratios = [1.0]
    for point in points:
        values = point.get("values") if isinstance(point, dict) else None
        if not isinstance(values, dict):
            return False
        for key in keys:
            number = _number(values.get(key))
            if number is None or number <= 0:
                return False
            ratio = number / bases[key]
            if not 0 < ratio <= 1_000_000:
                return False
            ratios.append(ratio)
    references = spec.get("references", [])
    if not isinstance(references, list):
        return False
    for ref in references:
        if (not isinstance(ref, dict) or not isinstance(ref.get("metric"), str)
                or ref["metric"] not in bases):
            return False
        number = _number(ref.get("value"))
        if number is None or not 0 < number / bases[ref["metric"]] <= 1_000_000:
            return False
        ratios.append(number / bases[ref["metric"]])
    axis = spec.get("axis", {})
    if not isinstance(axis, dict):
        return False
    step = _number(axis.get("step", 0.5))
    if step is None or step <= 0 or max(ratios) + step == max(ratios):
        return False
    # The shared renderer adds a 1e-9 tolerance when iterating ticks. Include
    # it in the bound, and leave room for floor/ceiling rounding.
    return (max(ratios) - min(ratios) + 1e-9) / step + 3 <= 150


def _chart(source: Path, view: dict) -> tuple[str, str]:
    chart_file = source / "summary-chart.json"
    spec = None
    recorded_title = False
    message = "Independent candidate results relative to their paired baselines."
    if view["overview"]["comparison_state"] != "comparable":
        return "", "Comparison evidence is missing, unsupported, or incompatible."
    if _inside(source, chart_file) and chart_file.is_file():
        try:
            if chart_file.stat().st_size <= 256 * 1024:
                recorded = json.loads(chart_file.read_text(encoding="utf-8"))
                if (isinstance(recorded, dict) and recorded.get("layout", "chain") == "chain"
                        and _bounded_chain(recorded)):
                    spec = _sanitize_spec(recorded)
                    recorded_title = isinstance(recorded.get("title"), str)
                    message = "Recorded cumulative campaign steps."
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, RecursionError):
            pass
    if spec is None:
        trials = []
        for index, row in enumerate(view["candidates"], 1):
            gain = row["improvement_pct"]
            if gain is None:
                continue
            status = {"improved": "gain", "noise": "flat", "regressed": "regressed"}.get(
                row["outcome"], "open"
            )
            trials.append({"group": "Candidates", "label": f'{index}. {row["title"]}',
                           "values": {"gain": 1 + gain / 100}, "status": status,
                           "note": row["outcome"]})
        if not trials:
            return "", "No measured candidate results recorded."
        target = view["overview"]["target_improvement_pct"]
        gains = [row["improvement_pct"] for row in view["candidates"]
                 if row["improvement_pct"] is not None]
        if target is not None and 1 + target / 100 > 0:
            gains.append(target)
        spread = max([0.0, *gains]) - min([0.0, *gains])
        if not math.isfinite(spread):
            return "", "Recorded values exceed the supported chart scale."
        tick = 0.01 if spread < 0.05 else 10 ** math.floor(math.log10(spread / 5))
        spec = {
            "title": "Candidate gain versus paired baseline", "layout": "branch", "sort": "given",
            "baseline": {"label": "paired baseline", "metrics": {"gain": 1}},
            "metrics": [{"key": "gain", "label": "gain"}], "trials": trials,
            "axis": {"tick": tick},
            "references": [{"label": "Target", "metric": "gain", "value": 1 + target / 100}]
            if target is not None and 1 + target / 100 > 0 else [],
        }
    try:
        svg = build_svg(spec)
    except (SpecError, TypeError, ValueError, OverflowError, ZeroDivisionError):
        return "", "The recorded chart specification is invalid or incomplete."
    # The shared renderer is unchanged. Adapt its fixed light palette for this panel.
    for light, dark in {
        "#fcfcfb": "#181b1f", "#0b0b0b": "#e7e9ed", "#52514e": "#aab2bf",
        "#8a8984": "#8e98a6", "#f1f1ee": "#20242c", "#e4e3df": "#343a45",
    }.items():
        svg = svg.replace(light, dark)
    # The first title and text nodes are the caller-authored chart heading.
    # Other chart labels can contain evidence states and must not use overlays.
    if recorded_title:
        svg = svg.replace("<title>", '<title data-narrative="">', 1)
        svg = svg.replace("<text ", '<text data-narrative="" ', 1)
    return svg[svg.find("<svg"):], message


def _translations(path: Path | None) -> dict:
    """Load an explicitly supplied, bounded translation overlay."""
    if path is None:
        return {"en": {}, "zh": {}}
    with Path(path).open("rb") as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("dashboard translations exceed 2 MiB")

    def unique(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate dashboard translation key")
            result[key] = value
        return result

    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("invalid dashboard translations") from exc
    if (not isinstance(document, dict) or set(document) - {"schema_version", "en", "zh"}
            or type(document.get("schema_version")) is not int
            or document["schema_version"] != 1):
        raise ValueError("invalid dashboard translations")
    result = {}
    for language in ("en", "zh"):
        entries = document.get(language, {})
        if (not isinstance(entries, dict) or any(
            not isinstance(key, str) or not key.strip() or not isinstance(value, str)
            or not value.strip() for key, value in entries.items()
        )):
            raise ValueError("invalid dashboard translations")
        try:
            for key, value in entries.items():
                key.encode("utf-8")
                value.encode("utf-8")
        except UnicodeError as exc:
            raise ValueError("invalid dashboard translations") from exc
        result[language] = entries
    return result


def write_dashboard(source: Path, destination: Path | None = None,
                    translations: Path | None = None) -> Path:
    """Write one offline HTML document, excluding raw logs and environment data."""
    source = Path(source).resolve()
    view = load_dashboard(source)
    chart, chart_note = _chart(source, view)
    temporal, temporal_note = temporal_chart(view)
    view["chart_note"] = chart_note
    view["temporal_note"] = temporal_note
    view["translations"] = _translations(translations)
    payload = json.dumps(view, ensure_ascii=False, allow_nan=False)
    # The JSON data block cannot terminate its script element or create markup.
    payload = (payload.replace("&", "\\u0026").replace("<", "\\u003c")
               .replace(">", "\\u003e").replace("\u2028", "\\u2028")
               .replace("\u2029", "\\u2029"))
    template = files("inferrsi").joinpath("data", "dashboard", "template.html").read_text(
        encoding="utf-8"
    )
    replacements = {"__DASHBOARD_DATA__": payload, "__DASHBOARD_CHART__": chart,
                    "__DASHBOARD_TEMPORAL__": temporal}
    document = re.sub(
        r"__DASHBOARD_(?:DATA|CHART|TEMPORAL)__", lambda match: replacements[match.group()],
        template,
    )
    output = Path(destination) if destination is not None else source / "dashboard.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_symlink():
        raise ValueError("dashboard output cannot be a symbolic link")
    if output.exists():
        if not output.is_file():
            raise ValueError("dashboard output is not a regular file")
        if output.suffix.lower() != ".html":
            raise ValueError("refusing to overwrite an existing non-dashboard file")
        with output.open("r", encoding="utf-8", errors="replace") as existing:
            if '<meta name="generator" content="InferRSI dashboard">' not in existing.read(1024):
                raise ValueError("refusing to overwrite an existing non-dashboard file")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent, prefix=".dashboard-",
            suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(document)
        os.replace(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return output.resolve()
