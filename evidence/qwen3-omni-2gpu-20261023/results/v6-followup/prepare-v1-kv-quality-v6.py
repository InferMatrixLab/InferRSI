from pathlib import Path
import hashlib,json,difflib
r=Path('<PATH_12>');old=r/'run-adapter-quality-v6.py';s=old.read_text()
control=r/'v6-v1-predictor-kv-control.yaml';candidate=r/'v6-v1-predictor-kv-only.yaml'
control.write_text(candidate.read_text().replace('# UNTESTED isolated V1 incremental predictor KV candidate.','# UNTESTED isolated V1 control with predictor incremental KV disabled.').replace('code_predictor_kv_cache: true','code_predictor_kv_cache: false'))
s=s.replace('Private adapter-only v6 quality pilot','Private V1 predictor-KV-only v6 quality pilot')
s=s.replace("a.expected_sha = {'baseline':'557097940fb38a2579af104997a387749c2a47a1', 'candidate':'4645c450ba4ed036433a30dfcb9782f22b0c3bfd'}[a.arm]", "a.expected_sha = '4645c450ba4ed036433a30dfcb9782f22b0c3bfd'")
s=s.replace("a.config = '<PATH_21>'", "a.config = '<PATH_11>' + {'baseline':'v6-v1-predictor-kv-control.yaml','candidate':'v6-v1-predictor-kv-only.yaml'}[a.arm]")
start=s.index("repo = Path('<PATH_22>'")
end=s.index('campaign = Path(',start)
s=s[:start]+'''repo = Path('<PATH_13>')
if pins['source_sha'] != a.expected_sha or pins['configs'][a.arm] != a.config:
    raise RuntimeError('Wrong source/config pins for V1 KV pilot')
# Exact parsed configuration contrast: only predictor KV changes false -> true.
baseline_config = yaml.safe_load(Path(pins['configs']['baseline']).read_text())
candidate_config = yaml.safe_load(Path(pins['configs']['candidate']).read_text())
be = baseline_config['connectors']['connector_of_shared_memory']['extra']
ce = candidate_config['connectors']['connector_of_shared_memory']['extra']
if be['code_predictor_kv_cache'] is not False or ce['code_predictor_kv_cache'] is not True:
    raise RuntimeError('KV contrast missing')
ce['code_predictor_kv_cache'] = False
if candidate_config != baseline_config:
    raise RuntimeError('Configuration contrast changes more than predictor KV')
''' +s[end:]
s=s.replace('v6-adapter-quality-','v6-v1-kv-quality-').replace('adapter-quality-v6-private','v1-kv-quality-v6-private')
s=s.replace("'CUDA_MPS_LOG_DIRECTORY']:","'CUDA_MPS_LOG_DIRECTORY', 'VLLM_TUNED_CONFIG_FOLDER']:")
s=s.replace("        # Native benchmark warmup", "        kv_active = 'code_predictor: torch.compile + incremental K/V decoding' in startup\n        if kv_active != (a.arm == 'candidate'):\n            raise RuntimeError('Actual predictor KV activation differs from selected arm')\n        record['predictor_kv_activation_verified'] = True\n        record['predictor_kv_observed'] = kv_active\n        # Native benchmark warmup")
new=r/'run-v1-kv-quality-v6.py';new.write_text(s)
(r/'v1-kv-quality-v6-harness.diff').write_text(''.join(difflib.unified_diff(old.read_text().splitlines(True),s.splitlines(True),fromfile=old.name,tofile=new.name)))
