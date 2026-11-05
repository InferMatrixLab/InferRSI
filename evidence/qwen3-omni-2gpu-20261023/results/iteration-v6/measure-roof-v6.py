import json,time,statistics,torch
from pathlib import Path
out={'scope':'Empirical operation envelopes, not hardware theoretical peaks or service bounds','torch':torch.__version__,'devices':[]}
for dev in range(2):
 torch.cuda.set_device(dev)
 p=torch.cuda.get_device_properties(dev)
 row={'logical_device':dev,'name':p.name,'compute_capability':[p.major,p.minor],'sm_count':p.multi_processor_count,'l2_bytes':p.L2_cache_size,'total_memory_bytes':p.total_memory,'copy':[],'bf16_mm':[]}
 def measure(fn):
  for _ in range(5):fn()
  torch.cuda.synchronize(); vals=[]
  for _ in range(7):
   s,e=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
   s.record()
   for _ in range(10):fn()
   e.record();e.synchronize();vals.append(s.elapsed_time(e)/10)
  return vals
 for mb in (64,256,1024):
  x=torch.ones(mb*1024*1024//2,device='cuda',dtype=torch.bfloat16);y=torch.empty_like(x)
  ts=measure(lambda:y.copy_(x)); row['copy'].append({'buffer_MiB':mb,'ms':ts,'read_write_GB_s':2*x.numel()*2/(statistics.median(ts)/1000)/1e9});del x,y
 for n in (2048,4096,8192):
  x=torch.randn(n,n,device='cuda',dtype=torch.bfloat16);y=torch.randn_like(x);z=torch.empty_like(x)
  ts=measure(lambda:torch.mm(x,y,out=z));row['bf16_mm'].append({'n':n,'ms':ts,'TFLOP_s':2*n**3/(statistics.median(ts)/1000)/1e12});del x,y,z
 out['devices'].append(row)
 torch.cuda.empty_cache()
Path('<PATH_28>').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
