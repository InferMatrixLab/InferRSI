"""Frozen 720p-class Qwen-Image-2.1-Turbo online B300 campaign.

Uses the stdlib OmniRSI infrastructure package for source/device/process
ownership. New campaigns must freeze fresh helper hashes and references.
"""
import argparse
import ast
import importlib.metadata
import json
import os
from pathlib import Path
import socket
from statistics import mean
import subprocess
import sys
import time
import urllib.request

from omnirsi.harness.scenarios.media import collect_samples
from omnirsi.model.protocols.image import ImageProtocol
from omnirsi.infra import campaign as lifecycle
from omnirsi.infra.platforms.cuda import qualify_devices

MODEL = "Qwen/Qwen-Image-2.1-Turbo"
REVISION = "d65dbc9a7e8f6b5479e33dee6030eaab2a906509"
SIGMAS = [1.0, 0.978453, 0.95418, 0.926626, 0.89508, 0.845148, 0.704534, 0.414568]
PROMPTS = [
    'A photorealistic red fox standing in a snowy forest at dawn, detailed fur, soft sunlight, a wide landscape composition.',
    'A clean product photograph of a blue ceramic teapot and two white cups on a wooden table, natural window lighting.',
    'A colorful travel poster of a rocky ocean coast at sunset with the exact headline "OCEAN JOURNEY", readable typography.',
]
HELD_OUT_PROMPTS = [
    'A watercolor painting of a yellow bicycle beside a purple flower shop, with three hanging baskets.',
    'A studio photograph of a transparent glass vase with five orange tulips on a dark green background.',
    'A minimalist book cover reading "NIGHT GARDEN", with silver moonlight and delicate blue flowers.',
]
PROTECTED_FILES = [
    'vllm_omni/model_extras/qwen_image_21.py',
    'vllm_omni/entrypoints/openai/diffusion.py',
    'vllm_omni/entrypoints/openai/api_server.py',
    'vllm_omni/entrypoints/openai/image_api_utils.py',
    'vllm_omni/diffusion/distributed/autoencoders/autoencoder_kl_qwenimage21.py',
]
PROTECTED_METHODS = {'__init__', 'prepare_timesteps', 'prepare_latents', '_pack_latents', '_unpack_latents'}


def protocol(diagnostic=False, profile_steps=2, held_out=False):
    if not 1 <= profile_steps <= 8:
        raise ValueError('Profile steps must be 1..8')
    sigmas = [SIGMAS[i * 7 // max(1, profile_steps - 1)] for i in range(profile_steps)] if diagnostic else SIGMAS
    return {'model': MODEL, 'model_revision': REVISION, 'width': 1280, 'height': 704,
            'dtype': 'bfloat16', 'true_cfg_scale': 1.0, 'sigmas': sigmas,
            'attention_backend': 'FLASH_ATTN', 'prefix_kv_cache': 'checkpoint_default_native',
            'compile_policy': 'enforce_eager',
            'codec': 'PNG', 'response_format': 'b64_json', 'concurrency': 1,
            'pixel_mode': 'RGBA', 'output_compression': 100,
            'prompts': [{'id': f'prompt-{i:03d}-seed-{(142 if held_out else 42)+i}', 'prompt': p,
                         'seed': (142 if held_out else 42)+i} for i,p in enumerate(HELD_OUT_PROMPTS if held_out else PROMPTS)],
            'warmup_seeds': [[10042,10043,10044],[11042,11043,11044]],
            'timing': 'POST until complete HTTP JSON response downloaded; PNG decode/write outside timer',
            'conditioning_scope': 'Repeated prompts with new seeds; deterministic conditioning reuse allowed; final-image reuse forbidden'}


def protected_sources(source):
    result = {p: lifecycle.sha256(source / p) for p in PROTECTED_FILES}
    relative = 'vllm_omni/diffusion/models/qwen_image_21/pipeline_qwen_image_21.py'
    tree = ast.parse((source / relative).read_text())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in {'get_qwen_image_21_pre_process_func', 'get_qwen_image_21_post_process_func'}:
            result[relative + ':' + node.name] = lifecycle.digest(ast.dump(node, include_attributes=False))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == 'QwenImage21Pipeline':
            found = set()
            for method in node.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and method.name in PROTECTED_METHODS:
                    result[relative + ':' + method.name] = lifecycle.digest(ast.dump(method, include_attributes=False))
                    found.add(method.name)
            if found != PROTECTED_METHODS:
                raise ValueError('Protected pipeline method missing')
            break
    else:
        raise ValueError('Protected pipeline class missing')
    return result


def dependencies():
    versions = lifecycle.semantic_dependency_versions(lifecycle.dependency_versions())
    for name in ['Pillow', 'numpy', 'scikit-image', 'flash-attn-4', 'nvidia-cutlass-dsl', 'kernels']:
        versions[name] = importlib.metadata.version(name)
    return versions


def model_assets(model, cache):
    manifest = cache.parent/'artifacts/model-assets.json'
    assets = json.loads(manifest.read_text())
    if Path(assets['model']).resolve() != model or assets['revision'] != REVISION:
        raise ValueError('Model asset manifest does not match the pinned snapshot')
    actual = {str(p.relative_to(model)) for p in model.rglob('*') if p.is_file()}
    if actual != {item['path'] for item in assets['files']}:
        raise ValueError('Model file coverage changed')
    for item in assets['files']:
        stat = (model/item['path']).stat()
        if (stat.st_size, stat.st_mtime_ns) != (item['bytes'], item['mtime_ns']):
            raise ValueError('Model asset changed after SHA256 freeze')
        if lifecycle.sha256(model/item['path']) != item.get('sha256'):
            raise ValueError(f"Model asset SHA256 mismatch: {item['path']}")
    return lifecycle.sha256(manifest)


def guards():
    paths = [Path(__file__), Path(__file__).with_name('qwen21_turbo_quality.py')]
    return {**lifecycle.helper_hashes(), **{p.name: lifecycle.sha256(p) for p in paths}}


def preflight():
    return qualify_devices(count=4, device_model="B300")


def image_request(port, item, destination, settings, timeout=900):
    protocol = ImageProtocol(MODEL, 1280, 704, {
        'true_cfg_scale': 1.0, 'sigmas': settings['sigmas'],
        'output_format': 'png', 'output_compression': 100,
    })
    return protocol.request(f'http://127.0.0.1:{port}', item, destination, timeout=timeout)


def run(args):
    source, output, cache = Path(args.source_repo).resolve(), Path(args.output).resolve(), Path(args.cache_root).resolve()
    if output.exists() or output.is_relative_to(source) or cache.is_relative_to(source):
        raise ValueError('Use new output and cache paths outside source')
    if args.tp * args.ulysses != (1 if args.single_reference else 4) or args.single_reference and (args.tp,args.ulysses)!=(1,1):
        raise ValueError('Four workers required, except explicit canonical reference')
    model = Path(args.model_path).resolve()
    if model.name != REVISION or json.loads((model/'model_index.json').read_text())['sample_sigmas'] != SIGMAS:
        raise ValueError('Exact pinned snapshot and Turbo schedule required')
    output.parent.mkdir(parents=True, exist_ok=True)
    media = output.parent/'media'
    media.mkdir()
    settings = protocol(args.diagnostic, args.profile_steps, args.held_out)
    before = lifecycle.source_snapshot(source)
    frozen = protected_sources(source)
    frozen_guards = guards()
    versions = dependencies()
    asset_hash = model_assets(model, cache)
    argv = [str(Path(sys.executable).parent/'vllm'), 'serve', str(model), '--served-model-name', MODEL,
            '--omni', '--enforce-eager', '--dtype', 'bfloat16', '--num-gpus', str(args.tp*args.ulysses),
            '--tensor-parallel-size', str(args.tp), '--usp', str(args.ulysses), '--ring', '1',
            '--cfg-parallel-size', '1', '--vae-patch-parallel-size', '1', '--max-num-seqs', '1',
            '--diffusion-attention-backend', 'FLASH_ATTN', '--host', '127.0.0.1', '--port', str(args.port),
            '--stage-init-timeout', str(args.startup_timeout)]
    if args.diagnostic:
        argv += ['--profiler-config', json.dumps({'profiler':'torch','torch_profiler_dir':str(output.parent/'torch-profile'),
                  'torch_profiler_record_shapes':True,'torch_profiler_with_stack':True}),
                 '--enable-diffusion-pipeline-profiler']
    record = {'status':'running','protocol':settings,'protocol_sha256':lifecycle.digest(settings),
              'diagnostic':args.diagnostic,'parallel':{'tp':args.tp,'ulysses':args.ulysses,'vae':1,'cfg':1,'ring':1},
              'source_before':before,'protected_sources':frozen,'guard_hashes':frozen_guards,
              'dependency_versions':versions,'model_assets_sha256':asset_hash,
              'server_argv':argv,'samples_ms':[],'artifacts':[],'groups_ms':[],'warmup_samples_ms':[]}
    process = ownership = None
    try:
        record['devices'] = preflight()
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1',args.port)) == 0:
                raise ValueError('Port already occupied')
        env = os.environ.copy()
        env.pop('HF_TOKEN',None)
        env['PYTHONPATH'] = str(source)
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        env['HF_HUB_OFFLINE'] = '1'
        env['HF_HOME'] = str(cache/'huggingface')
        env['HF_MODULES_CACHE'] = str(cache/'huggingface/modules')
        for key, folder in [('TORCHINDUCTOR_CACHE_DIR','inductor'),('TRITON_CACHE_DIR','triton'),('VLLM_CACHE_ROOT','vllm'),('CUDA_CACHE_PATH','cuda')]:
            env[key] = str(cache/folder)
        preparation_start = time.monotonic()
        with (output.parent/'server.log').open('wb') as log:
            process, ownership = lifecycle.launch_server(argv,source,env,log)
            record['server_process'] = ownership
            deadline = time.monotonic()+args.startup_timeout
            while True:
                if process.poll() is not None:
                    raise ValueError('Server exited before readiness; see server.log')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/health',timeout=2) as response:
                        if response.status == 200: break
                except (OSError,TimeoutError): pass
                if time.monotonic()>deadline: raise TimeoutError('Server readiness timeout')
                time.sleep(1)
            record['process_to_ready_s'] = time.monotonic()-preparation_start
            def before_measure():
                if args.diagnostic:
                    urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{args.port}/start_profile',data=b''),timeout=60).close()

            collect_samples(
                lambda item, path: image_request(args.port, item, path, settings),
                prompts=settings['prompts'], warmup_seeds=settings['warmup_seeds'],
                repetitions=args.repetitions, media=media, record=record, suffix='.png',
                before_measure=before_measure,
            )
            if args.diagnostic:
                urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{args.port}/stop_profile',data=b''),timeout=120).close()
            else: record['metrics']={'latency_ms':mean(record['groups_ms'])}
            record['status']='completed'
    except KeyboardInterrupt:
        record.update(status='cancelled',error='interrupted')
    except Exception as error:
        record.update(status='failed',error=str(error))
    finally:
        final_errors = []
        try:
            if process is not None:
                try:
                    record['server_cleanup'] = lifecycle.stop_server(process, ownership, 20)
                    if record['server_cleanup']['remaining_pids']:
                        final_errors.append('Owned processes remain')
                except Exception as error:
                    record['server_cleanup'] = {'verified': False, 'error': str(error)}
                    final_errors.append(f'Cleanup failed: {error}')
            record['source_integrity'] = {'verified': False}
            probes = [
                ('source', lambda: lifecycle.source_snapshot(source), before),
                ('protected_sources', lambda: protected_sources(source), frozen),
                ('guards', guards, frozen_guards),
                ('dependencies', dependencies, versions),
                ('model_assets', lambda: model_assets(model, cache), asset_hash),
            ]
            record['final_integrity_checks'] = {}
            for name, probe, expected in probes:
                try:
                    actual = probe()
                    if name == 'source':
                        record['source_after'] = actual
                        matched = before['snapshot_hash'] == actual['snapshot_hash']
                        record['source_integrity']['verified'] = matched
                    else:
                        matched = actual == expected
                    record['final_integrity_checks'][name] = {'verified': matched}
                    if not matched:
                        final_errors.append(f'{name} drifted during trial')
                except Exception as error:
                    record['final_integrity_checks'][name] = {'verified': False, 'error': str(error)}
                    final_errors.append(f'{name} check failed: {error}')
            if final_errors:
                record['finalization_errors'] = final_errors
                record.update(status='failed', error='; '.join(final_errors))
        finally:
            # Failed cleanup or verification must never erase the trial record.
            lifecycle.write_json(output, record)
    return record


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-repo',required=True)
    p.add_argument('--model-path',required=True)
    p.add_argument('--cache-root',required=True)
    p.add_argument('--tp',type=int,choices=[1,2,4],default=1)
    p.add_argument('--ulysses',type=int,choices=[1,2,4],default=4)
    p.add_argument('--single-reference',action='store_true')
    p.add_argument('--diagnostic',action='store_true')
    p.add_argument('--held-out',action='store_true')
    p.add_argument('--profile-steps',type=int,choices=range(1,9),default=2)
    p.add_argument('--repetitions',type=int,default=1)
    p.add_argument('--port',type=int,default=8098)
    p.add_argument('--startup-timeout',type=int,default=1200)
    p.add_argument('--output',required=True)
    args=p.parse_args()
    if args.repetitions<1: p.error('repetitions must be positive')
    r=run(args)
    print(json.dumps({'status':r['status'],'output':args.output,'error':r.get('error')}),flush=True)
    return 0 if r['status']=='completed' else 1

if __name__=='__main__':
    raise SystemExit(main())
