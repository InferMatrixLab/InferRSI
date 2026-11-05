"""Prototype: serial vs parallel CPU-reference prompt preparation."""
import argparse,json,time,statistics
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import torch,numpy as np,soundfile as sf
from bench.workload import load_seed_tts_rows,make_id_sets
from vllm_omni.model_executor.models.minicpmo_4_5.minicpmo_4_5_code2wav import _normalize_reference
from vllm_omni.model_executor.models.minicpmo_4_5.minicpmo_4_5_token2wav import MiniCPMO45Token2wav
p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--out',required=True);p.add_argument('--scratch',required=True);a=p.parse_args()
torch.set_num_threads(1);torch.manual_seed(0)
model=MiniCPMO45Token2wav(str(Path(a.model)/'assets/token2wav'),device='cuda:0',drop_upstream_chunk_att_buffers=True)
_ = model._core.spk_model
rows=load_seed_tts_rows();ids=make_id_sets(rows).tuning_pool[:16];byid={r.row_id:r for r in rows};paths=[];scratch=Path(a.scratch);scratch.mkdir(exist_ok=True)
for rid in ids:
 audio,sr=sf.read(byid[rid].ref_wav_path,dtype='float32',always_2d=True);audio,sr=_normalize_reference(audio.T,sr);path=scratch/f'{rid}.wav';sf.write(path,audio.numpy(),sr,subtype='PCM_16');paths.append(str(path))
stream=torch.cuda.current_stream()
def prepare(path):
 with torch.inference_mode(),torch.autocast('cuda',enabled=False),torch.cuda.stream(stream):return model._prepare_prompt(path)
def run(workers):
 if workers==1:outputs=[prepare(path) for path in paths]
 else:
  with ThreadPoolExecutor(max_workers=workers) as pool:outputs=list(pool.map(prepare,paths))
 torch.cuda.synchronize();return outputs
reference=run(1);results=[]
for workers in [1,2,4,8]:
 outputs=run(workers);checks=[]
 for rid,b,c in zip(ids,reference,outputs):
  for index,(x,y) in enumerate(zip(b,c)):
   if isinstance(x,torch.Tensor):checks.append({'id':rid,'field':index,'equal':torch.equal(x,y),'max_abs_error':float((x.float()-y.float()).abs().max())})
 samples=[]
 for _ in range(3):
  torch.cuda.synchronize();start=time.perf_counter();run(workers);samples.append((time.perf_counter()-start)*1000)
 result={'workers':workers,'all_equal':all(x['equal'] for x in checks),'checks':checks,'median_ms_per_16_references':statistics.median(samples),'samples_ms':samples};results.append(result);print(workers,result['all_equal'],result['median_ms_per_16_references'],flush=True)
Path(a.out).write_text(json.dumps({'scope':'Component prototype only; no lifecycle integration or service qualification','reference_count':len(paths),'results':results},indent=2)+'\n')
