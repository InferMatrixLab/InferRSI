import json,gzip,hashlib,re
from decimal import Decimal
from pathlib import Path
import ijson
r=Path(__file__).parent;run=r/'v6-adapter-profile-pilot01';e=json.loads((run/'execution.json').read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
assert e['execution_complete'] and e['diagnostic_run_complete']
for c in e['config_chain']:assert sha(Path(c['file']))==c['sha256']
log=(run/'server.log').read_text();mapping={}
for stage,logical,physical in re.findall(r'Stage (\d+) logical-to-physical device mapping: (\d+)->(\d+)',log):
 if int(stage) in mapping:assert mapping[int(stage)]==(logical,physical)
 mapping[int(stage)]=(logical,physical)
assert mapping[1]==mapping[2] and mapping[0][1]!=mapping[1][1]
def merge(a):
 a.sort();out=[]
 for s,t in a:
  if out and s<=out[-1][1]:out[-1]=(out[-1][0],max(t,out[-1][1]))
  else:out.append((s,t))
 return out
def total(a):return sum(t-s for s,t in a)
rows=[];artifacts=0
for phase in e['phases']:
 if not phase['phase'].startswith('profile-'):continue
 intervals={};meta=[]
 for ent in phase['traces']:
  p=run/ent['file'];assert p.stat().st_size==ent['bytes'] and sha(p)==ent['sha256'];artifacts+=1
  if not p.name.endswith('.json.gz'):continue
  stage=int(re.search(r'stage(\d+)/',ent['file'])[1])
  # Complete pass checks gzip trailer/CRC and JSON grammar, including base field.
  base=None
  with gzip.open(p,'rb') as f:
   for prefix,event,value in ijson.parse(f):
    if prefix=='baseTimeNanoseconds':base=int(value)
  assert base is not None
  a=[];devices=set()
  with gzip.open(p,'rb') as f:
   for ev in ijson.items(f,'traceEvents.item'):
    if ev.get('ph')=='X' and ev.get('cat')=='kernel':
     start=base+int(Decimal(str(ev['ts']))*1000);dur=int(Decimal(str(ev['dur']))*1000)
     assert dur>=0
     a.append((start,start+dur));devices.add(str(ev.get('args',{}).get('device')))
  assert a
  intervals[stage]=merge(a);meta.append({'stage':stage,'file':ent['file'],'sha256':ent['sha256'],'baseTimeNanoseconds':base,'kernel_count':len(a),'trace_local_devices':sorted(devices)})
 a,b=intervals[1],intervals[2];u=merge(a+b);ua,ub,ut=total(a),total(b),total(u);span=u[-1][1]-u[0][0]
 rows.append({'concurrency':phase['runs'][0]['concurrency'],'trace_sources':meta,'stage1_kernel_union_ms':ua/1e6,'stage2_kernel_union_ms':ub/1e6,'speech_combined_union_ms':ut/1e6,'speech_intersection_ms':(ua+ub-ut)/1e6,'speech_common_envelope_ms':span/1e6,'union_fraction_common_envelope':ut/span,'uncovered_inside_envelope_ms':(span-ut)/1e6,'first_kernel_epoch_ns':u[0][0],'last_kernel_end_epoch_ns':u[-1][1],'jit_lines_in_phase':len(phase['jit_lines'])})
report={'status':'INCONCLUSIVE','scope':'Cross-file process kernel intervals, not request critical path or available savings','execution_sha256':sha(run/'execution.json'),'server_log_sha256':sha(run/'server.log'),'verified_artifacts':artifacts,'mapping_evidence':'All config-chain hashes match execution; server startup mapping proves stage1 and stage2 share logicalGPU1 and stage0 uses separate logicalGPU0. Physical selectors omitted.','method':'gzip CRC/full JSON parse; explicit baseTimeNanoseconds + decimal ts*1000; integer ns endpoints; union and intersection on shared device only','limits':['Trace timestamps have emitted microsecond precision; ns arithmetic avoids epoch float cancellation but does not establish ns hardware accuracy.','No independent cross-process clock-skew calibration; Kineto common epoch supports alignment but small intersections near timing uncertainty should not be overinterpreted.','No stored request perf_counter-to-wall bridge; this is not an exact request window.','Kernel envelope omits startup/drain and includes any captured background kernels; gaps are not recoverable latency.','Memcpy/memset excluded; other processes not captured.','C64 retains JIT and profiler perturbation; no warmed service performance comparison.'],'rows':rows}
(r/'profile-cross-stage-union-v6.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='rows'}));print(json.dumps([{k:v for k,v in x.items() if k!='trace_sources'} for x in rows]))
