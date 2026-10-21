"""FP8 execution guards without GPU/model imports."""

import sys
import types
from types import SimpleNamespace as NS

import pytest

from examples.qwen38_text import fp8_reference
from examples.qwen38_text.profiles import FP8_MODEL_ID, precision, validate_native_loading


@pytest.fixture
def reference_modules():
    class Linear:
        weight = NS(dtype="fp8")
        weight_scale_inv = NS(dtype="fp32")
        block_size = [128, 128]
        activation_scheme = "dynamic"
        activation_scale = None

    module = Linear()
    quant = NS(dequantize=False, activation_scheme="dynamic", weight_block_size=[128, 128])
    model = NS(hf_quantizer=NS(quantization_config=quant), modules=lambda: [module])
    torch = NS(float8_e4m3fn="fp8", float32="fp32", bfloat16="bf16")
    return model, torch, Linear, module, quant


def test_actual_fp8_tensor_coverage_is_required(reference_modules):
    model, torch, linear, module, _quant = reference_modules
    assert fp8_reference.inspect_reference_fp8(model, torch, linear, 1)["dequantized"] is False
    module.weight = NS(dtype="bf16")
    with pytest.raises(ValueError, match="dequantized"):
        fp8_reference.inspect_reference_fp8(model, torch, linear, 1)


@pytest.mark.parametrize("field,value", [("dequantize", True), ("activation_scheme", "static"),
                                         ("weight_block_size", [64, 64])])
def test_reference_quantizer_fallback_is_rejected(reference_modules, field, value):
    model, torch, linear, _module, quant = reference_modules
    setattr(quant, field, value)
    with pytest.raises(ValueError):
        fp8_reference.inspect_reference_fp8(model, torch, linear, 1)


def test_partial_fp8_model_is_rejected(reference_modules):
    model, torch, linear, _module, _quant = reference_modules
    with pytest.raises(ValueError, match="coverage"):
        fp8_reference.inspect_reference_fp8(model, torch, linear, 2)


@pytest.fixture
def offline_kernel(tmp_path, monkeypatch):
    source = tmp_path / "torch-cuda/__init__.py"
    source.parent.mkdir()
    source.write_text("# synthetic kernel package\n")
    kernel = NS(__file__=str(source), **{name: lambda: None for name in
                                      ("matmul_2d", "matmul_batched", "matmul_grouped")})
    fingerprint = fp8_reference.kernel_fingerprint(kernel)
    hub = NS(_KERNEL_MODULE_MAPPING={}, _HUB_KERNEL_MAPPING={})
    def load(name):
        assert hub._HUB_KERNEL_MAPPING[name] == {
            "repo_id": fp8_reference.KERNEL_REPO, "revision": "a" * 40,
        }
        assert __import__("os").environ["TRANSFORMERS_DISABLE_DEEPGEMM_LINEAR"] == "1"
        return kernel
    hub.lazy_load_kernel = load
    fine = NS(_FINEGRAINED_FP8=None, load_finegrained_fp8_kernel=lambda: None)
    package = types.ModuleType("transformers.integrations")
    package.finegrained_fp8, package.hub_kernels = fine, hub
    monkeypatch.setitem(sys.modules, "transformers", types.ModuleType("transformers"))
    monkeypatch.setitem(sys.modules, "transformers.integrations", package)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    return fingerprint["snapshot_sha256"], fine, kernel


def test_exact_offline_kernel_pin_and_content(offline_kernel):
    digest, _fine, _kernel = offline_kernel
    result = fp8_reference.prepare_reference_kernel("a" * 40, digest)
    assert result["snapshot_sha256"] == digest and result["repo_type"] == "kernel"
    with pytest.raises(ValueError, match="frozen source"):
        fp8_reference.prepare_reference_kernel("a" * 40, "b" * 64)


def test_online_unpinned_and_preloaded_kernels_rejected(offline_kernel, monkeypatch):
    digest, fine, _kernel = offline_kernel
    with pytest.raises(ValueError, match="frozen"):
        fp8_reference.prepare_reference_kernel("main", digest)
    fine._FINEGRAINED_FP8 = object()
    with pytest.raises(ValueError, match="before pinning"):
        fp8_reference.prepare_reference_kernel("a" * 40, digest)
    monkeypatch.delenv("HF_HUB_OFFLINE")
    with pytest.raises(ValueError, match="offline"):
        fp8_reference.prepare_reference_kernel("a" * 40, digest)


def test_native_dequantization_cannot_be_labelled_fp8():
    loading = {"scope": "text_only", "dtype": "fp8", "loaded_parameters": 3,
               **precision(FP8_MODEL_ID), "execution": "native_fp8",
               "backend": "triton_block_fp8", "fp8_linear_modules": 1}
    validate_native_loading(loading, FP8_MODEL_ID)
    loading["dequantized"] = True
    with pytest.raises(ValueError, match="precision"):
        validate_native_loading(loading, FP8_MODEL_ID)


def test_reference_scale_upcast_is_explicit_and_recorded(reference_modules):
    model, torch, linear, module, _quant = reference_modules

    class Scale:
        dtype = "bf16"
        @property
        def data(self):
            return self
        @data.setter
        def data(self, value):
            self.dtype = value.dtype
        def float(self):
            return NS(dtype="fp32")

    module.weight_scale_inv = Scale()
    result = fp8_reference.inspect_reference_fp8(model, torch, linear, 1)
    assert result["bf16_scale_upcasts"] == 1
    assert result["scale_dtype"] == "float32"
    assert module.weight.dtype == "fp8"


def test_kernel_snapshot_symlinks_cover_own_blob_cache_only(tmp_path):
    repo = tmp_path / "kernels--synthetic"
    root = repo / "snapshots" / ("a" * 40) / "build/torch-cuda"
    root.mkdir(parents=True)
    blobs = repo / "blobs"
    blobs.mkdir()
    blob = blobs / "source"
    blob.write_text("# cached synthetic kernel\n")
    init = root / "__init__.py"
    init.symlink_to(blob)
    module = NS(__file__=str(init))
    result = fp8_reference.kernel_fingerprint(module)
    assert result["files"][0]["path"] == "__init__.py"
    outside = tmp_path / "other.py"
    outside.write_text("# unrelated source\n")
    (root / "escape.py").symlink_to(outside)
    with pytest.raises(ValueError, match="escapes"):
        fp8_reference.kernel_fingerprint(module)


@pytest.mark.parametrize("change", ["modify", "delete", "add"])
def test_reference_kernel_drift_during_trial_prevents_result(offline_kernel, tmp_path, change):
    from pathlib import Path

    import numpy as np

    from examples.qwen38_text.trial import write_traces

    digest, _fine, kernel = offline_kernel
    prepared = fp8_reference.prepare_reference_kernel("a" * 40, digest)
    fp8_reference.recheck_reference_kernel(prepared)
    output = tmp_path / "trial/result.json"
    result = {"vocab_size": 2, "cases": [], "reference_kernel": prepared}

    def collect(_prompt, _continuation):
        source = Path(kernel.__file__)
        if change == "modify":
            source.write_text("# changed after preparation\n")
        elif change == "delete":
            source.unlink()
        else:
            source.with_name("late_import.py").write_text("# new source\n")
        return [np.array([0., 1.], dtype=np.float32)]

    with pytest.raises(ValueError, match="source"):
        write_traces(result, output, [{"id": "one", "max_steps": 1}], [([0], [1])],
                     collect, lambda record: fp8_reference.recheck_reference_kernel(
                         record["reference_kernel"]))
    assert not output.exists()
    # Preserve partial logits for diagnosis; they cannot substitute for result evidence.
    assert output.with_name("result-one.npz").exists()
