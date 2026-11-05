"""Paired descriptive bootstrap; does not alter the frozen directional gates."""
import argparse,json
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
b=json.loads(a.baseline.read_text())['rows'];c=json.loads(a.candidate.read_text())['rows'];assert set(b)==set(c)
ids=sorted(b);rng=np.random.default_rng(20261021);indices=rng.integers(0,len(ids),size=(10000,len(ids)))
out={'scope':'Descriptive paired bootstrap over prompts; no noninferiority margin, no gate change and no proof of equivalence','n':len(ids),'replicates':10000,'seed':20261021,'metrics':{}}
for metric in ('sim','utmos'):
 delta=np.array([c[i][metric]-b[i][metric] for i in ids]);draws=delta[indices].mean(axis=1)
 out['metrics'][metric]={'candidate_minus_baseline':float(delta.mean()),'percentile_95_ci':[float(x) for x in np.percentile(draws,[2.5,97.5])]}
a.out.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
