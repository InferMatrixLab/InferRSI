"""CPU-only descriptive all-row paired WER audit; no scorer or service invocation."""
import json,hashlib,statistics
from pathlib import Path
import numpy as np
R=Path(__file__).parent
SOURCE=Path('ENGINE_SOURCE/vllm_omni/benchmarks/data_modules/seed_tts_eval.py')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def describe(x):
 return {'n':len(x),'mean':float(np.mean(x)),'zero_wer_count':int(np.sum(x==0)),'zero_wer_fraction':float(np.mean(x==0)),
         'quantiles':{str(q):float(v) for q,v in zip([0,.25,.5,.75,.9,.95,.99,1],np.quantile(x,[0,.25,.5,.75,.9,.95,.99,1],method='linear'))}}
def main():
 paths={arm:R/f'v6-cudnn-quality-pilot01-{arm}/quality.json' for arm in ('baseline','candidate')};hashes={arm:sha(p) for arm,p in paths.items()};sourcehash=sha(SOURCE)
 data={arm:json.loads(p.read_text()) for arm,p in paths.items()};items={arm:d['seed_tts_wer_eval_items'] for arm,d in data.items()}
 assert all(len(v)==256 for v in items.values())
 for arm,rows in items.items():
  assert len({x['utterance_id'] for x in rows})==256 and all('error' not in x and np.isfinite(x['wer']) and x['wer']>=0 for x in rows)
 assert [x['utterance_id'] for x in items['baseline']]==[x['utterance_id'] for x in items['candidate']]
 assert [x['reference_raw'] for x in items['baseline']]==[x['reference_raw'] for x in items['candidate']]
 arrays={arm:np.array([x['wer'] for x in rows],dtype=np.float64) for arm,rows in items.items()}
 formula={}
 for arm,x in arrays.items():
  mean=statistics.fmean(x.tolist());reported=data[arm]['seed_tts_content_error_mean'];assert abs(mean-reported)<1e-15
  formula[arm]={'recomputed_fmean':mean,'reported':reported,'absolute_difference':abs(mean-reported)}
 b=arrays['baseline'];c=arrays['candidate'];delta=c-b
 rng=np.random.default_rng(20261024);bootstrap=np.empty(10000,dtype=np.float64)
 for start in range(0,10000,1000):bootstrap[start:start+1000]=delta[rng.integers(0,256,size=(1000,256))].mean(axis=1)
 rows=[{'row_index':i,'baseline_wer':float(b[i]),'candidate_wer':float(c[i]),'delta_candidate_minus_baseline':float(delta[i]),'contribution_to_mean_delta':float(delta[i]/256)} for i in range(256)]
 largest=sorted(rows,key=lambda x:(-abs(x['contribution_to_mean_delta']),x['row_index']))[:10]
 report={'status':'DESCRIPTIVE_ONLY_NOT_A_NEW_GATE','source_sha256':sourcehash,'source_location':'vllm_omni/benchmarks/data_modules/seed_tts_eval.py:964,1009','script_sha256':sha(Path(__file__)),'input_sha256':hashes,'formula':'Unweighted arithmetic mean of per-utterance WER (statistics.fmean(errs)), NOT reference-word-weighted corpus WER. All256 rows had valid WER and retained.','formula_checks':formula,'arms':{arm:describe(x) for arm,x in arrays.items()},'paired_delta':{'direction':'candidate - baseline; negative improves','mean':float(delta.mean()),'median':float(np.median(delta)),'improved_rows':int(np.sum(delta<0)),'equal_rows':int(np.sum(delta==0)),'worsened_rows':int(np.sum(delta>0)),'quantiles':{str(q):float(v) for q,v in zip([0,.25,.5,.75,.9,.95,.99,1],np.quantile(delta,[0,.25,.5,.75,.9,.95,.99,1],method='linear'))}},'largest_absolute_contributors':largest,'all_paired_rows':rows,'paired_bootstrap':{'seed':20261024,'replicates':10000,'generator':'numpy.default_rng PCG64','numpy_version':np.__version__,'resampling':'256 paired row indices sampled with replacement per replicate; all rows eligible equally; no trimming or outlier exclusion','statistic':'mean(candidate_wer-baseline_wer)','percentile_95_interval':np.quantile(bootstrap,[.025,.975],method='linear').tolist(),'bootstrap_mean':float(bootstrap.mean()),'bootstrap_sd':float(bootstrap.std(ddof=1))},'limitations':['Single independently generated pair does not identify cuDNN causal effect; request scheduling, sampling and ASR variation are confounded.','Bootstrap describes observed paired utterance heterogeneity conditional on this pair; it does not estimate between-service-run/seed variance or hardware causal uncertainty.','Shared voice/speaker/context and any related utterances can violate independent-row bootstrap assumptions.','Unweighted per-row WER can exceed1 and gives short/long references equal row weight; largest contributors are descriptive, not exclusion recommendations.','Existing WER gate unchanged; no new significance/promotion rule, no rows removed, no scorer rerun.','No generated/reference text or utterance identities exported; only zero-based original-order row indices.']}
 assert sha(SOURCE)==sourcehash and all(sha(paths[a])==h for a,h in hashes.items())
 out=R/'cudnn-quality-variation-v6-private.json'
 with out.open('x') as f:json.dump(report,f,indent=2,allow_nan=False);f.write('\n')
 out.chmod(0o600)
 print(json.dumps({k:report[k] for k in ['formula_checks','arms','paired_delta','largest_absolute_contributors','paired_bootstrap']},indent=2))
if __name__=='__main__':main()
