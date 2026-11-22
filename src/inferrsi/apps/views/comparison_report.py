"""Offline comparison presentation over Apps' normalized, retained result projection."""

import hashlib
import json
import math
import os
import tempfile
from html import escape
from pathlib import Path

_LABELS = {
    "efficiency_improved": "Efficiency improved / 效率提高",
    "no_gain": "No observed gain / 未观察到收益",
    "regression": "Regression / 效率退化",
    "tradeoff": "Tradeoff / 存在权衡",
    "insufficient_evidence": "Insufficient evidence / 证据不足",
}
_TRACE_HEADERS = (
    "Round", "Strategy", "Hypothesis", "Knowledge references", "Round speedup",
    "Best speedup", "Correctness", "Adopted",
)
_METRICS = {
    "speedup": "Final speedup",
    "wall_seconds": "Campaign time (s)",
    "tokens": "Session tokens",
}


def _text(value):
    if value is None:
        return "unknown"
    if type(value) is bool:
        return "yes" if value else "no"
    if type(value) is float:
        return f"{value:.6g}"
    if type(value) is int:
        return f"{value:,}"
    return str(value)


def _md(value):
    value = escape(_text(value), quote=False)
    for char in "\\`*_{}[]()#+!|":
        value = value.replace(char, "\\" + char)
    return value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def _markdown_table(headers, rows):
    return ["| " + " | ".join(_md(value) for value in headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
            *["| " + " | ".join(_md(value) for value in row) + " |" for row in rows]]


def _html_table(headers, rows):
    return ("<div class=scroll><table><thead><tr>"
            + "".join(f"<th scope=col>{escape(_text(value))}</th>" for value in headers)
            + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<td>{escape(_text(value))}</td>" for value in row)
                      + "</tr>" for row in rows) + "</tbody></table></div>")


def _task_rows(assessment):
    rows = []
    for task in assessment["tasks"]:
        for name, label in _METRICS.items():
            metric = task["metrics"][name]
            rows.append((task["task"], label, metric["selected"],
                         _metric_value(name, metric["on_median"]),
                         _metric_value(name, metric["off_median"]),
                         _metric_value("speedup", metric["paired_factor"]), metric["pair_count"],
                         _LABELS[task["conclusion"]["kind"]]))
    return rows


def _metric_value(name, value):
    if value is None:
        return None
    if name == "speedup":
        return f"{value:.3f}×"
    if name == "wall_seconds":
        return f"{value:,.2f}"
    return f"{value:,}" if type(value) is int else f"{value:,.1f}".removesuffix(".0")


def benchmark_metric_rows(summary):
    """Compact rows shared by single-run and paired reports; JSON owns the numbers."""
    usage = summary["token_usage"]
    rate = summary["step_acceptance_rate"]
    acceptance = (f"{summary['accepted_steps']}/{summary['assessed_steps']} ({rate:.1%})"
                  if rate is not None else None)
    reasons = summary.get("missing_reasons", {})
    return [
        ("Final speedup", _metric_value("speedup", summary["final_speedup"]),
         summary["final_kind"] or "; ".join(reasons.get("final_speedup", []))),
        ("Step acceptance", acceptance,
         f"{summary['step_coverage']}; submitted {_text(summary['submitted_steps'])}; "
         f"infra {_text(summary['infrastructure_failures'])}; "
         f"unresolved {_text(summary['unresolved_steps'])}"),
        ("Token consumption", _metric_value("tokens", usage["total_tokens"]),
         f"{usage['coverage']}; input {_text(usage['input_tokens'])}, "
         f"output {_text(usage['output_tokens'])}, "
         f"cached input {_text(usage['cached_input_tokens'])}; "
         f"observed subtotal {_text(usage['observed_tokens'])}"),
    ]


_ACCOUNTING_REASONS = (("success_wall_seconds", "successful campaign wall"),
                       ("total_wall_seconds", "total wall"), ("tokens", "tokens"))


def _attempt_rows(trials):
    """One row per arm; older snapshots without accounting render as unknown."""
    rows = []
    for trial in trials:
        accounting = trial.get("attempt_accounting") or {}
        statuses = "; ".join(
            f"{_text(row.get('attempt'))}: {_text(row.get('status'))}"
            + (" (current evidence not re-verified)" if row.get("reverified") is False else "")
            for row in accounting.get("statuses", [])) or None
        reasons = accounting.get("missing_reasons") or {}
        unknown = "\n".join(f"{label}: {reason}" for key, label in _ACCOUNTING_REASONS
                            for reason in reasons.get(key, [])) or None
        rows.append((trial["task"], trial["condition"], trial["repeat"],
                     accounting.get("attempts"), accounting.get("failed_attempts"), statuses,
                     _metric_value("wall_seconds", accounting.get("success_wall_seconds")),
                     _metric_value("wall_seconds", accounting.get("total_wall_seconds")),
                     _metric_value("tokens", accounting.get("tokens")),
                     accounting.get("token_coverage"), (unknown or "None") if accounting else None))
    return rows


def _attempt_wall(row):
    window = row.get("attempt_window")
    if isinstance(window, dict):
        start, end = window.get("started_at"), window.get("ended_at")
        if all(type(value) in (int, float) and math.isfinite(value) for value in (start, end)):
            return _metric_value("wall_seconds", end - start)
    return "unknown: " + _text(row.get("attempt_window_missing"))


def _current_evidence(row):
    check = row.get("reverification")
    if not isinstance(check, dict):
        return "not collected"
    if check.get("verified") is True:
        return "matches collection"
    return "\n".join([f"re-read status: {_text(check.get('status'))}",
                      *(check.get("added_gaps") or [])])


def _trial_attempt_rows(trial):
    return [(row.get("attempt"), row.get("status"), row.get("eligible"), _attempt_wall(row),
             _metric_value("wall_seconds", row.get("wall_seconds")),
             _metric_value("tokens", row.get("tokens")),
             "\n".join(row.get("gaps") or []) or "None", _current_evidence(row))
            for row in trial.get("attempts") or []]


def _trace_rows(trial):
    rows = []
    for row in trial.get("trace", []):
        refs = row.get("knowledge_refs")
        citations = None if refs is None else "\n".join(refs) or "None"
        rows.append((row.get("round"), row.get("strategy"), row.get("hypothesis"),
                     citations, _metric_value("speedup", row.get("speedup")),
                     _metric_value("speedup", row.get("best_speedup")),
                     row.get("quality"), row.get("adopted")))
    return rows


def _final_rows(final):
    assessment = final.get("assessment") or final
    binding = final.get("binding") or {}
    candidate = final.get("selected_candidate") or {}
    rows = [
        ("Status", assessment.get("status")),
        ("Quality verdict", assessment.get("verdict")),
        ("Final speedup", _metric_value("speedup", final.get("speedup"))),
        ("Selected candidate", candidate.get("candidate_id") or candidate.get("kind")),
        ("Candidate binding verified", binding.get("verified")),
        ("Delivery accepted", final.get("delivery_accepted")),
    ]
    if assessment.get("reason"):
        rows.append(("Reason", assessment["reason"]))
    return rows


def _case_rows(final):
    rows = []
    for case in (final.get("assessment") or {}).get("case_metrics", []):
        samples = case.get("samples_ms") or {}
        rows.append((case.get("id"), case.get("baseline_median_ms"),
                     case.get("candidate_median_ms"), _metric_value("speedup", case.get("speedup")),
                     *(len(samples[side]) if side in samples else None
                       for side in ("baseline", "candidate"))))
    return rows


def _token_rows(trial):
    rows = []
    for key, label in (("host_session_tokens", "Agent session"), ("session_tokens", "Campaign"),
                       ("tokens", "Settled search rounds")):
        record = trial.get("usage", {}).get(key, {})
        value = record.get("value") or {}
        total = (trial["metrics"].get("tokens") if key == "host_session_tokens"
                 else value.get("total_tokens"))
        rows.append((label, value.get("input_tokens"), value.get("output_tokens"),
                     value.get("cached_input_tokens"), total, record.get("coverage")))
    return rows


def _positive(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value > 0
    except OverflowError:
        return False


def _curve(trials):
    """Keep each actual trial separate; missing points break its recorded curve."""
    if sum(len(trial.get("trace", [])) for trial in trials) > 1000:
        return "<p>Curve omitted for size; all recorded rounds remain in the tables.</p>"
    values = [row["best_speedup"] for trial in trials for row in trial.get("trace", [])
              if _positive(row.get("best_speedup"))]
    values += [trial["final"]["speedup"] for trial in trials
               if isinstance(trial.get("final"), dict)
               and _positive(trial["final"].get("speedup"))]
    rounds = [row["round"] for trial in trials for row in trial.get("trace", [])
              if type(row.get("round")) is int and row["round"] > 0]
    if not values or not rounds:
        return "<p>No recorded speedup curve is available.</p>"
    low, high, last = min(values), max(values), max(rounds)
    scale = max(high, 1)
    lower, upper = low / scale, high / scale
    span = upper - lower
    if not span:
        lower -= 0.05
        span = 0.1

    def xy(round_number, value):
        return (70 + 720 * round_number / (last + 1),
                45 + 210 * (1 - (value / scale - lower) / span))

    chunks = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 850 310" '
              'role="img" aria-label="Best retained speedup and independent final">',
              '<path d="M70 35 V255 H800" fill="none" stroke="#94a3b8"/>',
              f'<text x="8" y="48">{high:.4g}x</text>',
              f'<text x="8" y="255">{low:.4g}x</text>',
              '<text x="70" y="295">Recorded rounds; diamond = independent final</text>']
    colors = ("#2563eb", "#16a34a", "#9333ea", "#ea580c")
    for index, trial in enumerate(trials):
        color, previous = colors[index % len(colors)], None
        label = _text(trial.get("id"))
        for row in trial.get("trace", []):
            position, value = row.get("round"), row.get("best_speedup")
            if type(position) is not int or position <= 0 or not _positive(value):
                previous = None
                continue
            x, y = xy(position, value)
            if previous and previous[0] < x:
                chunks.append(f'<path d="M{previous[0]:.2f} {previous[1]:.2f} '
                              f'L{x:.2f} {y:.2f}" stroke="{color}" fill="none"/>')
            chunks.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="{color}">'
                          f'<title>{escape(label)}: round {position}, '
                          f'{value:.6g}x</title></circle>')
            previous = x, y
        final = trial.get("final")
        if isinstance(final, dict) and _positive(final.get("speedup")):
            value = final["speedup"]
            x, y = xy(last + 1, value)
            chunks.append(f'<path d="M{x:.2f} {y-6:.2f} l6 6 -6 6 -6 -6 Z" '
                          f'fill="{color}"><title>{escape(label)}: independent final, '
                          f'{value:.6g}x</title></path>')
    chunks.append("</svg>")
    return "".join(chunks)


def _documents(report, json_digest):
    assessment = report["assessment"]
    conclusion, counts = assessment["conclusion"], assessment["counts"]
    label = _LABELS[conclusion["kind"]]
    repeats = report["repeats"]
    repeat_label = "repeat" if repeats == 1 else "repeats"
    scope = ", ".join(report["tasks"]) + f" · {repeats} {repeat_label} per task"
    md = ["# Knowledge comparison", ""]
    html = ["<h1>Knowledge comparison</h1>"]

    def heading(title, level=2):
        md.extend(["#" * level + " " + _md(title), ""])
        html.append(f"<h{level}>{escape(title)}</h{level}>")

    def paragraph(value):
        md.extend([_md(value), ""])
        html.append(f"<p>{escape(value)}</p>")

    def table(headers, rows):
        md.extend([*_markdown_table(headers, rows), ""])
        html.append(_html_table(headers, rows))

    if report.get("benchmark_metrics") is not None:
        heading("Benchmark metrics")
        basic = []
        for trial in report["trials"]:
            summary = trial.get("benchmark_metrics")
            if summary:
                rows = benchmark_metric_rows(summary)
                coverage = (f"final: {_text(summary['final_kind'])}; "
                            f"steps: {summary['step_coverage']}; "
                            f"tokens: {summary['token_usage']['coverage']}")
                basic.append((trial["task"], trial["condition"], trial["repeat"],
                              rows[0][1], rows[1][1], rows[2][1], coverage))
            else:
                basic.append((trial["task"], trial["condition"], trial["repeat"],
                              None, None, None, "No retained metrics available"))
        table(("Task", "Arm", "Repeat", "Final speedup", "Step acceptance",
               "Token consumption", "Coverage / source"), basic)
        derived = []
        labels = {"performance_benefit_ratio": "Performance benefit (on/off)",
                  "token_consumption_ratio": "Token consumption (on/off)",
                  "acceptance_rate_delta_pp": "Acceptance difference (pp)"}
        for task in report["benchmark_metrics"]["tasks"]:
            for field, metric_label in labels.items():
                metric = task["metrics"][field]
                value = (_metric_value("speedup", metric["value"])
                         if metric["unit"] == "ratio" else metric["value"])
                derived.append((task["task"], metric_label, value,
                                metric["observed_only"] if metric["value"] is None else None,
                                f"{metric['eligible_pairs']}/{metric['planned_pairs']}",
                                "; ".join(metric["missing_reasons"])))
        table(("Task", "Comparison metric", "Value", "Observed only", "Valid pairs",
               "Missing reasons"), derived)
        paragraph("Final speedup uses an independent final; acceptance counts actual best "
                  "promotions. Token consumption below 1 favors on. Unknown costs remain unknown; "
                  "these metrics do not change the frozen comparison verdict below.")

    md.extend(["**" + label + "**", "", _md(conclusion["text"]), "",
               _md(conclusion["limitation"]), "", _md(scope), ""])
    html.extend([f"<p class=conclusion>{escape(label)}</p>",
                 f"<p>{escape(conclusion['text'])}</p>",
                 f"<p class=note>{escape(conclusion['limitation'])}</p>",
                 f"<p>{escape(scope)}</p>"])

    heading("Task comparisons")
    table(("Task", "Metric", "Used in verdict", "On median", "Off median",
           "Paired benefit factor", "Valid pairs", "Task conclusion"), _task_rows(assessment))
    paragraph("A benefit factor above 1 favors knowledge on. Speedup uses on/off, while time "
              "and tokens use off/on. Medians use eligible matched pairs.")
    table(("Completed trials", "Eligible trials", "Eligible pairs", "Running", "Pending",
           "Failed", "Blocked", "Missing"),
          [(f"{counts['statuses']['completed']} / {counts['planned_trials']}",
            counts["eligible_trials"], f"{counts['eligible_pairs']} / {counts['planned_pairs']}",
            *(counts["statuses"][state] for state in ("running", "pending", "failed", "blocked")),
            counts["missing_trials"])])
    heading("Attempts and wall time", 3)
    table(("Task", "Arm", "Repeat", "Attempts", "Failed attempts", "Attempt statuses",
           "Successful campaign wall (s)", "Total wall from first attempt start (s)",
           "Tokens across attempts", "Token coverage", "Unknown reasons"),
          _attempt_rows(report["trials"]))
    paragraph("Every attempt of an arm is retained. Total wall runs from the first attempt's "
              "native session start to the last attempt's native session end, as exported "
              "in each terminal host observation, so it includes start-up, failed attempts, "
              "retries, wrap-up and the gaps between them. Campaign start/end and receipt "
              "arrival times are not attempt boundaries; without an exported, bound session "
              "window the total stays unknown with its reason. Collected attempts keep their "
              "recorded status; evidence that no longer re-reads is marked, never dropped. "
              "The frozen verdict above still uses the selected attempt's campaign wall and "
              "is unchanged. Tokens across attempts are known only when every attempt has a "
              "complete session export; unknown tokens stay unknown.")

    gaps = [(row["task"], gap) for row in assessment["tasks"] for gap in row["gaps"]]
    if gaps:
        heading("Evidence gaps")
        table(("Task", "Gap"), gaps)

    heading("Optimization trace")
    html.append(_curve(report["trials"]))
    paragraph("Strategies and hypotheses are recorded by the agent. Knowledge references show "
              "which material was supplied. Actual model consumption is unverified.")
    for index, trial in enumerate(report["trials"], 1):
        html.append(f'<section id="trial-{index}">')
        heading(f"{trial['task']} · {trial['condition'].upper()} · repeat {trial['repeat']}", 3)
        status = trial["status"]
        eligibility = "eligible for comparison" if trial["eligible"] else "excluded from comparison"
        paragraph(f"{status.capitalize()} · {eligibility}")
        if len(trial.get("attempts") or []) > 1:
            heading("Attempts", 4)
            table(("Attempt", "Status", "Eligible", "Attempt wall (s)", "Campaign wall (s)",
                   "Session tokens", "Gaps", "Current evidence"),
                  _trial_attempt_rows(trial))
        rows = _trace_rows(trial)
        if rows:
            table(_TRACE_HEADERS, rows)
        else:
            paragraph("No rounds recorded.")
        heading("Independent final", 4)
        final = trial.get("final")
        if final and (final.get("assessment") or final.get("verdict")):
            fields = _final_rows(final)
            table([label for label, _ in fields], [[value for _, value in fields]])
            cases = _case_rows(final)
            if cases:
                table(("Case", "Baseline median (ms)", "Candidate median (ms)", "Speedup",
                       "Baseline samples", "Candidate samples"), cases)
        else:
            paragraph("No independent final recorded.")
        if trial.get("gaps"):
            table(("Trial evidence gap",), [(gap,) for gap in trial["gaps"]])

        html.append("<details><summary>Usage and evidence</summary>")
        md.extend(["#### Usage and evidence", ""])
        table(("Token scope", "Input", "Output", "Cached input", "Total", "Coverage"),
              _token_rows(trial))
        observed = trial.get("observed_settings") or {}
        candidate = (final or {}).get("selected_candidate") or {}
        evidence = [
            ("Trial ID", trial["id"]),
            ("Model", observed.get("model")),
            ("Reasoning effort", observed.get("effort")),
            ("Environment", observed.get("environment_id")),
            ("Candidate path", candidate.get("path")),
        ]
        if isinstance(trial.get("evidence"), str):
            evidence.append(("Evidence reference", trial["evidence"]))
        table(("Evidence field", "Value"), evidence)
        deliveries = trial.get("knowledge_deliveries") or []
        if deliveries:
            table(("Delivered knowledge",), [
                (entry.get("path") if isinstance(entry, dict) else entry,) for entry in deliveries
            ])
        html.append("</details></section>")

    heading("Comparison settings and source data")
    policy = report["policy"]
    table(("Metric", "Used in verdict", "Neutral tolerance"),
          [(label, name in policy["metrics"], f"{policy['tolerances'][name]:.3g}")
           for name, label in _METRICS.items()])
    paragraph(f"Minimum eligible pairs per task: {policy['minimum_pairs']}. "
              "Aggregation uses the median of paired log ratios.")
    md += ["[Download raw comparison JSON](comparison-result.json)", "",
           "JSON SHA-256: `" + json_digest + "`.", ""]
    html += ['<p><a href="comparison-result.json" download>Download raw comparison JSON</a> · '
             '<a href="report.md">Markdown report</a></p>',
             f"<p>JSON SHA-256: <code>{json_digest}</code></p>"]
    document = ('<!doctype html><html lang="en"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
                'style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
                '<title>Knowledge comparison</title><style>'
                'body{font:15px/1.55 system-ui,sans-serif;max-width:1200px;margin:32px auto;'
                'padding:0 20px;color:#172033;background:#fff}h1,h2,h3{line-height:1.2}'
                'h2{margin-top:32px}.conclusion{font-size:22px;font-weight:650}.note{color:#526078}'
                'table{border-collapse:collapse;width:100%;font-size:13px}td,th{border:1px solid '
                '#d4dbe5;text-align:left;padding:8px;white-space:pre-wrap;overflow-wrap:anywhere}'
                'th{background:#eef3f9}.scroll{overflow:auto;margin-bottom:12px}'
                'section{border-top:1px solid #d4dbe5;margin-top:24px;padding-top:8px}'
                'details{margin:12px 0}summary{cursor:pointer;font-weight:600;padding:6px 0}'
                'svg{max-width:100%;height:auto;font-size:12px}'
                'p{overflow-wrap:anywhere}</style><main>' + "".join(html) + '</main></html>')
    return "\n".join(md), document


def write_comparison_report(report: dict, directory: Path) -> dict:
    """Write JSON and escaped Markdown/HTML projections of the same derived snapshot.

    Regeneration replaces only these three known derived files. Both human
    documents identify the exact JSON digest; no source experiment is modified.
    """
    if (not isinstance(report, dict) or type(report.get("schema_version")) is not int
            or report["schema_version"] != 1 or report.get("focus") != "knowledge"):
        raise ValueError("Expected a version 1 knowledge comparison report")
    raw = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
           + "\n").encode("utf-8")
    markdown, html = _documents(report, hashlib.sha256(raw).hexdigest())
    directory = Path(directory).absolute()
    if any(parent.is_symlink() for parent in (directory, *directory.parents)):
        raise ValueError("Comparison report output cannot traverse symbolic links")
    directory.mkdir(parents=True, exist_ok=True)
    outputs = {"json": ("comparison-result.json", raw),
               "markdown": ("report.md", markdown.encode("utf-8")),
               "html": ("report.html", html.encode("utf-8"))}
    for name, _ in outputs.values():
        destination = directory / name
        if destination.is_symlink() or destination.exists() and not destination.is_file():
            raise ValueError("Comparison report destination must be a regular file")
    for name, data in outputs.values():
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=directory, prefix=".comparison-", delete=False,
            ) as out:
                temporary = Path(out.name)
                out.write(data)
            os.replace(temporary, directory / name)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
    return {key: str(directory / name) for key, (name, _) in outputs.items()}
