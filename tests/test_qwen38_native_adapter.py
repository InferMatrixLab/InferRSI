"""Native adapter import binding and role contracts; no model/GPU execution."""

import argparse
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

from examples.qwen38_text import native_trial, provenance, trial


def test_preloaded_foreign_engine_is_rejected_before_import(tmp_path, monkeypatch):
    loader = tmp_path / "engine/nanovllm/qwen38/loader.py"
    loader.parent.mkdir(parents=True)
    loader.write_text("raise AssertionError('must not execute')\n")
    foreign = tmp_path / "foreign.py"
    foreign.write_text("# foreign installed package\n")
    module = types.ModuleType("nanovllm")
    module.__file__ = str(foreign)
    monkeypatch.setitem(sys.modules, "nanovllm", module)
    with pytest.raises(ValueError, match="escaped"):
        provenance.import_native(tmp_path / "engine")


def test_import_origin_symlink_cannot_escape_checkout(tmp_path, monkeypatch):
    root = tmp_path / "engine"
    root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("# wrong source\n")
    link = root / "module.py"
    link.symlink_to(outside)
    module = types.ModuleType("nanovllm")
    module.__file__ = str(link)
    monkeypatch.setitem(sys.modules, "nanovllm", module)
    with pytest.raises(ValueError, match="escaped"):
        provenance.import_records("nanovllm", root)


def test_foreign_namespace_search_path_is_rejected(tmp_path, monkeypatch):
    root = tmp_path / "engine"
    root.mkdir()
    module = types.ModuleType("nanovllm.qwen38")
    module.__path__ = [str(tmp_path / "foreign")]
    monkeypatch.setitem(sys.modules, "nanovllm.qwen38", module)
    with pytest.raises(ValueError, match="search path"):
        provenance.import_records("nanovllm", root)


def test_explicit_engine_import_wins_over_unrelated_installed_package(tmp_path):
    engine, foreign = tmp_path / "engine", tmp_path / "installed"
    for root in (engine, foreign):
        package = root / "nanovllm/qwen38"
        package.mkdir(parents=True)
        (root / "nanovllm/__init__.py").write_text("")
        (package / "__init__.py").write_text("")
        (package / "loader.py").write_text("def load_checkpoint(*args): return 'selected'\n")
        (package / "runner.py").write_text("class RequestRunner: pass\n")
    code = (
        "import json,sys; "
        "from examples.qwen38_text.provenance import import_native,import_records; "
        "sys.path.insert(0,sys.argv[2]); load,runner=import_native(sys.argv[1]); "
        "print(json.dumps(import_records('nanovllm',sys.argv[1])))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code, str(engine), str(foreign)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, check=True,
    )
    records = json.loads(completed.stdout)
    assert records["nanovllm.qwen38.loader"]["path"] == "nanovllm/qwen38/loader.py"
    assert len(records["nanovllm.qwen38.runner"]["sha256"]) == 64


def test_cached_reference_cannot_claim_native_baseline_scope():
    args = argparse.Namespace(qualification_scope="native_text_smoke", mode="cached")
    with pytest.raises(ValueError, match="full-prefix"):
        trial.run(args)


@pytest.fixture
def native_runtime(tmp_path, monkeypatch):
    np = pytest.importorskip("numpy")
    model_path = tmp_path / "model"
    model_path.mkdir()
    (model_path / "config.json").write_text(json.dumps({"text_config": {"vocab_size": 3}}))
    cases = [{"id": "one", "prompt": "prompt", "continuation": "next", "max_steps": 1}]
    monkeypatch.setattr(trial, "verify_manifest", lambda *_: "a" * 64)
    monkeypatch.setattr(trial, "load_workload", lambda *_: (cases, "b" * 64))
    tokenizer = types.SimpleNamespace(encode=lambda text, **_: [1] if text == "prompt" else [2])
    cuda = types.SimpleNamespace(is_available=lambda: True, device_count=lambda: 1,
                                 is_bf16_supported=lambda: True,
                                 get_device_name=lambda _: "Synthetic GPU")
    torch = types.SimpleNamespace(cuda=cuda, __version__="test",
                                  version=types.SimpleNamespace(cuda="test"))
    transformers = types.SimpleNamespace(
        __version__="test",
        AutoTokenizer=types.SimpleNamespace(from_pretrained=lambda *_a, **_kw: tokenizer),
    )  # No Transformers model API: candidate execution cannot call one.
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    calls = []
    model = type("NativeModel", (), {"__module__": "nanovllm.qwen38.model",
                                     "eval": lambda self: self})()

    def load(path, *, device):
        calls.append((path, device))
        return model, {"scope": "text_only", "dtype": "bfloat16", "loaded_parameters": 3}

    class Row:
        def float(self):
            return self

        def cpu(self):
            return self

        def numpy(self):
            return np.array([0.0, 1.0, 2.0], dtype=np.float32)

    class Runner:
        active_request_ids = ()

        def __init__(self, loaded, selected_tokenizer, **kwargs):
            assert loaded is model and selected_tokenizer is tokenizer
            assert kwargs["vocab_size"] == 3 and kwargs["max_context_tokens"] == 2

        def trace_teacher_forced(self, prompt, continuation):
            assert prompt == [1] and continuation == [2]
            return [Row()]

    monkeypatch.setattr(native_trial, "import_native", lambda *_: (load, Runner))
    monkeypatch.setattr(native_trial, "capture_sources", lambda *_a, **_kw: {
        "engine": {"imports": {"nanovllm.qwen38.model": {}}}, "control": {},
    })
    args = argparse.Namespace(model_path=model_path, manifest=tmp_path / "manifest",
                              workload=tmp_path / "workload", model_revision="a" * 40,
                              engine_repo=tmp_path / "engine", device_model="Synthetic GPU",
                              output=tmp_path / "run/candidate/trial-001/result.json")
    return args, cuda, calls


def test_native_serialization_uses_native_loader_and_trace_only(native_runtime):
    args, _cuda, calls = native_runtime
    result = native_trial.run(args)
    assert calls == [(args.model_path, "cuda:0")]
    assert result["implementation"] == "nanovllm_qwen38"
    assert result["qualification_scope"] == "native_text_smoke"
    assert result["kernel_policy"] == native_trial.NATIVE_POLICY
    assert result["cases"][0]["greedy_ids"] == [2]
    assert result == json.loads(args.output.read_text())
    with pytest.raises(ValueError, match="overwrite"):
        native_trial.run(args)


@pytest.mark.parametrize("count", [0, 2])
def test_native_gpu_guard_prevents_loading(native_runtime, count):
    args, cuda, calls = native_runtime
    cuda.device_count = lambda: count
    with pytest.raises(ValueError, match="exactly one"):
        native_trial.run(args)
    assert not calls and not args.output.exists()


def test_native_gpu_model_guard_prevents_loading(native_runtime):
    args, _cuda, calls = native_runtime
    args.device_model = "Different GPU"
    with pytest.raises(ValueError, match="target"):
        native_trial.run(args)
    assert not calls
