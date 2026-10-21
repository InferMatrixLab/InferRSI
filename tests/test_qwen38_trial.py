"""CPU contract tests; these do not claim model or GPU qualification."""

import hashlib
import json
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from examples.qwen38_text import trial

REVISION = "a" * 40


def write_json(path, value):
    path.write_text(json.dumps(value))


@pytest.fixture
def model_bundle(tmp_path):
    model = tmp_path / "model"
    model.mkdir()
    config = {
        "model_type": "qwen3_5",
        "architectures": ["Qwen3_5ForConditionalGeneration"],
        "text_config": {"model_type": "qwen3_5_text", "dtype": "bfloat16", "vocab_size": 2},
    }
    write_json(model / "config.json", config)
    for name in ("tokenizer_config.json", "tokenizer.json"):
        write_json(model / name, {})
    write_json(
        model / "model.safetensors.index.json", {"weight_map": {"weight": "part.safetensors"}}
    )
    (model / "part.safetensors").write_bytes(b"synthetic weight bytes")
    manifest = tmp_path / "manifest.json"
    records = [
        {"path": item.name, "sha256": trial.sha256_file(item), "size": item.stat().st_size}
        for item in sorted(model.iterdir())
    ]
    write_json(manifest, {"model_id": trial.MODEL_ID, "revision": REVISION, "files": records})
    return model, manifest


def test_integrity_reads_bytes_even_when_size_unchanged(model_bundle):
    model, manifest = model_bundle
    assert trial.verify_manifest(model, manifest, REVISION) == trial.sha256_file(manifest)
    weight = model / "part.safetensors"
    original = weight.read_bytes()
    weight.write_bytes(b"X" + original[1:])
    with pytest.raises(ValueError, match="integrity mismatch"):
        trial.verify_manifest(model, manifest, REVISION)


def test_manifest_must_cover_index_and_tokenizer(model_bundle):
    model, manifest = model_bundle
    value = json.loads(manifest.read_text())
    value["files"] = [row for row in value["files"] if row["path"] != "part.safetensors"]
    write_json(manifest, value)
    with pytest.raises(ValueError, match="indexed"):
        trial.verify_manifest(model, manifest, REVISION)
    value["files"] = [row for row in value["files"] if row["path"] != "tokenizer.json"]
    write_json(manifest, value)
    with pytest.raises(ValueError, match="required"):
        trial.verify_manifest(model, manifest, REVISION)


def test_extra_tokenizer_metadata_requires_hash(model_bundle):
    model, manifest = model_bundle
    write_json(model / "added_tokens.json", {})
    with pytest.raises(ValueError, match="metadata"):
        trial.verify_manifest(model, manifest, REVISION)


def test_symlink_and_traversal_cannot_escape_model(tmp_path):
    root = tmp_path / "model"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("synthetic")
    (root / "link").symlink_to(outside)
    for name in ("../outside", "/outside", "link", "a/../link"):
        with pytest.raises(ValueError):
            trial.model_file(root, name)


def test_wrong_identity_and_quantization_rejected(model_bundle):
    model, manifest = model_bundle
    with pytest.raises(ValueError, match="identity"):
        trial.verify_manifest(model, manifest, "b" * 40)
    config_path = model / "config.json"
    config = json.loads(config_path.read_text())
    config["quantization_config"] = {"quant_method": "fp8"}
    write_json(config_path, config)
    value = json.loads(manifest.read_text())
    for row in value["files"]:
        if row["path"] == "config.json":
            row.update(size=config_path.stat().st_size, sha256=trial.sha256_file(config_path))
    write_json(manifest, value)
    with pytest.raises(ValueError, match="unquantized"):
        trial.verify_manifest(model, manifest, REVISION)


def test_workload_validation_and_raw_bytes_hash(tmp_path):
    path = tmp_path / "workload.json"
    case = {"id": "plain", "prompt": "P", "continuation": "ABC", "max_steps": 2}
    value = {"schema_version": 1, "model_id": trial.MODEL_ID, "cases": [case]}
    write_json(path, value)
    cases, digest = trial.load_workload(path)
    assert cases == [case]
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    value["cases"].append(case)
    write_json(path, value)
    with pytest.raises(ValueError, match="duplicate"):
        trial.load_workload(path)
    value["cases"] = [{**case, "max_steps": True}]
    write_json(path, value)
    with pytest.raises(ValueError):
        trial.load_workload(path)


def test_tokenization_never_adds_special_tokens_and_requires_enough():
    def encode(text, *, add_special_tokens):
        assert add_special_tokens is False
        return list(text.encode())

    tokenizer = SimpleNamespace(encode=encode)
    case = {"prompt": "P", "continuation": "ABC", "max_steps": 2}
    assert trial.tokenize_case(tokenizer, case) == ([80], [65, 66])
    with pytest.raises(ValueError, match="insufficient"):
        trial.tokenize_case(tokenizer, {**case, "max_steps": 4})


class FakeRow:
    def detach(self):
        return self

    def float(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return pytest.importorskip("numpy").array([1.0, 3.0], dtype="float32")


class FakeLogits:
    def __getitem__(self, key):
        assert key == (0, -1)
        return FakeRow()


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("full", [[10, 11], [10, 11, 20], [10, 11, 20, 21]]),
        ("cached", [[10, 11], [20], [21]]),
    ],
)
def test_teacher_forcing_prefix_and_cache_transition(mode, expected):
    calls = []
    caches = []

    def model(**kwargs):
        calls.append(kwargs["input_ids"][0])
        assert kwargs["use_cache"] == (mode == "cached")
        assert kwargs["past_key_values"] == (caches[-1] if caches and mode == "cached" else None)
        cache = object()
        caches.append(cache)
        return SimpleNamespace(logits=FakeLogits(), past_key_values=cache)

    def tensor(value, *, dtype, device):
        assert dtype == "long" and device == "cuda:0"
        return value

    torch = SimpleNamespace(tensor=tensor, long="long", inference_mode=nullcontext)
    rows = trial.collect_logits(model, torch, [10, 11], [20, 21, 22], mode)
    assert calls == expected
    assert len(rows) == 3
    assert all(row.dtype == "float32" for row in rows)
    # A second request starts from empty recurrent/KV state even in cached mode.
    caches.clear()
    trial.collect_logits(model, torch, [30], [40], mode)
    assert calls[-1] == [30]


def test_failure_message_does_not_disclose_runtime_paths(monkeypatch, capsys):
    def fail(_args):
        raise OSError("/private/example-user/model: permission denied")

    monkeypatch.setattr(trial, "run", fail)
    result = trial.main(
        [
            "--model-path",
            "/private/example-user/model",
            "--model-revision",
            REVISION,
            "--device-model",
            "TEST GPU",
            "--manifest",
            "manifest",
            "--workload",
            "workload",
            "--mode",
            "full",
            "--output",
            "result",
        ]
    )
    assert result == 1
    output = capsys.readouterr()
    assert "OSError" in output.err and "example-user" not in output.err


@pytest.fixture
def fake_runtime(monkeypatch):
    """Dependency doubles exercise serialization and guards, not GPU inference."""
    import sys

    np = pytest.importorskip("numpy")
    calls = []

    def forward(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(logits=FakeLogits(), past_key_values=object())

    model = type(
        "FakeModel",
        (),
        {"eval": lambda self: self, "__call__": lambda self, **kwargs: forward(**kwargs)},
    )()

    def load_model(_path, **kwargs):
        assert kwargs["dtype"] == "bfloat16"
        assert kwargs["device_map"] == {"": "cuda:0"}
        assert kwargs["local_files_only"] and not kwargs["trust_remote_code"]
        assert kwargs["use_kernels"] is False
        return model, {"missing_keys": [], "mismatched_keys": [], "error_msgs": []}

    tokenizer = SimpleNamespace(encode=lambda text, **_kwargs: list(text.encode()))
    cuda = SimpleNamespace(
        is_available=lambda: True,
        device_count=lambda: 1,
        is_bf16_supported=lambda: True,
        get_device_name=lambda _index: "TEST GPU",
    )
    torch = SimpleNamespace(
        cuda=cuda,
        long="long",
        bfloat16="bfloat16",
        __version__="test",
        version=SimpleNamespace(cuda="test"),
        inference_mode=nullcontext,
        tensor=lambda value, **_kwargs: value,
    )
    transformers = SimpleNamespace(
        __version__="test",
        AutoTokenizer=SimpleNamespace(from_pretrained=lambda *_a, **_k: tokenizer),
        Qwen3_5ForConditionalGeneration=SimpleNamespace(from_pretrained=load_model),
    )
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    return cuda, calls, np


def trial_args(model_bundle, tmp_path):
    model, manifest = model_bundle
    workload = tmp_path / "workload.json"
    write_json(
        workload,
        {
            "schema_version": 1,
            "model_id": trial.MODEL_ID,
            "cases": [
                {"id": "simple", "prompt": "P", "continuation": "ABC", "max_steps": 2},
            ],
        },
    )
    return SimpleNamespace(
        model_path=model,
        manifest=manifest,
        model_revision=REVISION,
        device_model="TEST GPU",
        workload=workload,
        mode="cached",
        output=tmp_path / "result.json",
    )


def test_result_artifacts_are_linked_and_labeled_self_check(model_bundle, tmp_path, fake_runtime):
    _cuda, calls, np = fake_runtime
    args = trial_args(model_bundle, tmp_path)
    result = trial.run(args)
    assert result["qualification_scope"] == "reference_self_check"
    assert result["implementation"] == "transformers_cached"
    assert result["tokenization"] == "raw_text_no_special_tokens"
    assert result["vocab_size"] == 2 and result["device_model"] == "TEST GPU"
    assert result["workload_sha256"] == trial.sha256_file(args.workload)
    assert result == json.loads(args.output.read_text())
    assert str(tmp_path) not in args.output.read_text()
    case = result["cases"][0]
    assert case["continuation_ids"] == [65, 66]
    assert case["greedy_ids"] == [1, 1]
    logits_path = args.output.parent / case["logits_file"]
    assert trial.sha256_file(logits_path) == case["logits_sha256"]
    with np.load(logits_path, allow_pickle=False) as archive:
        assert archive["logits"].shape == (2, 2)
        assert archive["logits"].dtype == np.float32
    assert len(calls) == 2
    with pytest.raises(ValueError, match="overwrite"):
        trial.run(args)


@pytest.mark.parametrize("count", [0, 2])
def test_gpu_count_guard_before_model_execution(model_bundle, tmp_path, fake_runtime, count):
    cuda, calls, _np = fake_runtime
    cuda.device_count = lambda: count
    args = trial_args(model_bundle, tmp_path)
    with pytest.raises(ValueError, match="exactly one"):
        trial.run(args)
    assert not args.output.exists() and not calls


def test_gpu_model_mismatch_rejected(model_bundle, tmp_path, fake_runtime):
    _cuda, calls, _np = fake_runtime
    args = trial_args(model_bundle, tmp_path)
    args.device_model = "OTHER GPU"
    with pytest.raises(ValueError, match="frozen device model"):
        trial.run(args)
    assert not args.output.exists() and not calls


def test_optional_kernel_cannot_silently_change_reference(monkeypatch):
    monkeypatch.setattr(trial.importlib.util, "find_spec", lambda name: object())
    with pytest.raises(ValueError, match="optional DeltaNet kernels"):
        trial.kernel_policy()


def test_fp8_manifest_and_workload_are_separate(model_bundle, tmp_path):
    from examples.qwen38_text.profiles import FP8_MODEL_ID, FP8_QUANTIZATION, precision

    model, manifest = model_bundle
    config = json.loads((model / "config.json").read_text())
    config["quantization_config"] = FP8_QUANTIZATION
    write_json(model / "config.json", config)
    document = json.loads(manifest.read_text())
    document.update(model_id=FP8_MODEL_ID, precision=precision(FP8_MODEL_ID))
    for record in document["files"]:
        path = model / record["path"]
        record.update(size=path.stat().st_size, sha256=trial.sha256_file(path))
    write_json(manifest, document)
    assert trial.verify_manifest(model, manifest, REVISION, FP8_MODEL_ID)
    with pytest.raises(ValueError, match="identity"):
        trial.verify_manifest(model, manifest, REVISION)
    workload = tmp_path / "workload.json"
    write_json(workload, {"schema_version": 1, "model_id": FP8_MODEL_ID,
                          "precision": precision(FP8_MODEL_ID),
                          "cases": [{"id": "one", "prompt": "abc", "continuation": "def",
                                     "max_steps": 1}]})
    assert len(trial.load_workload(workload, FP8_MODEL_ID)[0]) == 1
    with pytest.raises(ValueError):
        trial.load_workload(workload)
    document.pop("precision")
    write_json(manifest, document)
    with pytest.raises(ValueError, match="precision"):
        trial.verify_manifest(model, manifest, REVISION, FP8_MODEL_ID)
