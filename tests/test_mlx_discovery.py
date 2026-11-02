import json
import platform
import sys
from pathlib import Path

import pytest

from inferrsi import catalog
from inferrsi.catalog import get_knowledge, search_knowledge
from inferrsi.cli import main
from inferrsi.infra.commands import probe_command
from inferrsi.infra.platforms import inspect_device
from inferrsi.infra.platforms import mlx as mlx_platform
from inferrsi.infra.platforms.mlx import _parse_sysctl_info
from inferrsi.knowledge_operations import KnowledgeReader

PROJECT = Path(__file__).resolve().parents[1]
IDS = {
    "mlx.mlx.execution.evaluation_completion",
    "mlx.mlx.execution.cross_stream_dependency",
    "mlx.mlx.execution.post_detachment_buffer_lifetime",
}


@pytest.mark.parametrize(
    "text,expected",
    [
        ("hw.optional.arm64: 1\nmachdep.cpu.brand_string: Apple M3 Pro\n", (True, "Apple M3 Pro")),
        ("hw.optional.arm64: 0\nmachdep.cpu.brand_string: Intel Core\n", (False, "Intel Core")),
        (" machdep.cpu.brand_string: Apple M1 \n hw.optional.arm64: 1 \n", (True, "Apple M1")),
    ],
)
def test_sysctl_parser_static_text_only(text, expected):
    # Test explicit static text only; do not simulate sysctl or a hardware PASS.
    assert _parse_sysctl_info(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "hw.optional.arm64: 1\n",
        "hw.optional.arm64: 2\nmachdep.cpu.brand_string: Apple M3\n",
        "hw.optional.arm64: 1\nmachdep.cpu.brand_string: \n",
        "hw.optional.arm64: 1\nhw.optional.arm64: 0\n",
    ],
)
def test_sysctl_parser_rejects_incomplete_static_text(text):
    with pytest.raises(ValueError):
        _parse_sysctl_info(text)


@pytest.mark.skipif(platform.system() == "Darwin", reason="Requires a real non-macOS host")
def test_actual_non_macos_doctor_reports_unavailable(capsys):
    result = main([
        "doctor", "--repo", str(PROJECT), "--repo-type", "vllm_omni",
        "--backend", "mlx", "--python", sys.executable,
    ])
    environment = json.loads(capsys.readouterr().out)
    assert result == 1
    assert environment["repository"]["available"]
    assert environment["target_python"]["returncode"] == 0
    assert "mlx" in environment["target_python"]["environment"]["packages"]
    assert environment["device"]["status"] == "unavailable"
    assert "macOS" in environment["device"]["reason"]
    assert "probe" not in environment["device"]
    assert environment["compatibility"] == "unverified"


def _mocked_darwin(monkeypatch, *, returncode=0, stdout=""):
    # Mocked software branches only; these cases claim no Apple hardware validation.
    monkeypatch.setattr(mlx_platform.platform, "system", lambda: "Darwin")
    return lambda argv: {"argv": argv, "returncode": returncode, "stdout": stdout, "stderr": ""}


M1_PRO = "hw.optional.arm64: 1\nmachdep.cpu.brand_string: Apple M1 Pro\n"


@pytest.mark.parametrize("device_model", [None, "Apple M1 Pro", "m1 pro", " M1  PRO "])
def test_mocked_darwin_apple_silicon_is_available(monkeypatch, device_model):
    result = mlx_platform.inspect_devices(
        device_ids=(), device_model=device_model, command=_mocked_darwin(monkeypatch, stdout=M1_PRO)
    )
    assert result["status"] == "available"
    assert result["selection_verified"] is True
    assert result["chip"] == "Apple M1 Pro"


@pytest.mark.parametrize("device_model", ["M1", "pro", "Apple M", "M1 Max", "M4"])
def test_mocked_darwin_partial_or_other_model_is_a_mismatch(monkeypatch, device_model):
    result = mlx_platform.inspect_devices(
        device_ids=(), device_model=device_model, command=_mocked_darwin(monkeypatch, stdout=M1_PRO)
    )
    assert result["status"] == "device_model_mismatch"
    assert result["selection_verified"] is False
    assert result["chip"] == "Apple M1 Pro"


def test_mocked_darwin_intel_chip_is_unavailable(monkeypatch):
    stdout = "hw.optional.arm64: 0\nmachdep.cpu.brand_string: Intel Core i7\n"
    result = mlx_platform.inspect_devices(
        device_ids=(), device_model=None, command=_mocked_darwin(monkeypatch, stdout=stdout)
    )
    assert result["status"] == "unavailable"
    assert result["reason"] == "Host is not Apple Silicon"
    assert result["selection_verified"] is False


def test_mocked_darwin_failed_sysctl_is_unavailable(monkeypatch):
    result = mlx_platform.inspect_devices(
        device_ids=(), device_model=None, command=_mocked_darwin(monkeypatch, returncode=1)
    )
    assert result["status"] == "unavailable"
    assert "sysctl" in result["reason"]
    assert "chip" not in result


@pytest.mark.skipif(
    platform.system() != "Darwin" or platform.machine() != "arm64",
    reason="Requires a real Apple Silicon host",
)
def test_actual_apple_silicon_doctor_reports_available(capsys):
    result = main([
        "doctor", "--repo", str(PROJECT), "--repo-type", "vllm_omni",
        "--backend", "mlx", "--python", sys.executable,
    ])
    environment = json.loads(capsys.readouterr().out)
    assert result == 0
    assert environment["device"]["status"] == "available"
    assert environment["device"]["selection_verified"] is True
    assert environment["device"]["chip"].startswith("Apple M")
    assert environment["compatibility"] == "unverified"


def test_discrete_ids_are_rejected_by_real_adapter():
    result = inspect_device(
        "mlx", device_ids=("0",), device_model=None, command=probe_command
    )
    assert result["status"] == "unavailable"
    assert "discrete device IDs" in result["reason"]
    assert result["selection_verified"] is False
    assert "probe" not in result


def test_mlx_cards_are_source_scoped_and_readable(capsys):
    records = search_knowledge(repo="mlx", tier="dependency", backend="mlx", limit=100)
    assert {item["id"] for item in records} == IDS
    assert "mlx" not in catalog.REPO_TYPES
    assert search_knowledge(repo="mlx", tier="peer", backend="mlx") == []
    assert search_knowledge(repo="mlx", backend="cuda") == []
    assert main([
        "knowledge", "search", "--tier", "dependency", "--repo-type", "mlx",
        "--backend", "mlx", "--json", "--limit", "100",
    ]) == 0
    assert {item["id"] for item in json.loads(capsys.readouterr().out)} == IDS
    reader = KnowledgeReader()
    document = "data/skill_library/frameworks/mlx/lazy-evaluation-stream-lifetimes/SKILL.md"
    expected = (PROJECT / "src/inferrsi" / document).read_bytes()
    for record in records:
        assert record["backend"] == "mlx"
        assert record["status"] == "imported"
        assert record["verification"]["locally_verified"] is False
        assert {s["commit"] for s in record["sources"]} == {
            "bff10220c742907f0c68e55ff174aaea56f74e3d"
        }
        bundle = reader.read("package:" + record["id"])
        assert json.loads(bundle.content["record.json"])["id"] == record["id"]
        assert reader.resource(
            "package:" + record["id"], document, revision=bundle.revision
        ) == expected
    for name in ("lazy_evaluation_stream_lifetimes", "generation_cache_lifecycle"):
        old = get_knowledge("inferrsi.common.skills." + name)
        assert old["backend"] == "common" and old["repo"] == "inferrsi"
        assert old["skill_metadata"]["status"] == "candidate"
        assert old["skill_metadata"]["empirical_validation"] == "not_run"
