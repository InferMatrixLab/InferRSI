"""Both offline reports render one projection; imported text is never markup."""

import html
import json

from .schema import number


def _text(value):
    if value is None:
        return "Unknown"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    return str(value)


def _markdown(value):
    # Numeric entities prevent caller text from becoming HTML, Markdown links,
    # headings, fences or table rows, including javascript: links and </script>.
    return "".join(f"&#{ord(c)};" if c in '\\`*_{}[]()#+-.!|<>"&\n\r' else c for c in _text(value))


def _assessment_source(value):
    if not value:
        return None
    return "cached state; unverified" if value["kind"] == "cached_state" else "retained observation"


def _sections(result):
    acceptance = result["acceptance"]
    selected = result["selected_candidate"]
    verdict = acceptance["verdict"] if acceptance["status"] == "assessed" else "Not assessed"
    metrics = result["metrics"] or []
    sections = [
        (
            "Result summary",
            ["Item", "Result"],
            [
                ["Goal", result["campaign"].get("goal")],
                ["Workflow", result["completion"]["status"]],
                ["Completion reason", result["completion"]["reason"]],
                ["Outcome", result["outcome"]["kind"]],
                ["Original assessment", verdict],
                ["Assessment source", _assessment_source(acceptance.get("assessment_provenance"))],
                ["Assessment reference", acceptance["assessment_ref"]],
                ["Acceptance scope", acceptance["scope"]],
                ["Delivery acceptance verified", acceptance["delivery_accepted"]],
                [
                    "Selected code",
                    selected.get("path", selected.get("revision")) if selected else None,
                ],
                ["Optimization speedup", result["outcome"].get("optimization_speedup")],
            ],
        ),
        (
            "Experiment conditions",
            ["Item", "Recorded value"],
            [
                ["Task kind", result["campaign"]["task_kind"]],
                ["Task", result["campaign"].get("task")],
                ["Frozen plan", result["campaign"].get("plan_ref")],
                ["Acceptance basis", result["campaign"].get("acceptance_basis")],
                ["Baseline", result["baseline"]],
            ],
        ),
        (
            "Final comparison",
            [
                "Metric",
                "Scope / workload",
                "Phase",
                "Statistic",
                "Unit",
                "Baseline",
                "Candidate",
                "Speedup",
                "Improvement %",
                "Sample counts",
                "Repetitions",
                "Comparison limits",
                "Evidence",
            ],
            [
                [
                    m["name"],
                    [m["scope"], m["workload_id"]],
                    m["phase"],
                    m["statistic"],
                    m["unit"],
                    m["baseline"],
                    m["candidate"],
                    m["speedup"],
                    m["improvement_pct"],
                    m["sample_counts"],
                    m["repetitions"],
                    m["comparability"]["reason"],
                    m["evidence_refs"],
                ]
                for m in metrics
                if m["phase"] != "search"
            ],
        ),
        (
            "Optimization history",
            [
                "Round",
                "Attempt",
                "Hypothesis",
                "Change",
                "State",
                "Verdict",
                "Assessment source",
                "Score",
                "Best score",
                "Selection / reason",
            ],
            [
                [
                    r.get("round"),
                    r.get("attempt_id"),
                    r.get("hypothesis"),
                    r.get("change_summary"),
                    r.get("execution_state"),
                    r.get("verdict"),
                    _assessment_source(r.get("assessment_provenance")),
                    r.get("score"),
                    r.get("best_score"),
                    [r.get("selection_decision"), r.get("reason")],
                ]
                for r in result["rounds"] or []
            ],
        ),
        (
            "Validation and limitations",
            ["Item", "Recorded value"],
            [
                ["Independent final", result["final"]],
                ["Checks", result["checks"]],
                *[[g["code"] + " (" + g["affects"] + ")", g["reason"]] for g in result["gaps"]],
                ["Statistical significance", "Not established by export"],
            ],
        ),
        (
            "Code and reproduction",
            ["Item", "Reference"],
            [
                ["Selected retained code", selected],
                ["Frozen commands / configuration", result["campaign"].get("acceptance_basis")],
                ["Source records", result["sources"]],
                [
                    "Evidence access",
                    "Source paths in artifacts.json require the original input "
                    "directory. External archives retain their own access requirements. "
                    "No evidence, models or dependencies were downloaded or executed.",
                ],
            ],
        ),
        (
            "Time and resources",
            ["Measure", "Value / source / coverage"],
            [
                ["Execution", result["execution"]],
                *[[key, value] for key, value in result["usage"].items()],
            ],
        ),
    ]
    if result.get("benchmark_metrics") is not None:
        from ..views.comparison_report import benchmark_metric_rows

        sections.insert(0, ("Benchmark metrics", ["Metric", "Value", "Coverage / source"],
                            benchmark_metric_rows(result["benchmark_metrics"])))
    return sections


def _curve(result):
    rounds = [row for row in result["rounds"] or [] if row.get("round") is not None]
    values = [number(row.get(key)) for row in rounds for key in ("score", "best_score")]
    positive = [value for value in values if value is not None and value > 0]
    if not positive:
        return ""
    scale = max(positive)
    nodes = [
        '<figure><svg viewBox="0 0 800 250" role="img" '
        'aria-label="Search round scores and best retained score">',
        "<title>Search only; independent final acceptance is reported separately</title>",
        '<path d="M50 15 V210 H770" fill="none" stroke="#657689"/>',
    ]
    for key, color, label in (
        ("score", "#176fa6", "Round score"),
        ("best_score", "#bd6e0a", "Best retained score"),
    ):
        previous = None
        for index, row in enumerate(rounds):
            value = number(row.get(key))
            if value is None or value <= 0:
                previous = None  # Missing/failed observations leave gaps, never zeros.
                continue
            x, y = 60 + 690 * index / max(1, len(rounds) - 1), 205 - 180 * (value / scale)
            if previous is not None:
                nodes.append(
                    f'<path d="M{previous[0]:.2f} {previous[1]:.2f} L{x:.2f} {y:.2f}" '
                    f'fill="none" stroke="{color}"/>'
                )
            nodes.append(
                f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="{color}">'
                f"<title>{label}, round {index + 1}: {value}</title></circle>"
            )
            previous = x, y
    nodes += [
        '<text x="50" y="238">Round score (blue) · best retained score (orange)</text>',
        "</svg><figcaption>Search rounds in submission order; missing scores leave gaps. "
        "Hover a point for its recorded value. Final acceptance remains separate.</figcaption>"
        "</figure>",
    ]
    if any((r.get("assessment_provenance") or {}).get("kind") == "cached_state" for r in rounds):
        nodes.append(
            "<p>Some search scores are from cached state; unverified. "
            "See each round's assessment source below.</p>"
        )
    return "".join(nodes)


def reports(result, result_digest):
    metadata = (
        f"Export: {result['export']['id']} · Snapshot: {result['export']['snapshot_at']} · "
        f"Kind: {result['export']['kind']} · Structured result SHA-256: {result_digest}"
    )
    verdict = result["acceptance"]["verdict"] or "Not assessed"
    if (result["acceptance"].get("assessment_provenance") or {}).get("kind") == "cached_state":
        verdict += " (cached state; unverified)"
    conclusion = (
        f"{result['completion']['status']}: {result['outcome']['kind']}. "
        f"Original assessment: {verdict}. "
        f"{result['completion']['reason']}."
    )
    md = [
        "# RSI result report",
        "",
        _markdown(conclusion),
        "",
        _markdown(metadata),
        "",
        "[Open in a browser](report.html) · [Structured result](campaign-result.json) · "
        "[Artifact index](artifacts.json)",
        "",
        "Evidence remains in the referenced source locations; it is not bundled. "
        "Review source records and references before sharing this local export.",
        "",
    ]
    body = [
        "<h1>RSI result report</h1>",
        f"<p><strong>{html.escape(conclusion)}</strong></p>",
        f"<p>{html.escape(metadata)}</p>",
        '<nav><a href="report.md">Markdown</a> · '
        '<a href="campaign-result.json">Structured result</a> · '
        '<a href="artifacts.json">Artifact index</a></nav>',
        "<p>Evidence remains in the referenced source locations; it is not bundled. "
        "Core content is available offline without scripts. Review before sharing.</p>",
    ]
    # Verification failures must be on the first screen even for a historical PASS.
    if result["gaps"]:
        warning = "; ".join(g["reason"] for g in result["gaps"])
        md += ["**Current gaps:** " + _markdown(warning), ""]
        body += [f'<p class="gaps"><strong>Current gaps:</strong> {html.escape(warning)}</p>']
    preamble = None
    if result.get("benchmark_metrics") is not None:
        preamble = (md[2:], body[1:])
        md, body = md[:2], body[:1]
    for title, headers, rows in _sections(result):
        md += [
            "## " + title,
            "",
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
        ]
        md.extend("| " + " | ".join(_markdown(v) for v in row) + " |" for row in rows)
        if not rows:
            md.append("| Not recorded | " + " | " * (len(headers) - 2) + "|")
        md.append("")
        body += [
            f"<section><h2>{title}</h2>",
            _curve(result) if title == "Optimization history" else "",
            "<div class='table'><table><thead><tr>",
            "".join(f"<th>{h}</th>" for h in headers),
            "</tr></thead><tbody>",
        ]
        body.extend(
            "<tr>" + "".join(f"<td>{html.escape(_text(v))}</td>" for v in row) + "</tr>"
            for row in rows
        )
        body += ["</tbody></table></div></section>"]
        if preamble is not None:
            md.extend(preamble[0])
            body.extend(preamble[1])
            preamble = None
    # Native details supplies offline interaction without executable imported data.
    body += [
        "<details><summary>Full structured snapshot</summary><pre>",
        html.escape(json.dumps(result, ensure_ascii=False, indent=2)),
        "</pre></details>",
    ]
    document = (
        """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>RSI result report</title><style>
body{font:16px/1.5 system-ui,sans-serif;color:#172b42;background:#fafbfd;
max-width:1200px;margin:2rem auto;padding:0 1.5rem}h1,h2{line-height:1.2}
.table{overflow:auto}table{border-collapse:collapse;width:100%;background:white}
th,td{border:1px solid #d7dfe8;padding:.6rem;text-align:left;vertical-align:top;
overflow-wrap:anywhere;min-width:5rem}th{background:#eaf0f6}.gaps{border-left:4px solid #b46300;
padding:1rem;background:#fff4e0}pre{white-space:pre-wrap;overflow-wrap:anywhere}
a{color:#145da0}section{margin:2rem 0}details{margin:2rem 0}
</style></head><body>"""
        + "\n".join(body)
        + "</body></html>\n"
    )
    return "\n".join(md).encode("utf-8"), document.encode("utf-8")
