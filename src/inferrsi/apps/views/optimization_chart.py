"""Render shared Harness optimization records without filling missing measurements."""

import math
from html import escape


def render_result(summary: dict) -> str:
    final = summary["final_assessment"]
    verdict = final["verdict"] if final else "Not recorded"
    reason = final["reason"] if final else "Search results are not final acceptance."
    score = final["score"] if final else None
    reference = summary.get("final_reference") or {}
    fields = [f'Campaign state: {summary["state"]}', reason]
    if score is not None:
        fields.append(f'Final {summary["selection"]["metric"]}: {score:.6g}')
    if reference.get("state") == "present":
        fields.append(f'Evidence: {reference["path"]} (SHA-256 {reference["sha256"]})')
    return (f'<section aria-label="Independent final result"><h3>Independent final: '
            f'{escape(verdict)}</h3>'
            + "".join(f'<p>{escape(field)}</p>' for field in fields) + '</section>')


def render_curve(summary: dict) -> str:
    curve = summary["curve"]
    if not curve or len(curve) > 1000:
        return ""
    chunks = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 560" '
              'role="img" aria-label="Optimization objective and cumulative tokens">',
              '<rect width="900" height="560" fill="white"/>']

    def panel(top, title, series):
        values = [value for _, _, points in series for value in points
                  if type(value) in (int, float) and math.isfinite(value)]
        chunks.append(f'<text x="75" y="{top}" font-size="16" fill="#24334b">'
                      f'{escape(title)}</text>')
        if not values:
            chunks.append(f'<text x="75" y="{top + 45}" fill="#64748b">Not recorded</text>')
            return
        low, high = min(values), max(values)
        scale = max(abs(low), abs(high), 1)
        lo, hi = low / scale, high / scale
        span = hi - lo or 1
        width, height = 740, 150
        chunks.append(f'<path d="M75 {top+25} V{top+25+height} H815" '
                      'fill="none" stroke="#94a3b8"/>')
        for series_index, (name, color, points) in enumerate(series):
            previous = None
            for index, value in enumerate(points):
                if type(value) not in (int, float) or not math.isfinite(value):
                    previous = None
                    continue
                x = 75 + width * index / max(1, len(curve) - 1)
                y = top + 25 + height * (1 - (value / scale - lo) / span)
                if previous:
                    chunks.append(f'<path d="M{previous[0]:.2f} {previous[1]:.2f} '
                                  f'L{x:.2f} {y:.2f}" stroke="{color}" fill="none"/>')
                chunks.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="{color}">'
                              f'<title>{escape(name)}: round {index+1}, {value:.6g}</title>'
                              '</circle>')
                previous = (x, y)
            chunks.append(f'<text x="{75 + 220 * series_index}" '
                          f'y="{top+205}" fill="{color}" font-size="12">{escape(name)}</text>')
        chunks.append(f'<text x="8" y="{top+35}" font-size="11">{high:.6g}</text>'
                      f'<text x="8" y="{top+175}" font-size="11">{low:.6g}</text>'
                      f'<text x="75" y="{top+190}" font-size="11">Round 1</text>'
                      f'<text x="745" y="{top+190}" font-size="11">Round {len(curve)}</text>')

    selection = summary["selection"]
    panel(30, f'{selection["metric"]} ({selection["direction"]})', [
        ("Candidate", "#94a3b8", [item["assessment"].get("score") for item in curve]),
        ("Best valid", "#2166ac", [item["best_score"] for item in curve]),
    ])
    panel(300, "Cumulative observed tokens", [
        ("Input + output tokens", "#27834b",
         [item["cumulative_usage"]["total_tokens"] for item in curve]),
    ])
    chunks.append('</svg>')
    return "".join(chunks)
