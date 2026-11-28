import json
import os
import sys
from pathlib import Path

source = Path(os.environ["P762_CANDIDATE_SOURCE"])
sys.path[:0] = [str(source / "src"), str(source)]

from inferrsi.apps.cli import main
from tests.fixtures.campaign_intake import write_start_record

if sys.argv[1] == "approve":
    raise SystemExit(main([
        "task", "intake", "answer", "--record", "managed.intake.json",
        "--question", sys.argv[2], "--value", "approve", "--json",
    ]))

project = Path("project")
project.mkdir()
(project / "engine.py").write_text("def compute(x):\n    return x * 2\n", encoding="utf-8")
(project / "config.json").write_text('{"metric": 10}', encoding="utf-8")
protocol = Path("protocol")
protocol.mkdir()
(protocol / "measure.py").write_text(
    "import json, sys\nfrom pathlib import Path\n"
    "value=json.loads((Path(sys.argv[1])/'config.json').read_text())\n"
    "Path(sys.argv[2]).write_text(json.dumps(value))\n",
    encoding="utf-8",
)
(protocol / "quality.py").write_text(
    "import json, runpy, sys\nfrom pathlib import Path\n"
    "compute=runpy.run_path(str(Path(sys.argv[1])/'engine.py'))['compute']\n"
    "result={'correct':compute(16)==32,'dataset':'fixture-exact-v1'}\n"
    "Path(sys.argv[2]).write_text(json.dumps(result))\n",
    encoding="utf-8",
)
Path("task.md").write_text("DSH preflight fixture. Preserve compute outputs.", encoding="utf-8")
start = [
    "session", "start", "project", "--session", "managed", "--repo", "project",
    "--include", "engine.py", "--include", "config.json", "--protocol", "protocol",
    "--instructions", "task.md",
    "--measure-command", '"{python}" "{protocol}/measure.py" "{candidate}" "{result}"',
    "--quality-command", '"{python}" "{protocol}/quality.py" "{candidate}" "{result}"',
    "--metric-key", "metric", "--metric-unit", "synthetic-units", "--direction", "maximize",
    "--quality-benchmark", "fixture-exact-v1", "--quality-key", "correct",
    "--scope", "synthetic-software-control", "--repetitions", "2", "--warmups", "1",
    "--min-improvement-pct", "1", "--rounds", "3", "--max-minutes", "5",
    "--evaluation-timeout-seconds", "20", "--knowledge", "off",
]
record = write_start_record(start)
print(json.dumps([*start, "--intake", str(record)]))
