import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--model", type=Path, required=True)
parser.add_argument("--result", type=Path, required=True)
args = parser.parse_args()
from vllm_omni.config.stage_config import resolve_deploy_yaml
from vllm_omni.transformers_utils.configs.realtime_venus import RealtimeVenusOmniConfig

config = RealtimeVenusOmniConfig.from_pretrained(args.model, local_files_only=True)
deploy = resolve_deploy_yaml(str(args.source / "vllm_omni/deploy/realtime_venus_omni.yaml"))
assert (config.hidden_size, config.num_hidden_layers, config.vocab_size) == (4096, 36, 151752)
assert deploy["connectors"]["connector_of_shared_memory"]["extra"]["token2wav_n_timesteps"] == 10
assert deploy["platforms"]["cuda"]["connectors"]["connector_of_shared_memory"]["extra"]["token2wav_float16"] is False
args.result.write_text(
    json.dumps(
        {"quality_passed": True, "scope": "configuration identity; generation assertions also enforced by measurement"}
    )
)
