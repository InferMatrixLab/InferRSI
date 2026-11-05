"""Export finite metrics and artifact hashes without local paths or raw audio."""
import argparse,gzip,hashlib,json,math
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
def clean(x):
 if isinstance(x,float) and not math.isfinite(x):return None
 if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
 if isinstance(x,list):return [clean(v) for v in x]
 return x
cells=[]
for d in sorted(a.input.glob('c*/run*')):
 if not (d/'summary.json').exists():continue
 summary=json.loads((d/'summary.json').read_text())
 records=[json.loads(x) for x in (d/'requests.jsonl').read_text().splitlines()]
 # Monotonic absolute clock values have no cross-host meaning.
 for r in records:
  for k in ('t_dispatch','t_complete'):r.pop(k,None)
 files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in d.glob('*') if p.is_file()}
 wavs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (d/'wav').glob('*.wav')}
 cells.append({'cell':str(d.relative_to(a.input)),'summary':summary,'requests':records,'artifact_hashes':files,'wav_hashes':wavs})
a.output.parent.mkdir(parents=True,exist_ok=True)
plan=json.loads((a.input/'plan.json').read_text())
source_plan={k:plan[k] for k in ('eval_offset','adapter','concurrency','requests','repeats','id_set','cache_policy','qualification','ids') if k in plan}
source_plan.setdefault('id_set','eval')
payload=json.dumps(clean({'qualification':'exploratory repeated steady state; no restart between cells','source_plan':source_plan,'metadata_notes':'Summary fields such as id_set, revision and GPU retain reference-helper defaults. The source_plan and campaign manifests are authoritative; tuning selection is not inferred from summary.id_set.','cells':cells}),indent=2,allow_nan=False)+'\n'
if a.output.suffix == '.gz':
 a.output.write_bytes(gzip.compress(payload.encode(),mtime=0))
else:
 a.output.write_text(payload)
