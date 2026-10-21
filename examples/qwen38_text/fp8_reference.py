"""Offline, pinned Transformers FP8 reference binding and loaded-weight guards.

Imports remain lazy so control-plane smoke requires no Torch or kernel package.
"""

import copy
import hashlib
import json
import os
import re
from pathlib import Path

KERNEL_REPO = "kernels-community/finegrained-fp8"


def kernel_fingerprint(kernel):
    root = Path(kernel.__file__).absolute().parent.resolve(strict=True)
    return _package_fingerprint(root)


def _package_fingerprint(root):
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        resolved = path.resolve(strict=True)
        # Hugging Face snapshots link individual files to this repository's blob cache.
        cached_blob = (len(root.parents) >= 4 and root.parent.name == "build"
                       and root.parents[2].name == "snapshots"
                       and resolved.is_relative_to(root.parents[3] / "blobs"))
        if not resolved.is_relative_to(root) and not cached_blob:
            raise ValueError("Reference kernel source escapes package/cache")
        files.append({"path": path.relative_to(root).as_posix(),
                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    if not files:
        raise ValueError("Reference kernel source missing")
    snapshot = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return {"files": files, "snapshot_sha256": snapshot}


def prepare_reference_kernel(revision, expected_sha256):
    if (not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision)
            or not isinstance(expected_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)):
        raise ValueError("FP8 reference requires frozen kernel revision and source SHA-256")
    if os.environ.get("HF_HUB_OFFLINE") != "1" or os.environ.get("TRANSFORMERS_OFFLINE") != "1":
        raise ValueError("FP8 reference requires offline caches before process startup")
    os.environ["TRANSFORMERS_DISABLE_DEEPGEMM_LINEAR"] = "1"
    from transformers.integrations import finegrained_fp8, hub_kernels

    # Reject prior lazy loading: it may have resolved an unpinned version.
    if (finegrained_fp8._FINEGRAINED_FP8 is not None
            or hub_kernels._KERNEL_MODULE_MAPPING.get("finegrained-fp8") is not None):
        raise ValueError("Reference kernel was loaded before pinning")
    hub_kernels._HUB_KERNEL_MAPPING["finegrained-fp8"] = {
        "repo_id": KERNEL_REPO, "revision": revision,
    }
    kernel = hub_kernels.lazy_load_kernel("finegrained-fp8")
    if kernel is None or not all(callable(getattr(kernel, name, None)) for name in (
        "matmul_2d", "matmul_batched", "matmul_grouped",
    )):
        raise ValueError("Pinned reference kernel lacks required FP8 entrypoints")
    root = Path(kernel.__file__).absolute().parent.resolve(strict=True)
    if root.name != "torch-cuda":
        raise ValueError("Reference kernel is not the prepared torch-cuda build")
    if (len(root.parents) >= 3 and root.parents[2].name == "snapshots"
            and root.parents[1].name != revision):
        raise ValueError("Reference cache origin has wrong revision")
    fingerprint = kernel_fingerprint(kernel)
    if fingerprint["snapshot_sha256"] != expected_sha256:
        raise ValueError("Reference kernel differs from frozen source")
    finegrained_fp8.load_finegrained_fp8_kernel()
    return {"repo_id": KERNEL_REPO, "repo_type": "kernel",
            "revision": revision, "build": "torch-cuda", "package_root": str(root), **fingerprint}


def recheck_reference_kernel(record):
    """Require the prepared package to remain unchanged through trial execution."""
    root = Path(record["package_root"]).resolve(strict=True)
    if str(root) != record["package_root"]:
        raise ValueError("Reference kernel package origin changed during execution")
    fingerprint = _package_fingerprint(root)
    if any(fingerprint[key] != record[key] for key in ("files", "snapshot_sha256")):
        raise ValueError("Reference kernel source changed during execution")


def expected_fp8_modules(index):
    """Derive text projections from authenticated checkpoint scale/weight pairs."""
    weights = index["weight_map"]
    if (not isinstance(weights, dict)
            or any(not isinstance(key, str) or not isinstance(value, str)
                   for key, value in weights.items())):
        raise ValueError("Reference FP8 weight index is invalid")
    suffix = ".weight_scale_inv"
    names = {name[:-len(suffix)] for name in weights
             if name.startswith("model.language_model.layers.") and name.endswith(suffix)}
    if not names or any(name + ".weight" not in weights for name in names):
        raise ValueError("Reference FP8 checkpoint projection coverage missing")
    return names


def adapt_reference_config(config, index, module_names):
    """Remove only nonexistent dense gate aliases that shadow indexed gate_proj.

    Transformers' skip matcher treats skip entries as unanchored regex prefixes.
    The official dense checkpoint also contains MoE-only `.mlp.gate` aliases;
    those incorrectly exclude `.mlp.gate_proj`. A real meta model's module tree
    and the authenticated index must independently confirm each exact removal.
    """
    expected = expected_fp8_modules(index)
    layers = config["text_config"]["num_hidden_layers"]
    if (config.get("model_type") != "qwen3_5" or type(layers) is not int or layers <= 0
            or not expected.issubset(module_names)):
        raise ValueError("Reference configuration/module tree mismatch")
    skip = config["quantization_config"]["modules_to_not_convert"]
    if not isinstance(skip, list) or any(not isinstance(name, str) for name in skip):
        raise ValueError("Reference exclusion list is invalid")
    aliases = [f"model.language_model.layers.{layer}.mlp.gate" for layer in range(layers)]
    if any(alias in module_names or skip.count(alias) != 1 or alias + "_proj" not in expected
           for alias in aliases):
        raise ValueError("Reference dense gate alias identity is not established")
    adapted = copy.deepcopy(config)
    adapted["quantization_config"]["modules_to_not_convert"] = [
        name for name in skip if name not in aliases]

    def identity(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                         allow_nan=False).encode()).hexdigest()

    return adapted, {"policy": "remove_nonexistent_dense_gate_aliases", "version": 1,
                     "original_config_sha256": identity(config),
                     "adapted_config_sha256": identity(adapted),
                     "config_identity_encoding": "sorted_compact_json_utf8",
                     "removed_exclusions": aliases,
                     "expected_fp8_modules": sorted(expected)}


def inspect_reference_fp8(model, torch, fp8_linear_type, expected_names):
    quantizer = getattr(model, "hf_quantizer", None)
    quant = getattr(quantizer, "quantization_config", None)
    if (quant is None or getattr(quant, "dequantize", None) is not False
            or getattr(quant, "activation_scheme", None) != "dynamic"
            or list(getattr(quant, "weight_block_size", ()) or ()) != [128, 128]):
        raise ValueError("Reference is dequantized or has unsupported FP8 execution")
    names = set()
    upcasts = 0
    for name, module in model.named_modules():
        if not isinstance(module, fp8_linear_type):
            continue
        names.add(name)
        if module.weight_scale_inv.dtype == torch.bfloat16:
            module.weight_scale_inv.data = module.weight_scale_inv.data.float()
            upcasts += 1
        if (module.weight.dtype != torch.float8_e4m3fn
                or module.weight_scale_inv.dtype != torch.float32
                or list(module.block_size or ()) != [128, 128]
                or module.activation_scheme != "dynamic"
                or module.activation_scale is not None):
            raise ValueError("Reference FP8 linear has dequantized or mismatched tensors")
    if (not isinstance(expected_names, (set, frozenset))
            or not expected_names or names != expected_names):
        raise ValueError("Reference FP8 module coverage differs from checkpoint")
    return {"execution": "transformers_fp8", "fp8_linear_modules": len(names),
            "fp8_module_names": sorted(names), "dequantized": False,
            "backend": "finegrained_fp8", "weight_dtype": "float8_e4m3fn",
            "activation_dtype": "bfloat16", "scale_dtype": "float32",
            "scale_normalization": "lossless_float32", "bf16_scale_upcasts": upcasts}
