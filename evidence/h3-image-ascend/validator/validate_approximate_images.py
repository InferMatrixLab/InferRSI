"""Predeclared numerical screen; PASS does not replace visual quality review."""
import argparse,json,math
from pathlib import Path
import numpy as np
from skimage.metrics import structural_similarity
from validate_images import read_run

p=argparse.ArgumentParser();p.add_argument('--reference',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
if a.reference.resolve()==a.candidate.resolve():raise ValueError('Independent run directories required')
plan=json.loads((Path(__file__).parent/'plan/quality-exploration.json').read_text())['initial_screen']
reference=read_run(a.reference);candidate=read_run(a.candidate)
if reference.keys()!=candidate.keys():raise ValueError('Request coverage differs')
checks=[]
for key,(row,actual) in candidate.items():
 expected_row,expected=reference[key]
 if row['request']!=expected_row['request'] or actual.shape!=expected.shape:raise ValueError('Request or dimensions differ')
 difference=actual.astype(np.float32)-expected.astype(np.float32)
 mse=float(np.mean(difference*difference,dtype=np.float64));exact=mse==0
 psnr=None if exact else 10*math.log10(255**2/mse)
 ssim=float(structural_similarity(expected,actual,data_range=255,channel_axis=-1,gaussian_weights=True,sigma=1.5,use_sample_covariance=False))
 accepted=(exact or psnr>=plan['per_image_psnr_db_min']) and ssim>=plan['per_image_ssim_min']
 check={'workload':key[0],'seed':key[1],'index':key[2],'exact':exact,'psnr_db':psnr,'ssim':ssim,'mean_abs_error':float(np.abs(difference).mean()),'numerical_screen_pass':accepted}
 checks.append(check);print(json.dumps(check),flush=True)
result={'verdict':'PASS' if checks and all(c['numerical_screen_pass'] for c in checks) else 'FAIL','scope':'numerical image-quality screen only','visual_review':'pending','additional_prompt_coverage':'pending','checks':checks}
a.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
raise SystemExit(0 if result['verdict']=='PASS' else 1)
