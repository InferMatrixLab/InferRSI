#!<PATH_27> python3
"""Actual-checkpoint Code2Wav first-frame parity diagnostic; no speech quality claim."""
import argparse,hashlib,json,math,subprocess,sys
from pathlib import Path
from types import SimpleNamespace

def finite_or_none(value):
 value=float(value)
 return value if math.isfinite(value) else None

def source_guard(repo,expected_sha):
 repo=Path(repo).resolve()
 head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
 dirty=subprocess.check_output(['git','-C',str(repo),'status','--porcelain','--untracked-files=normal'],text=True)
 if head!=expected_sha or dirty:raise RuntimeError('Source guard rejected HEAD mismatch or dirty worktree')
 return {'head':head,'clean':True}

def imported_sources():
 prefixes=('vllm_omni.model_executor.models.qwen3_omni','vllm_omni.model_executor.models.common.snake_activation',
  'transformers.models.qwen3_omni_moe','vllm.model_executor.models.utils')
 out={}
 for name,module in sorted(sys.modules.items()):
  path=getattr(module,'__file__',None)
  if name.startswith(prefixes) and path and Path(path).is_file():
   out[name]={'path':str(Path(path).resolve()),'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest()}
 return out

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--checkpoint',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 p.add_argument('--repo',type=Path,default=Path('<PATH_21>'))
 p.add_argument('--expected-sha',default='4645c450ba4ed036433a30dfcb9782f22b0c3bfd')
 p.add_argument('--device',choices=['cpu','cuda'],default='cpu');p.add_argument('--load-only',action='store_true')
 p.add_argument('--dtype',choices=['bfloat16','float32'],default='bfloat16')
 p.add_argument('--fused-snake',action='store_true');p.add_argument('--cudnn-benchmark',action='store_true')
 a=p.parse_args()
 if a.output.exists():p.error('output must be new')
 if a.device=='cpu' and not a.load_only:p.error('CPU mode is constructor/loader smoke only; pass --load-only')
 before=source_guard(a.repo,a.expected_sha)
 script_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 a.output.mkdir(parents=True)
 import torch
 from safetensors import safe_open
 from transformers.models.qwen3_omni_moe.configuration_qwen3_omni_moe import Qwen3OmniMoeCode2WavConfig
 from vllm_omni.model_executor.models.qwen3_omni.qwen3_omni_code2wav import Qwen3OmniMoeCode2Wav
 from vllm_omni.model_executor.models.qwen3_omni.first_frame_decoder import Qwen3OmniFirstFrameDecoder
 source_files=imported_sources()
 for module_name,record in source_files.items():
  if module_name.startswith('vllm_omni.') and not Path(record['path']).is_relative_to(a.repo.resolve()):raise RuntimeError('Imported Omni source outside pinned repo')
 torch.set_num_threads(1);torch.set_grad_enabled(False)
 dtype=getattr(torch,a.dtype);torch.set_default_dtype(dtype)
 cfgraw=json.loads((a.checkpoint/'config.json').read_text())['code2wav_config']
 cfg=Qwen3OmniMoeCode2WavConfig(**cfgraw)
 cfg._attn_implementation='sdpa'
 extra={'codec_fused_snake':a.fused_snake,'codec_cudnn_benchmark':a.cudnn_benchmark}
 vc=SimpleNamespace(model_config=SimpleNamespace(hf_config=cfg,stage_connector_config={'extra':extra}),device_config=SimpleNamespace(device=a.device))
 mapping=json.loads((a.checkpoint/'model.safetensors.index.json').read_text())['weight_map']
 names=sorted(k for k in mapping if k.startswith('code2wav.'))
 manifest=[]
 def weights():
  for shard in sorted({mapping[k] for k in names}):
   with safe_open(a.checkpoint/shard,framework='pt',device='cpu') as sf:
    for name in names:
     if mapping[name]==shard:yield name,sf.get_tensor(name)
 for name,t in weights():
  manifest.append({'name':name,'shape':list(t.shape),'dtype':str(t.dtype),'bytes':t.numel()*t.element_size(),'sha256':hashlib.sha256(t.contiguous().view(torch.uint8).numpy().tobytes()).hexdigest()})
 report={'status':'INCONCLUSIVE','scope':'CPU actual-weight loader only' if a.load_only else 'Actual codec operator parity; not full-model quality',
  'checkpoint':a.checkpoint.name,'config_sha256':hashlib.sha256((a.checkpoint/'config.json').read_bytes()).hexdigest(),
  'script_sha256':script_hash,'source_before':before,'imported_sources_before':source_files,'run_arguments':{k:str(v) if isinstance(v,Path) else v for k,v in vars(a).items()},'codec_weights':manifest,
  'codec_bytes':sum(x['bytes'] for x in manifest),'dtype':a.dtype,'device':a.device,'connector_extra':extra,
  'input_semantics':'One frame, 16 code groups, valid IDs [0,codebook_size); same IDs across two independently loaded codec instances',
  'comparisons':[],'limits':['No sampler or request routing tested','No waveform tolerance implies speech-quality acceptance','Same-process cuDNN selection does not test independent-process algorithm divergence']}
 def save(): (a.output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
 def guard_after():
  report['source_after']=source_guard(a.repo,a.expected_sha)
  report['imported_sources_after']=imported_sources()
  for key,value in source_files.items():
   if report['imported_sources_after'].get(key)!=value:raise RuntimeError('Imported source changed during run')
  if hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=script_hash:raise RuntimeError('Diagnostic script changed during run')

 save()
 def build():
  with torch.device(a.device):model=Qwen3OmniMoeCode2Wav(vllm_config=vc).eval()
  loaded=model.load_weights(weights())
  missing=sorted(set(dict(model.named_parameters()))-set(loaded))
  if missing:raise RuntimeError(f'Unloaded parameters: {missing}')
  model.precompute_snake_caches()
  return model,sorted(loaded)
 native,loaded=build();report['loaded_parameter_names']=loaded
 report['native_parameter_count']=sum(t.numel() for t in native.parameters())
 if a.load_only:
  report['status']='PASS';report['scope']='CPU actual-checkpoint constructor and complete parameter loader only';guard_after();save();print(json.dumps({'status':'PASS','codec_bytes':report['codec_bytes'],'loaded':len(loaded)}));return
 other,other_loaded=build(); assert loaded==other_loaded
 first=Qwen3OmniFirstFrameDecoder(other,sample_rate=24000)
 report.update(torch=torch.__version__,cuda=torch.version.cuda,cudnn=torch.backends.cudnn.version(),gpu=torch.cuda.get_device_name(),capability=torch.cuda.get_device_capability())
 def metrics(x,y,label,batch,codes):
  x=x.float();y=y.float();shape_equal=x.shape==y.shape
  r={'label':label,'batch':batch,'shape_a':list(x.shape),'shape_b':list(y.shape),'shape_equal':shape_equal,
     'finite_a':bool(x.isfinite().all()),'finite_b':bool(y.isfinite().all()),'range_a':[finite_or_none(x.min()),finite_or_none(x.max())],'range_b':[finite_or_none(y.min()),finite_or_none(y.max())],
     'nonfinite_count_a':int((~x.isfinite()).sum()),'nonfinite_count_b':int((~y.isfinite()).sum()),
     'codes_sha256':hashlib.sha256(codes.cpu().numpy().tobytes()).hexdigest()}
  if shape_equal:
   delta=x-y;r.update(bitwise_equal=torch.equal(x,y),max_abs=finite_or_none(delta.abs().max()),mean_abs=finite_or_none(delta.abs().mean()),rmse=finite_or_none(delta.square().mean().sqrt()),
      reference_rms=finite_or_none(x.square().mean().sqrt()),num_different=int((x!=y).sum()))
  if label=='firstframe_return_storage_after_next_replay':
   r['required_invariant']='exact returned-buffer stability across later replay'
   r['invariant_pass']=bool(shape_equal and torch.equal(x,y))
  if not r['finite_a'] or not r['finite_b']:
   artifact=f'nonfinite-{len(report["comparisons"]):03d}.pt'
   torch.save({'a':x.cpu(),'b':y.cpu(),'codes':codes.cpu()},a.output/artifact)
   r['nonfinite_artifact']=artifact
   r['nonfinite_artifact_sha256']=hashlib.sha256((a.output/artifact).read_bytes()).hexdigest()
  report['comparisons'].append(r);save()
 gen=torch.Generator(device='cpu').manual_seed(20261024)
 inputs={b:torch.randint(0,cfg.codebook_size,(b,cfg.num_quantizers),generator=gen).to(a.device) for b in [1,2,4,8]}
 (a.output/'inputs.json').write_text(json.dumps({str(b):v.cpu().tolist() for b,v in inputs.items()},indent=2)+'\n')
 eager={}
 with torch.inference_mode():
  for b,codes in inputs.items():
   full=native(codes.unsqueeze(-1))[:,0,:].float().clone(); eager[b]=full
   fast=first.decode(codes)
   metrics(full,fast,'native_forward_vs_firstframe_eager',b,codes)
   cropped=torch.stack(native.chunked_decode_streaming(codes.unsqueeze(-1),left_context_size=[0]*b,seq_token_counts=[cfg.num_quantizers]*b))[:,0,:].float()
   metrics(full,cropped,'native_forward_vs_streaming_crop',b,codes)
   singles=torch.cat([native(row[None,:,None])[:,0,:].float() for row in codes],0)
   metrics(singles,full,'native_singletons_vs_batched',b,codes)
  first.capture([1,2,4,8])
  for b,codes in inputs.items():
   fast=first.decode(codes);metrics(eager[b],fast,'native_eager_vs_firstframe_graph',b,codes)
   # Independently capture native forward, without first-frame wrapper.
   static=codes.unsqueeze(-1).clone();stream=torch.cuda.Stream();stream.wait_stream(torch.cuda.current_stream())
   with torch.cuda.stream(stream):
    for _ in range(3):native(static)
   torch.cuda.current_stream().wait_stream(stream);torch.cuda.synchronize()
   graph=torch.cuda.CUDAGraph()
   with torch.cuda.graph(graph,stream=stream): native_graph_out=native(static)
   graph.replay();torch.cuda.synchronize()
   metrics(native_graph_out[:,0,:],fast,'native_graph_vs_firstframe_graph',b,codes)
   saved=fast.clone();first.decode((codes+1)%cfg.codebook_size)
   metrics(saved,fast,'firstframe_return_storage_after_next_replay',b,codes)
   graph.reset()
 report['status']='PASS' if all(r['shape_equal'] and r['finite_a'] and r['finite_b'] and r.get('invariant_pass',True) for r in report['comparisons']) else 'FAIL'
 report['scope']='Diagnostic execution/shape/finiteness and exact returned-buffer lifetime invariant only; arithmetic differences reported without invented quality tolerance'
 report['total_upsample']=int(native.total_upsample);guard_after();save()
 print(json.dumps({'status':report['status'],'comparisons':len(report['comparisons']),'max_abs':max((r['max_abs'] for r in report['comparisons'] if r.get('max_abs') is not None),default=None)}))
if __name__=='__main__':main()
