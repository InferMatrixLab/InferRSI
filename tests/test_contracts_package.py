"""The shared data/byte contracts package (#451 C1).

``inferrsi.contracts`` replaces root ``contracts.py``, ``_json_v1.py``, ``runspec.py``
and ``claim.py``. The moved objects keep their behavior and identity. The old module
paths are retired without aliases, including for pickles that name them.
"""

from __future__ import annotations

import dataclasses
import importlib
import importlib.util
import json
import os
import pickle
import subprocess
import sys
from pathlib import Path

import pytest

import inferrsi.contracts as contracts
import inferrsi.harness as harness
from inferrsi.apps.cli import arguments
from inferrsi.apps.legacy import evaluation as legacy_evaluation
from inferrsi.apps.legacy import run as legacy_run
from inferrsi.contracts import RunSpec, claim, json_v1, runspec
from inferrsi.harness import runner

SRC = Path(__file__).resolve().parents[1] / "src"
ROOT = SRC / "inferrsi"
RETIRED = {
    "inferrsi._json_v1": ("_json_v1.py", "CanonicalError"),
    "inferrsi.runspec": ("runspec.py", "RunSpec"),
    "inferrsi.claim": ("claim.py", "Verdict"),
}
MODULES = (
    "inferrsi.contracts",
    "inferrsi.contracts.runspec",
    "inferrsi.contracts.json_v1",
    "inferrsi.contracts.claim",
    # #451 C2: evidence segment and path rules; no filesystem access.
    "inferrsi.contracts.evidence",
)
COLD_IMPORT = """
import importlib, json, sys
module = importlib.import_module(sys.argv[1])
print(json.dumps({
    "loaded": sorted(name for name in sys.modules if name.split(".")[0] == "inferrsi"),
    "public": sorted(name for name in vars(module) if not name.startswith("_")),
}))
"""
# Run each module body again, in a throwaway namespace, after its dependencies are
# loaded. Any filesystem, process or network audit event then comes from the body itself.
IO_PROBE = """
import importlib, json, os, sys
IO_EVENTS = ("os.", "shutil.", "subprocess.", "socket.", "sqlite3.", "tempfile.", "glob.",
             "pathlib.", "urllib.", "http.", "ctypes.", "winreg.", "mmap.", "fcntl.", "msvcrt.")
bodies = []
for name in json.loads(sys.argv[1]):
    module = importlib.import_module(name)
    with open(module.__spec__.origin, encoding="utf-8") as handle:
        code = compile(handle.read(), module.__spec__.origin, "exec")
    bodies.append((name, module.__package__, code))
bodies.append(("control", "", compile(sys.argv[2], "control", "exec")))
seen = {name: [] for name, _, _ in bodies}
active = []
def hook(event, args):
    if active and (event == "open" or event.startswith(IO_EVENTS)):
        seen[active[0]].append(event)
sys.addaudithook(hook)
defined = {}
for name, package, code in bodies:
    namespace = {"__name__": name, "__package__": package, "__file__": code.co_filename}
    active[:] = [name]
    exec(code, namespace)
    active.clear()
    defined[name] = sorted(key for key in namespace if not key.startswith("_"))
print(json.dumps({"seen": seen, "defined": defined}))
"""
IO_CONTROL = "import os\nos.listdir(os.getcwd())\nopen(os.devnull).close()\n"
RUNSPEC_DEFAULTS = {
    "repo": "example/repo",
    "baseline_command": (),
    "candidate_command": (),
    "candidate_repo": None,
    "repo_type": "vllm",
    "backend": "cpu",
    "scenario": "external_benchmark",
    "mode": "config",
    "validation_command": None,
    "metric_key": "metrics.latency_ms",
    "metric_unit": "ms",
    "comparison_scope": "external_command",
    "direction": "minimize",
    "repetitions": 3,
    "min_improvement_pct": 0.0,
    "max_minutes": 120.0,
    "workload_id": None,
    "model": None,
    "model_revision": None,
    "agent": "manual",
    "device_ids": (),
    "revision": "",
    "device": "",
    "executor": "default",
    "snapshot_id": "",
    "output_dir": "runs",
    "required_trial_checks": (),
}


def _fresh(script: str, *args: str) -> dict:
    environment = {**os.environ, "PYTHONPATH": str(SRC)}
    result = subprocess.run(
        [sys.executable, "-c", script, *args], capture_output=True, text=True,
        encoding="utf-8", env=environment, timeout=120, check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_initializer_reexports_only_runspec_and_there_is_one_class() -> None:
    assert contracts.__all__ == ["RunSpec"]
    assert contracts.RunSpec is runspec.RunSpec is RunSpec
    assert (RunSpec.__module__, RunSpec.__qualname__) == ("inferrsi.contracts.runspec", "RunSpec")
    # Every consumer in the tree holds that same class object.
    for consumer in (arguments, legacy_evaluation, legacy_run, runner):
        assert consumer.RunSpec is RunSpec, consumer.__name__


def test_harness_reexports_the_same_verdict_objects() -> None:
    assert harness.__all__ == ["Verdict", "parse_verdict"]
    assert harness.Verdict is claim.Verdict
    assert harness.parse_verdict is claim.parse_verdict
    assert claim.Verdict.__module__ == "inferrsi.contracts.claim"
    assert [(verdict.name, verdict.value) for verdict in claim.Verdict] == [
        ("PASS", "PASS"), ("FAIL", "FAIL"), ("INCONCLUSIVE", "INCONCLUSIVE"),
    ]
    assert claim.parse_verdict("pass") is claim.Verdict.PASS
    assert isinstance(claim.Verdict.PASS, str) and claim.Verdict.PASS == "PASS"
    assert claim.claim_requires_pinned_shas(claim.Verdict.PASS) is True
    assert claim.claim_requires_pinned_shas(claim.Verdict.FAIL) is False
    with pytest.raises(ValueError) as caught:
        claim.parse_verdict("maybe")
    assert str(caught.value) == "Invalid verdict 'maybe'; expected one of PASS, FAIL, INCONCLUSIVE"


@pytest.mark.parametrize("module", MODULES)
def test_cold_import_loads_only_the_initializer_and_runspec(module: str) -> None:
    # No core, Apps, Infra or Model module loads: the initializer's RunSpec import is all.
    result = _fresh(COLD_IMPORT, module)
    expected = {"inferrsi", "inferrsi.contracts", "inferrsi.contracts.runspec", module}
    assert set(result["loaded"]) - {"inferrsi._version"} == expected
    if module == "inferrsi.contracts":
        assert result["public"] == ["RunSpec", "runspec"]


def test_module_bodies_do_no_io_on_import() -> None:
    result = _fresh(IO_PROBE, json.dumps(MODULES), IO_CONTROL)
    seen, defined = result["seen"], result["defined"]
    # Positive control: the same probe reports a body that touches the filesystem.
    assert {"os.listdir", "open"} <= set(seen.pop("control"))
    assert seen == {name: [] for name in MODULES}
    # Each body really ran under the probe.
    assert "RunSpec" in defined["inferrsi.contracts"]
    assert "RunSpec" in defined["inferrsi.contracts.runspec"]
    assert {"CanonicalError", "decode", "encode"} <= set(defined["inferrsi.contracts.json_v1"])
    assert {"Verdict", "parse_verdict"} <= set(defined["inferrsi.contracts.claim"])
    assert {"EVIDENCE_SEGMENTS", "campaign_evidence_root", "evidence_subpaths"} <= set(
        defined["inferrsi.contracts.evidence"]
    )
    # The initializer still re-exports RunSpec alone; evidence is reached by its module.
    assert not hasattr(contracts, "EVIDENCE_SEGMENTS")
    assert not hasattr(contracts, "evidence_subpaths")


@pytest.mark.parametrize("name", sorted(RETIRED))
def test_retired_root_module_paths_have_no_alias(name: str) -> None:
    filename, attribute = RETIRED[name]
    assert not (ROOT / filename).exists()
    assert importlib.util.find_spec(name) is None
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(name)
    assert name not in sys.modules
    # A pickle that names a class by its retired module path no longer loads.
    with pytest.raises(ModuleNotFoundError):
        pickle.loads(f"c{name}\n{attribute}\n.".encode("ascii"))


def test_contracts_is_a_package_and_pickles_name_the_new_paths() -> None:
    assert not (ROOT / "contracts.py").exists()
    assert Path(contracts.__file__).name == "__init__.py"
    spec = RunSpec(repo="example/repo", baseline_command=("run",), device_ids=("0", "1"))
    assert b"inferrsi.contracts.runspec" in pickle.dumps(spec, protocol=0)
    assert pickle.loads(pickle.dumps(spec)) == spec
    assert b"inferrsi.contracts.claim" in pickle.dumps(claim.Verdict.PASS, protocol=0)
    assert pickle.loads(pickle.dumps(claim.Verdict.PASS)) is claim.Verdict.PASS


def test_canonical_json_bytes_are_unchanged() -> None:
    value = {"b": [1, -2, True, False, None], "a": "é\n \x7f\"\\", "": {"z": 0, "A": []}}
    data = json_v1.encode(value)
    assert data == (
        b'{"":{"A":[],"z":0},"a":"\xc3\xa9\\n\xe2\x80\xa8\x7f\\"\\\\",'
        b'"b":[1,-2,true,false,null]}'
    )
    assert json_v1.decode(data) == value
    assert json_v1.encode("\x00\x1f\b\t\f\r") == b'"\\u0000\\u001f\\b\\t\\f\\r"'
    assert json_v1.MAX_SAFE_INTEGER == 9007199254740991
    for edge in (json_v1.MAX_SAFE_INTEGER, -json_v1.MAX_SAFE_INTEGER):
        assert json_v1.decode(json_v1.encode(edge)) == edge
    assert json_v1.CanonicalError.__module__ == "inferrsi.contracts.json_v1"
    assert issubclass(json_v1.CanonicalError, ValueError)


@pytest.mark.parametrize(
    "value,stage",
    [
        (2**53, "integer_range"),
        (-(2**53), "integer_range"),
        (1.5, "float_token"),
        (float("nan"), "nonfinite_token"),
        (float("inf"), "nonfinite_token"),
        ({1: "x"}, "ascii_key"),
        ({"é": 1}, "ascii_key"),
        ("\ud800", "unicode_scalar"),
        ((1, 2), "unsupported_type"),
        (b"bytes", "unsupported_type"),
    ],
    ids=repr,
)
def test_encode_error_stages_are_unchanged(value: object, stage: str) -> None:
    with pytest.raises(json_v1.CanonicalError) as caught:
        json_v1.encode(value)
    assert caught.value.stage == stage
    assert str(caught.value).startswith(stage + ": ")


@pytest.mark.parametrize(
    "data,stage",
    [
        (b"\xef\xbb\xbf{}", "no_bom"),
        (b"\xff", "strict_utf8"),
        (b"{", "json_syntax"),
        (b"1.0", "float_token"),
        (b"NaN", "nonfinite_token"),
        (b"9007199254740992", "integer_range"),
        (b"1" + b"0" * 4400, "integer_range"),
        (b'{"a":1,"a":2}', "duplicate_key"),
        (b'"\\ud800"', "unicode_scalar"),
        (b'{"\\u00e9":1}', "ascii_key"),
        (b'{"b":1,"a":2}', "canonical_bytes"),
        (b" 1", "canonical_bytes"),
    ],
    ids=lambda item: item[:24].decode("latin-1") if isinstance(item, bytes) else item,
)
def test_decode_error_stages_are_unchanged(data: bytes, stage: str) -> None:
    with pytest.raises(json_v1.CanonicalError) as caught:
        json_v1.decode(data)
    assert caught.value.stage == stage
    assert str(caught.value).startswith(stage + ": ")


def _valid(tmp_path: Path, **changes: object) -> RunSpec:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    values: dict = {
        "repo": str(repo), "baseline_command": ("base",), "candidate_command": ("candidate",),
        "output_dir": str(tmp_path / "runs"),
    }
    return RunSpec(**{**values, **changes})


def test_runspec_defaults_and_round_trip_are_unchanged(tmp_path: Path) -> None:
    assert [field.name for field in dataclasses.fields(RunSpec)] == list(RUNSPEC_DEFAULTS)
    assert RunSpec(repo="example/repo").to_dict() == RUNSPEC_DEFAULTS
    spec = _valid(
        tmp_path, validation_command=("check", "--strict"), device_ids=("0", "1"),
        required_trial_checks=("evidence.closed",), min_improvement_pct=2.5,
    )
    assert spec.validate() is None
    # JSON turns the tuples into lists; from_dict restores the same frozen value.
    restored = RunSpec.from_dict(json.loads(json.dumps(spec.to_dict())))
    assert restored == spec and hash(restored) == hash(spec)
    assert isinstance(restored.baseline_command, tuple) and restored.candidate_repo is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.repo = "elsewhere"
    with pytest.raises(ValueError, match="device_ids must be an argv/ID sequence"):
        RunSpec.from_dict({"repo": "r", "device_ids": "0"})
    with pytest.raises(TypeError):
        RunSpec.from_dict({"repo": "r", "unknown_field": 1})


@pytest.mark.parametrize(
    "changes,message",
    [
        ({"repo": "missing-directory"}, "repo must be an existing directory"),
        ({"baseline_command": ()}, "baseline_command must be a nonempty argv sequence"),
        ({"candidate_command": ("",)}, "candidate_command executable cannot be empty"),
        ({"validation_command": ("ok", 1)}, "validation_command must be a nonempty argv"),
        ({"required_trial_checks": ("a", "a")}, "required_trial_checks must be a tuple"),
        ({"required_trial_checks": ("a..b",)}, "required_trial_checks must be a tuple"),
        ({"direction": "up"}, "direction must be minimize or maximize"),
        ({"mode": "other"}, "mode must be config, code or semantic"),
        ({"repetitions": 0}, "repetitions must be a positive integer"),
        ({"repetitions": True}, "repetitions must be a positive integer"),
        ({"max_minutes": float("nan")}, "max_minutes must be finite"),
        ({"min_improvement_pct": -1.0}, "max_minutes must be positive and min_improvement_pct"),
        ({"max_minutes": 7 * 24 * 60 + 1}, "max_minutes cannot exceed seven days"),
        ({"metric_key": "a..b"}, "metric_key must be a nonempty dotted JSON key"),
        ({"metric_unit": ""}, "metric_unit and comparison_scope must be declared"),
    ],
    ids=lambda item: next(iter(item)) if isinstance(item, dict) else None,
)
def test_runspec_validation_errors_are_unchanged(
    tmp_path: Path, changes: dict, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _valid(tmp_path, **changes).validate()


def test_runspec_output_dir_may_not_contain_a_source_repository(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="output_dir cannot equal or contain a source"):
        _valid(tmp_path, output_dir=str(tmp_path)).validate()
