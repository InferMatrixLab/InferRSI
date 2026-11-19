"""InferRSI AB/BA project adapter. Works only on frozen real-GPU pilot evidence."""
import argparse
from pathlib import Path
import json
import signal

from trial import dump, run

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--project", required=True, type=Path)
p.add_argument("--result", required=True, type=Path)
args = p.parse_args()
args.project = args.project.resolve()
where = Path(__file__).resolve().parent
params = json.loads((where/"conditions.json").read_text())
canonical = where/"pilot.json"
args.model = Path(params["model"])
args.gpu = params["gpu"]
args.out = args.result.resolve().parent/"raw-h3-http"
args.start_timeout = 1800
args.request_timeout = 600
candidate_cfg = args.project/"vllm_omni"/"h3_kb516_trial.json"
args.config = candidate_cfg if candidate_cfg.is_file() else None
args.reference = canonical
def terminate(*_):
    raise KeyboardInterrupt("terminated")
signal.signal(signal.SIGTERM, terminate)
trial = run(args)
if trial.get("contamination"):
    raise RuntimeError("foreign or unverified device process; comparison inconclusive")
if trial["admission"]["uuid"] != params["uuid"]:
    raise RuntimeError("physical device assignment drifted from the frozen pilot")
# An RGB mismatch also invalidates a measurement after a separately passing quality step.
record = {"passed":trial["passed"],"latency_s":trial["latency_s"],"raw":"raw-h3-http/trial.json"}
if not trial["passed"]:
    record.update(status="candidate_failure", reason=trial.get("quality_error","failed image check"))
dump(args.result, record)

