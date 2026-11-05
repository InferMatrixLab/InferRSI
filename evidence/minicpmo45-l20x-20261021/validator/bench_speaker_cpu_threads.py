"""CPU-only CAM++ thread-count diagnostic; no service claim."""
import argparse,json,time,statistics
from pathlib import Path
import numpy as np
import onnxruntime as ort
p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--out',required=True);a=p.parse_args()
asset=str(Path(a.model)/'assets/token2wav/campplus.onnx')
rng=np.random.default_rng(42);inputs=[rng.standard_normal((1,t,80),dtype=np.float32) for t in [97,200,598]]
rows=[];references=None
for threads in [1,2,4,8]:
 o=ort.SessionOptions();o.intra_op_num_threads=threads;o.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_ALL
 o.add_session_config_entry('session.intra_op.allow_spinning','0')
 s=ort.InferenceSession(asset,sess_options=o,providers=['CPUExecutionProvider']);name=s.get_inputs()[0].name
 outputs=[s.run(None,{name:x})[0] for x in inputs]
 if references is None:references=outputs
 for _ in range(5):s.run(None,{name:inputs[-1]})
 times=[]
 for _ in range(20):
  start=time.perf_counter();s.run(None,{name:inputs[-1]});times.append((time.perf_counter()-start)*1000)
 rows.append({'threads':threads,'bitwise_equal':[bool(np.array_equal(x,y)) for x,y in zip(outputs,references)],'max_abs_error':[float(np.max(np.abs(x-y))) for x,y in zip(outputs,references)],'median_ms':statistics.median(times),'samples_ms':times})
 print(rows[-1]['threads'],rows[-1]['bitwise_equal'],rows[-1]['median_ms'],flush=True)
 del s
Path(a.out).write_text(json.dumps({'scope':'Synthetic CPU inputs, isolated diagnostic only; not service or speech quality','spinning':False,'rows':rows},indent=2)+'\n')
