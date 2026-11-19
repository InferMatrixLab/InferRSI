"""Freeze and drive the real InferRSI project campaign on either pinned KB checkout."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from uuid import uuid4

from trial import PROMPTS, WORKLOAD, dump

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PIN = "51f54de16b08416182926b8f071034422561f99c"
TASK = """Single B300 MiniMax-H3-Image T2I performance on vllm-omni main.
Optimize median HTTP E2E image latency by 20% versus the fixed upstream baseline with the same
4K size, six native steps, model snapshot, prompt/seed suite, one warmup and three serial timed
images (seeds 43,44,45). Strict exact decoded RGB after matching baseline.
Use three hypotheses per arm, six total independent proposals. AB/BA experiment: 2 repetitions;
each trial launches its own clean service and measures 3 hot requests. Changing model inputs,
weights, resolution, step count, or returning cached generated requests violates the protocol.
Retain separately the count of common hypotheses, retrieval quality and GPU results.
"""

def run_cli(a, argv):
    src = (ROOT/"kb"/a.arm/"src").resolve(strict=True)
    if not (src/"inferrsi").is_dir():
        raise ValueError(f"Missing InferRSI checkout under {src}")
    env = os.environ.copy()
    env.update(PYTHONPATH=str(src),PYTHONDONTWRITEBYTECODE="1")
    cmd = [sys.executable, "-m", "inferrsi", "campaign", *argv, "--directory", str(a.directory)]
    print(shlex.join(cmd), flush=True)
    return subprocess.run(cmd,cwd=ROOT,env=env,check=False).returncode

def start(a):
    pilot = json.loads(a.pilot.read_text())
    project = a.project.resolve(strict=True)
    if subprocess.check_output(["git","rev-parse","HEAD"],cwd=project,text=True).strip() != PIN:
        raise ValueError("pilot baseline checkout must be at the tested upstream commit")
    if subprocess.check_output(["git","status","--porcelain=v1","--untracked-files=all","--","vllm_omni","pyproject.toml"],cwd=project,text=True).strip():
        raise ValueError("baseline candidate source has uncommitted changes")
    samples = pilot.get("samples", [])
    if (not pilot.get("passed") or pilot.get("contamination") or not pilot.get("monitor_samples") or
            pilot.get("workload") != WORKLOAD or len(samples) != 3 or pilot.get("candidate_config") or
            pilot.get("gpu") not in range(4) or
            [(s["prompt"],s["seed"]) for s in samples] != [(p,42+i) for i,p in enumerate(PROMPTS) if i]):
        raise ValueError("Need uncontaminated matching upstream pilot trial.json with 3 full images")
    model = Path(pilot["model_snapshot"]).resolve(strict=True)
    inputs = HERE/("frozen-input-"+a.arm+"-"+uuid4().hex[:8])
    inputs.mkdir()
    for name in ("trial.py", "step.py"):
        shutil.copyfile(HERE/name, inputs/name)
    shutil.copyfile(a.pilot, inputs/"pilot.json")
    dump(inputs/"conditions.json",{"model":str(model),"model_revision":a.model_revision,
        "gpu":pilot["gpu"],"uuid":pilot["admission"]["uuid"],"engine_commit":PIN,
        "pilot_sha256":hashlib.sha256(a.pilot.read_bytes()).hexdigest()})
    (inputs/"TASK.md").write_text(TASK)
    step = '"{python}" "{protocol}/step.py" --project "{candidate}" --result "{result}"'
    return run_cli(a,["start","--repo",str(project),"--include","vllm_omni","--include","pyproject.toml",
        "--protocol",str(inputs),"--instructions",str(inputs/"TASK.md"),"--measure-command",step,"--quality-command",step,
        "--metric-key","latency_s","--metric-unit","seconds","--direction","minimize","--quality-key","passed",
        "--scope","hot single-B300 H3 HTTP T2I, complete PNG response, 4096x4096 six steps, serial batch 1",
        "--min-improvement-pct","20","--warmups","0","--repetitions","2","--rounds","3","--round-mode","exact",
        "--max-minutes",str(a.max_minutes),"--evaluation-timeout-seconds",str(a.timeout),"--knowledge","on",
        "--condition","kb-"+a.arm,"--python",sys.executable])

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arm",choices=["old","new"])
    parser.add_argument("--directory",type=Path,help="Default ROOT/campaign-{arm}")
    sub = parser.add_subparsers(dest="action",required=True)
    s = sub.add_parser("start",help="Freeze controller. Uses a completed neutral pilot trial, no GPU process here.")
    s.add_argument("--pilot",type=Path,required=True)
    s.add_argument("--project",type=Path,required=True)
    s.add_argument("--model-revision",required=True)
    s.add_argument("--max-minutes",type=float,default=1440)
    s.add_argument("--timeout",type=int,default=10800,help="Entire quality+AB/BA evaluation seconds")
    k = sub.add_parser("knowledge")
    k.add_argument("query")
    r = sub.add_parser("round",help="Schedules a real quality/AB-BA evaluation immediately")
    r.add_argument("--candidate",type=Path,required=True)
    r.add_argument("--hypothesis",required=True)
    r.add_argument("--knowledge-ref",action="append",default=[])
    r.add_argument("--retry-of")
    sub.add_parser("status")
    sub.add_parser("final",help="Re-evaluates retained best or baseline; uses the GPU")
    a=parser.parse_args()
    a.directory = a.directory.resolve() if a.directory else ROOT/("campaign-"+a.arm)
    if a.action == "start":
        return start(a)
    if a.action == "knowledge":
        return run_cli(a,["knowledge","--query",a.query,"--context-bytes","8192","--limit","5"])
    if a.action == "round":
        flags=[]
        for ref in a.knowledge_ref:
            flags.extend(["--knowledge-ref",ref])
        if a.retry_of:
            flags.extend(["--retry-of",a.retry_of])
        return run_cli(a,["round","--candidate",str(a.candidate.resolve(strict=True)),"--hypothesis",a.hypothesis,*flags])
    return run_cli(a,[a.action])

if __name__ == "__main__":
    sys.exit(main())

