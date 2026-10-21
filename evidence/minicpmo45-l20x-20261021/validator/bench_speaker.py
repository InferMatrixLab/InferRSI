"""Isolated CAM++ parity and synchronized latency; not a service benchmark."""
import argparse,hashlib,json,time,statistics
from pathlib import Path
import numpy as np
import soundfile as sf
import torch
import torch.nn.functional as F
import onnxruntime as ort
from bench.workload import load_seed_tts_rows,make_id_sets
from vllm_omni.model_executor.models.minicpmo_4_5.minicpmo_4_5_code2wav import _normalize_reference
from vllm_omni.model_executor.models.step_audio2.step_audio2_token2wav import AudioResampler,kaldi
p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--out',required=True);p.add_argument('--backend',choices=['torch','trt'],required=True);p.add_argument('--ieee',action='store_true');p.add_argument('--gpu-onnx');p.add_argument('--cpu-reference',action='store_true');a=p.parse_args()
if a.ieee:
 torch.backends.cuda.matmul.allow_tf32=False
 torch.backends.cudnn.allow_tf32=False
asset=Path(a.model)/'assets/token2wav/campplus.onnx'
options=ort.SessionOptions();options.intra_op_num_threads=1;options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_ALL
cpu=ort.InferenceSession(str(asset),sess_options=options,providers=['CPUExecutionProvider'])
if a.backend=='trt':
 if a.ieee:
  from speaker_trt_ieee import get_campplus_trt
 else:
  from vllm_omni.model_executor.models.cosyvoice3.speaker_embedding_trt import get_campplus_trt
 gpu=get_campplus_trt(a.gpu_onnx or str(asset),device='cuda:0',**({'cpu_reference':True} if a.cpu_reference else {}))
else:
 from vllm_omni.model_executor.models.cosyvoice3.speaker_embedding_torch import get_campplus_torch
 gpu=get_campplus_torch(str(asset),device='cuda:0')
rows=load_seed_tts_rows();ids=make_id_sets(rows).tuning_pool[:32];byid={r.row_id:r for r in rows};feats=[]
for i in ids:
 audio,sr=sf.read(byid[i].ref_wav_path,dtype='float32',always_2d=True)
 norm,sr=_normalize_reference(audio.T,sr)
 audio16=AudioResampler(target_sr=16000).resample(norm.numpy(),orig_sr=sr)
 feat=kaldi.fbank(torch.from_numpy(audio16).unsqueeze(0),num_mel_bins=80,dither=0,sample_frequency=16000)
 feat-=feat.mean(0,keepdim=True);feats.append((i,feat))
feats.extend([(ids[0]+'-short97',feats[0][1][:97]),(ids[0]+'-short200',feats[0][1][:200])])
def run_cpu(feat):return torch.from_numpy(cpu.run(None,{cpu.get_inputs()[0].name:feat.unsqueeze(0).numpy()})[0])
quality=[]
with torch.inference_mode():
 for i,f in feats:
  ref=F.normalize(run_cpu(f),dim=-1);out=F.normalize(gpu(f).float().cpu(),dim=-1)
  quality.append({'id':i,'frames':len(f),'input_sha256':hashlib.sha256(f.numpy().tobytes()).hexdigest(),'cosine':float(F.cosine_similarity(ref,out).item()),'max_normalized_abs_error':float((ref-out).abs().max())})
 timings={}
 for label,fn in [('cpu_onnx',run_cpu),(a.backend,gpu)]:
  f=feats[0][1]
  for _ in range(10):fn(f)
  torch.cuda.synchronize();samples=[]
  for _ in range(30):
   torch.cuda.synchronize();t=time.perf_counter();fn(f);torch.cuda.synchronize();samples.append((time.perf_counter()-t)*1000)
  timings[label]={'mean_ms':statistics.mean(samples),'median_ms':statistics.median(samples),'samples_ms':samples}
passed=all(q['cosine']>=0.99999 and q['max_normalized_abs_error']<=0.001 for q in quality)
doc={'verdict':'PASS' if passed else 'FAIL','scope':'isolated speaker embedding only','backend':a.backend,'cpu_reference':a.cpu_reference,'asset_sha256':hashlib.sha256(asset.read_bytes()).hexdigest(),'quality':quality,'latency':timings,'settings':{'torch':torch.__version__,'cuda':torch.version.cuda,'cudnn_allow_tf32':torch.backends.cudnn.allow_tf32,'matmul_allow_tf32':torch.backends.cuda.matmul.allow_tf32}}
Path(a.out).write_text(json.dumps(doc,indent=2));print(json.dumps({'verdict':doc['verdict'],'latency':{k:v['median_ms'] for k,v in timings.items()},'min_cosine':min(x['cosine'] for x in quality),'max_error':max(x['max_normalized_abs_error'] for x in quality)}),flush=True)
