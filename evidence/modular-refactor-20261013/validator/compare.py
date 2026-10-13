import json
import sys
from pathlib import Path
from omnirsi.infra.artifacts import sha256
from omnirsi.model.validators.image import ImageQualityGate, compare_images

root = Path(sys.argv[1]).resolve()
plan = json.loads((root/'plan.json').read_text())
old, new = [json.loads((root/f'{arm}-run/result.json').read_text()) for arm in ('legacy','modular')]
gate = ImageQualityGate(1280,704,plan['min_ssim'],plan['min_psnr_db'],require_pixel_identity=True)
assert old['protocol'] == new['protocol']
assert old['dependency_versions'] == new['dependency_versions']
assert old['model_assets_sha256'] == new['model_assets_sha256']
assert old['source_before']['head'] == new['source_before']['head'] == plan['engine_revision']
summary = {'scope': plan['purpose'], 'control_revision':plan['control_revision'],
           'candidate_revision':plan['candidate_revision'], 'engine_revision':plan['engine_revision'],
           'protocol_sha256':new['protocol_sha256'], 'protocol':new['protocol'], 'runs':{}, 'comparisons':[]}
for arm, record in [('legacy',old),('modular',new)]:
 assert record['status'] == 'completed'
 assert record['source_integrity']['verified']
 assert all(check['verified'] for check in record['final_integrity_checks'].values())
 assert record['server_cleanup']['remaining_pids']==[]
 summary['runs'][arm] = {key:record[key] for key in (
   'status','process_to_ready_s','metrics','warmup_samples_ms','samples_ms',
   'source_integrity','server_cleanup','final_integrity_checks','guard_hashes','dependency_versions')}
 summary['runs'][arm]['result_sha256'] = sha256(root/f'{arm}-run/result.json')
for label, a, b in [('first-request',old['first_request'],new['first_request'])]+[(a['id'],a,b) for a,b in zip(old['artifacts'],new['artifacts'])]:
 result = compare_images(b,a,gate)
 assert result['verdict'] == 'PASS' and result['pixel_identical']
 summary['comparisons'].append({'id':label, 'reference_sha256':a['sha256'], 'candidate_sha256':b['sha256'], **result})
summary['functional_verdict'] = 'PASS'
summary['comparison_pairs'] = len(summary['comparisons'])
summary['latency_claim'] = 'None: one functional run per runner, no formal performance inference'
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:summary[k] for k in ('functional_verdict','comparison_pairs','control_revision','candidate_revision','engine_revision','latency_claim')},indent=2))
