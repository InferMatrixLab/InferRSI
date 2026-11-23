"""Read and verify public metadata for the pinned Qwen checkpoint on explicit request."""

import hashlib
import json
import math
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

from model_sol import join_checkpoint


def schema_digest(headers):
    data = json.dumps(headers, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def _header_range(url, start, end):
    request = Request(f"{url}?header-range={start}-{end}",
                      headers={"Range": f"bytes={start}-{end}"})
    with urlopen(request, timeout=30) as response:
        interval = response.headers.get("Content-Range", "").partition("/")[0]
        if response.status != 206 or interval != f"bytes {start}-{end}":
            raise ValueError("Server did not return the requested header range")
        data = response.read(end - start + 1)
    if len(data) != end - start + 1:
        raise ValueError("Incomplete safetensors header range")
    return data


def _read_verified_json(url, digest):
    with urlopen(url, timeout=30) as response:
        data = response.read(4 * 1024**2)
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"Unexpected source bytes for {url}")
    return json.loads(data)


def audit_headers(facts, expected_text):
    base = f"https://huggingface.co/{facts['model']}/resolve/{facts['revision']}/"
    config = _read_verified_json(base + "config.json", facts["config_sha256"])["text_config"]
    for key, value in facts["text_config"].items():
        if config.get(key) != value:
            raise ValueError(f"Packaged model configuration differs at {key}")
    interval = config["full_attention_interval"]
    expected_layers = ["full_attention" if (i + 1) % interval == 0 else "linear_attention"
                       for i in range(config["num_hidden_layers"])]
    if config["layer_types"] != expected_layers:
        raise ValueError("Layer sequence differs from the priced GDN/QSA layout")

    evidence = facts["checkpoint"]
    index = _read_verified_json(base + "model.safetensors.index.json", evidence["index_sha256"])
    by_shard = {}
    for name, shard in index["weight_map"].items():
        by_shard.setdefault(shard, set()).add(name)

    def read(shard):
        url = base + shard
        length = int.from_bytes(_header_range(url, 0, 7), "little")
        if not 0 < length < 4 * 1024**2:
            raise ValueError(f"Unexpected header size for {shard}")
        rows = json.loads(_header_range(url, 8, 7 + length))
        rows.pop("__metadata__", None)
        if rows.keys() != by_shard[shard]:
            raise ValueError(f"Tensor names differ from the index for {shard}")
        return {key: {"shape": row["shape"], "dtype": row["dtype"]} for key, row in rows.items()}

    with ThreadPoolExecutor(max_workers=4) as pool:
        all_rows = {k: v for shard in pool.map(read, sorted(by_shard)) for k, v in shard.items()}
    stored = sum(math.prod(row["shape"]) * {"BF16": 2, "I64": 8}[row["dtype"]]
                 for row in all_rows.values())
    if (len(by_shard) != evidence["shards"] or len(all_rows) != evidence["tensors"]
            or stored != index["metadata"]["total_size"] or stored != evidence["stored_bytes"]
            or schema_digest(all_rows) != evidence["all_schema_sha256"]):
        raise ValueError("Checkpoint header inventory differs from the archived identity")

    text = {k: v for k, v in all_rows.items() if k.startswith("model.language_model.")
            or k == "lm_head.weight"}
    joined = join_checkpoint(
        {"source": {"kind": "measured", "locator": base}, "tensors": text},
        {"source": {"kind": "derived", "locator": "qwen38_h200_tp4.py:text_weights"},
         "tensors": [dict(name=k, **v) for k, v in expected_text.items()]},
    )
    if not joined["join_clean"] or text != expected_text:
        raise ValueError("Text checkpoint names, shapes or dtypes differ from the inventory")
    return {"shards": len(by_shard), "checkpoint_tensors": len(all_rows),
            "stored_bytes": stored, "text_tensors_joined": len(text), "join_clean": True,
            "read_scope": "config, index and safetensors headers only"}
