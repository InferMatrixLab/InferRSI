"""Every core's copy of the shared file helpers stays the same code with the same bytes.

#412 R2 gave Harness its own copies and #498 slice 1 gave Benchmark its own, so no core
imports another for them. This test fails when one copy drifts from the others.
"""

import importlib
import inspect
import json

import pytest

# Each helper name and the modules that hold a copy. #498 slice 3b added the Apps copy
# and slice 5 deleted the Infra one, so Harness, Benchmark and Apps hold the three.
COPIES = {
    "sha256": ("inferrsi.apps.artifacts", "inferrsi.harness.artifact_primitives",
               "inferrsi.benchmark.artifacts"),
    "write_json": ("inferrsi.apps.artifacts", "inferrsi.benchmark.artifacts"),
    "atomic_write_json": ("inferrsi.apps.artifacts", "inferrsi.harness.atomic_json",
                          "inferrsi.benchmark.artifacts"),
    "digest": ("inferrsi.apps.artifacts", "inferrsi.harness.artifact_primitives"),
    "file_lock": ("inferrsi.apps.artifacts", "inferrsi.harness.artifact_primitives"),
}
CONSTANTS = ("REPLACE_ATTEMPTS", "REPLACE_DELAY_SECONDS")
VALUE = {"b": [1.5, None, True, 1e-07, 1e16], "a": "非 ASCII", "nested": {"z": 0.1 + 0.2}}


@pytest.mark.parametrize("name", sorted(COPIES))
def test_every_copy_has_the_same_source(name):
    sources = {module: inspect.getsource(getattr(importlib.import_module(module), name))
               for module in COPIES[name]}
    assert len(set(sources.values())) == 1, sorted(sources)


def test_the_atomic_writers_share_their_retry_constants():
    for constant in CONSTANTS:
        values = {getattr(importlib.import_module(module), constant)
                  for module in COPIES["atomic_write_json"]}
        assert len(values) == 1, constant


def test_the_benchmark_copy_imports_no_other_inferrsi_module():
    import ast

    from inferrsi.benchmark import artifacts

    tree = ast.parse(inspect.getsource(artifacts))
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                and (node.level or (node.module or "").split(".")[0] == "inferrsi")]
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Import)
                and any(alias.name.split(".")[0] == "inferrsi" for alias in node.names)]


@pytest.mark.parametrize("name", ["write_json", "atomic_write_json"])
def test_every_writer_writes_the_same_bytes(tmp_path, name):
    written = set()
    for index, module in enumerate(COPIES[name]):
        path = tmp_path / f"{index}.json"
        getattr(importlib.import_module(module), name)(path, VALUE)
        written.add(path.read_bytes())
    assert len(written) == 1
    assert json.loads(written.pop()) == VALUE
    for module in COPIES[name]:
        with pytest.raises(ValueError):
            getattr(importlib.import_module(module), name)(tmp_path / "nan.json",
                                                           {"value": float("nan")})


def test_every_digest_copy_reads_the_same_bytes(tmp_path):
    blob = tmp_path / "blob.bin"
    blob.write_bytes(bytes(range(256)) * 9000)  # crosses the 1 MiB read block
    digests = {getattr(importlib.import_module(module), "sha256")(blob)
               for module in COPIES["sha256"]}
    assert len(digests) == 1
    for module in COPIES["sha256"]:
        with pytest.raises(FileNotFoundError):
            importlib.import_module(module).sha256(tmp_path / "missing.bin")
