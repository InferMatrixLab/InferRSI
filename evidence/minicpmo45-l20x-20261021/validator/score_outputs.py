"""Score saved benchmark WAVs with the pinned SGLang-Omni native scorers."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import numpy as np
import soundfile as sf
from bench.workload import load_seed_tts_rows
from benchmarks.tasks.asr import load_qwen3_asr, transcribe, apply_wer
from benchmarks.metrics.wer import SampleOutput

p=argparse.ArgumentParser()
p.add_argument('--run', required=True)
p.add_argument('--out', required=True)
p.add_argument('--scorers', required=True)
p.add_argument('--asr-port',type=int,default=29181)
p.add_argument('--device',default='cuda:0')
p.add_argument('--tasks',nargs='+',default=['wer','sim','utmos'])
a=p.parse_args()
rows={r.row_id:r for r in load_seed_tts_rows()}
metrics=[json.loads(x) for x in (Path(a.run)/'requests.jsonl').read_text().splitlines()]
assert metrics and all(x['ok'] for x in metrics)
ids=sorted(x['request_id'] for x in metrics)
assert len(ids)==len(set(ids))
wavs=[str(Path(a.run)/'wav'/f'{i}.wav') for i in ids]
out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
doc=json.loads(out.read_text()) if out.exists() else {'rows':{},'tasks':[]}
for i,w in zip(ids,wavs):
 audio,sr=sf.read(w)
 assert len(audio)>0 and np.isfinite(audio).all()
 doc['rows'].setdefault(i,{}).update({'wav_sha256':hashlib.sha256(Path(w).read_bytes()).hexdigest(),'duration_s':len(audio)/sr})
def save():
 out.write_text(json.dumps(doc,indent=2,allow_nan=False))
save()
if 'wer' in a.tasks and 'wer' not in doc['tasks']:
 asr=load_qwen3_asr(a.asr_port)
 def score(pair):
  i,w=pair
  hyp=transcribe(asr,w,'en',a.device)
  r=apply_wer(SampleOutput(sample_id=i,target_text=rows[i].target_text),hyp,'en')
  assert r.is_success, r.error
  return i,{k:getattr(r,k) for k in ('wer','substitutions','deletions','insertions','hits')}|{'hyp_text':hyp}
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  for i,result in pool.map(score,zip(ids,wavs)):
   doc['rows'][i]['wer']=result
 doc['tasks'].append('wer');save()
if 'sim' in a.tasks and 'sim' not in doc['tasks']:
 from benchmarks.metrics.speaker_similarity import WavLMSpeakerSimilarity
 s=Path(a.scorers)/'sim'
 scorer=WavLMSpeakerSimilarity(finetune_checkpoint=s/'wavlm_large_finetune.pth',wavlm_base=s/'wavlm_large.pt',device=a.device)
 for j in range(0,len(ids),4):
  scores=scorer.score_batch([rows[i].ref_wav_path for i in ids[j:j+4]],wavs[j:j+4])
  for i,v in zip(ids[j:j+4],scores):doc['rows'][i]['sim']=float(v)
 doc['tasks'].append('sim');save();del scorer
if 'utmos' in a.tasks and 'utmos' not in doc['tasks']:
 from benchmarks.metrics.utmos import UTMOSScorer
 scorer=UTMOSScorer(device=a.device,cache_dir=Path(a.scorers)/'utmos')
 for j in range(0,len(ids),8):
  scores=scorer.score_batch(wavs[j:j+8])
  for i,v in zip(ids[j:j+8],scores):doc['rows'][i]['utmos']=float(v)
 doc['tasks'].append('utmos');save()
summary={'n':len(ids)}
for k in ('sim','utmos'):
 if k in doc['tasks']:summary[k]=float(np.mean([v[k] for v in doc['rows'].values()]))
if 'wer' in doc['tasks']:
 counts={k:sum(v['wer'][k] for v in doc['rows'].values()) for k in ('substitutions','deletions','insertions','hits')}
 summary['wer']=sum(counts[k] for k in ('substitutions','deletions','insertions'))/sum(counts[k] for k in ('substitutions','deletions','hits'))
 summary['wer_counts']=counts
 summary['wer_mean']=float(np.mean([v['wer']['wer'] for v in doc['rows'].values()]))
doc['summary']=summary;save();print(json.dumps(summary),flush=True)
