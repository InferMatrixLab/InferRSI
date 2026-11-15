"""Render a fixed attempt for the report and Dashboard."""

from html import escape


def _text(value: object) -> str:
    if value is None:
        return "Unknown"
    if isinstance(value, list):
        return escape(", ".join(str(item) for item in value)) if value else "—"
    return escape(str(value))


def _table(rows: list[dict], columns: tuple[tuple[str, str], ...]) -> str:
    if not rows:
        return "<p>No entries recorded.</p>"
    head = "".join(f'<th scope="col">{label}</th>' for _, label in columns)
    body = [
        "<tr>" + "".join(f"<td>{_text(row[key])}</td>" for key, _ in columns) + "</tr>"
        for row in rows
    ]
    return (
        f'<div class="scroll"><table><thead><tr>{head}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>'
    )


def render_attempt(view: dict, *, title: str) -> str:
    """Present the shared read model without exposing raw log or artifact paths."""
    execution, assessment, trace = view["execution"], view["assessment"], view["trace"]
    facts = (
        ("Run", execution["run_id"]),
        ("Attempt", execution["attempt_id"]),
        ("Record revision", execution["record_version"]),
        ("Record SHA-256", view["record_ref"]["artifact"]["sha256"]),
        ("Recorded at", execution["recorded_at"]),
        ("Candidate", execution["candidate_id"]),
        ("Phase", execution["phase"]),
        ("Process outcome", execution["process_outcome"]),
        ("Exit code", execution["exit_code"]),
        ("Cleanup", execution["cleanup_status"]),
    )
    summary = "".join(f"<dt>{label}</dt><dd>{_text(value)}</dd>" for label, value in facts)
    claims = "<p>No archived assessment selected.</p>"
    if assessment is not None:
        digest = _text(view["assessment_ref"]["artifact"]["sha256"])
        claims = f"<p>Assessment SHA-256 <code>{digest}</code></p>" + _table(
            assessment["claims"],
            (("claim_id", "Claim"), ("validation_scope", "Scope"), ("verdict", "Verdict"),
             ("reasons", "Reasons"), ("missing_evidence", "Missing evidence")),
        )

    steps = _table(
        trace["steps"],
        (("step_id", "Step"), ("status", "Status"), ("started_at", "Started"),
         ("ended_at", "Ended"), ("elapsed_seconds", "Seconds"), ("exit_code", "Exit code"),
         ("reasons", "Reasons")),
    )
    checks = _table(
        trace["checks"],
        (("check_id", "Check"), ("subject", "Subject"), ("phase", "Phase"), ("status", "Status"),
         ("reasons", "Reasons")),
    )
    errors = _table(
        trace["errors"], (("code", "Code"), ("stage", "Stage"), ("retryable", "Retryable")),
    )
    name = escape(title)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="InferRSI {name}">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>InferRSI {name}</title>
<style>
body{{font:16px/1.6 system-ui,sans-serif;max-width:1050px;margin:40px auto;
padding:0 20px;background:#fafafa;color:#182432}}
section{{margin:24px 0;padding:18px;background:white;border:1px solid #ddd}}
dl{{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:4px 20px}}
dd{{margin:0;overflow-wrap:anywhere}}dt,th{{font-weight:650}}.scroll{{overflow:auto}}
table{{border-collapse:collapse;width:100%}}td,th{{padding:8px;text-align:left;
vertical-align:top;border-bottom:1px solid #ddd}}code{{overflow-wrap:anywhere}}
</style></head>
<body><main><h1>InferRSI {name}</h1>
<section><h2>Execution</h2><dl>{summary}</dl></section>
<section><h2>Archived assessment</h2>{claims}</section>
<section><h2>Trace</h2><h3>Steps</h3>{steps}<h3>Checks</h3>{checks}<h3>Errors</h3>{errors}</section>
</main></body></html>"""
