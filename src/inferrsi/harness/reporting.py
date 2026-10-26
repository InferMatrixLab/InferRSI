"""Portable HTML evidence report with escaped caller-controlled content."""

import json
from html import escape
from pathlib import Path
from urllib.parse import quote

from ..summary_chart import SpecError, build_svg, spec_from_evaluation


def write_report(run_dir: Path) -> Path:
    run_dir = Path(run_dir)

    def read(name: str) -> dict:
        path = run_dir / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    spec, status, evaluation = read("run.lock.json"), read("status.json"), read("evaluation.json")

    def dump(value: object) -> str:
        return escape(json.dumps(value, ensure_ascii=False, indent=2))

    links = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name != "report.html":
            relative = path.relative_to(run_dir).as_posix()
            links.append(f'<li><a href="./{quote(relative, safe="/")}">{escape(relative)}</a></li>')
    verdict = escape(str(evaluation.get("verdict", "INCONCLUSIVE")))
    figure = _summary_figure(run_dir, evaluation)
    report = f"""<!doctype html>
<html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>InferRSI experiment report</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;max-width:1050px;margin:40px auto;
padding:0 20px;background:#fafafa;color:#182432}}
pre{{background:white;border:1px solid #ddd;padding:16px;overflow:auto;
white-space:pre-wrap;overflow-wrap:anywhere}}
h1,h2{{line-height:1.3}}a{{color:#1558b0}}.verdict{{font-size:24px;font-weight:700}}</style>
<h1>InferRSI experiment report</h1><p class="verdict">{verdict}</p>
<p>Caller-declared units, scope and workload are preserved. These results do not establish
statistical significance or accelerator support.
Successful quality validation covers only the supplied command.</p>
<h2>Gain summary</h2>{figure}
<h2>Evaluation</h2><pre>{dump(evaluation)}</pre>
<h2>Run status</h2><pre>{dump(status)}</pre>
<h2>Frozen CLI contract</h2><pre>{dump(spec)}</pre>
<h2>Environment</h2><pre>{dump(read("environment.json"))}</pre>
<h2>Evidence files</h2><ul>{"".join(links)}</ul></html>"""
    destination = run_dir / "report.html"
    destination.write_text(report, encoding="utf-8")
    return destination


def _summary_figure(run_dir: Path, evaluation: dict) -> str:
    """Render the run's gain figure, or say plainly why it is absent.

    A report is generated at the end of every experiment, so this is where a
    finished run gets its figure without a separate command. A run with no
    paired measurement gets a sentence rather than a misleading empty chart.

    A campaign that has accumulated several steps can commit a chain
    specification as ``summary-chart.json`` beside the run; that spec wins,
    because it records the whole campaign rather than one pairing.
    """
    campaign = run_dir / "summary-chart.json"
    try:
        if campaign.is_file():
            spec = json.loads(campaign.read_text(encoding="utf-8"))
            if not isinstance(spec, dict):
                raise SpecError("summary-chart.json must hold a specification object")
        else:
            spec = spec_from_evaluation(evaluation)
        svg = build_svg(spec)
    except (SpecError, json.JSONDecodeError) as error:
        return f"<p>No gain figure: {escape(str(error))}.</p>"
    (run_dir / "summary-chart.svg").write_text(svg, encoding="utf-8")
    # Inline the figure so the report stays one self-contained file.
    return f'<figure class="summary-chart">{svg}</figure>'
