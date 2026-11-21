"""MUSA platform discovery, registry wiring and the vllm-musa repository pack.

The probe contract is exercised through injected command callables, so these
tests never need MUSA hardware, pymtml or a MUSA toolkit; the numbers they use
are contract fixtures, not accelerator measurements.
"""

import json
import subprocess
from unittest.mock import patch

import pytest

from inferrsi.apps.host.inspection import inspect_environment
from inferrsi.apps.host.platforms import PLATFORM_PROBES, inspect_device
from inferrsi.apps.host.platforms.musa import PROBE_CODE, qualify_devices
from inferrsi.knowledge.catalog import BACKENDS
from inferrsi.resources.repository_packs import REPO_TYPES, repository_pack

DEVICES = {
    "devices": [
        {
            "index": "0",
            "uuid": "GPU-1111",
            "name": "MTT S5000",
            "driver_version": "6.1.0",
            "memory_total_mib": 49152,
        },
        {
            "index": "1",
            "uuid": "GPU-2222",
            "name": "MTT S5000",
            "driver_version": "6.1.0",
            "memory_total_mib": 49152,
        },
    ]
}


def probe(stdout="", returncode=0, stderr=""):
    return {"argv": ["python", "-c", PROBE_CODE], "returncode": returncode,
            "stdout": stdout, "stderr": stderr}


def test_musa_probe_selects_requested_devices():
    device = inspect_device(
        "musa",
        device_ids=("0",),
        device_model="S5000",
        command=lambda argv: probe(json.dumps(DEVICES)),
        python="/opt/musa/bin/python",
    )
    assert device["status"] == "available"
    assert device["selection_verified"] is True
    assert [row["uuid"] for row in device["devices"]] == ["GPU-1111", "GPU-2222"]


def test_musa_probe_reports_absent_device_id():
    device = inspect_device(
        "musa",
        device_ids=("7",),
        device_model=None,
        command=lambda argv: probe(json.dumps(DEVICES)),
    )
    assert device["status"] == "unavailable"
    assert device["selection_verified"] is False
    assert "Requested device IDs absent" in device["reason"]


def test_musa_probe_reports_model_mismatch():
    device = inspect_device(
        "musa",
        device_ids=(),
        device_model="S4000",
        command=lambda argv: probe(json.dumps(DEVICES)),
    )
    assert device["status"] == "device_model_mismatch"
    assert "S4000" in device["reason"]


def test_musa_probe_reports_missing_bindings():
    device = inspect_device(
        "musa", device_ids=(), device_model=None,
        command=lambda argv: probe('{"error": "pymtml unavailable"}', returncode=3),
    )
    assert device["status"] == "unavailable"
    assert device["probe"]["returncode"] == 3


def test_musa_probe_rejects_unparsable_output():
    device = inspect_device(
        "musa", device_ids=(), device_model=None, command=lambda argv: probe("no json here"),
    )
    assert device["status"] == "unavailable"
    assert device["devices"] == []
    assert "No device records parsed from pymtml output" in device["reason"]


def test_registry_exposes_musa_backend_and_target_python():
    assert PLATFORM_PROBES["musa"].__name__ == "inspect_devices"
    assert "musa" in BACKENDS
    seen = []

    def command(argv):
        seen.append(argv)
        return probe(json.dumps(DEVICES))

    inspect_device(
        "musa", device_ids=(), device_model=None, command=command, python="/opt/musa/bin/python"
    )
    assert seen[0][0] == "/opt/musa/bin/python"
    assert seen[0][1:] == ["-c", PROBE_CODE]


def test_cuda_probe_accepts_the_target_python_argument():
    csv = "0, GPU-fixture, NVIDIA H100 SXM, 550.54\n"
    device = inspect_device(
        "cuda", device_ids=("0",), device_model="H100",
        command=lambda argv: {"argv": argv, "returncode": 0, "stdout": csv, "stderr": ""},
        python="/usr/bin/python3",
    )
    assert device["status"] == "available"
    assert device["selection_verified"] is True


def test_inspection_records_musa_visibility_and_packages(monkeypatch):
    monkeypatch.setenv("MUSA_VISIBLE_DEVICES", "0,1")
    seen = []

    def command(argv):
        seen.append(argv)
        if "importlib.metadata" in argv[-1]:
            return {"argv": argv, "returncode": 0, "stderr": "", "stdout": json.dumps(
                {"python": "3.10", "packages": {"torch": "2.7.0", "vllm": "0.10.0"}}
            )}
        return probe(json.dumps(DEVICES))

    environment = inspect_environment(
        ".", "vllm_musa", "musa", python="/opt/musa/bin/python",
        command=command, snapshot=lambda path: {"path": str(path), "head": "0" * 40},
    )
    assert environment["visible_devices"]["MUSA_VISIBLE_DEVICES"] == "0,1"
    assert environment["device"]["status"] == "available"
    package_code = seen[0][-1]
    for name in ("torch_musa", "vllm-musa", "mthreads-ml-py", "torchada", "mate"):
        assert name in package_code


def test_vllm_musa_pack_is_registered_and_covers_both_model_lanes():
    assert "vllm_musa" in REPO_TYPES
    pack = repository_pack("vllm_musa")
    assert pack["source_repository"] == "MooreThreads/vllm-musa"
    assert pack["execution_support"] == "caller_supplied_external_commands"
    assert {"llm.decode", "llm.serving", "diffusion.image_generation"} <= set(pack["scenarios"])
    assert set(pack["backend_compatibility"].values()) == {"unverified"}


def test_musa_qualification_accepts_idle_reserved_devices(monkeypatch):
    monkeypatch.setenv("MUSA_VISIBLE_DEVICES", "0,1")
    idle = subprocess.CompletedProcess([], 0, json.dumps(DEVICES), "")
    empty = subprocess.CompletedProcess(
        [], 0, json.dumps({"processes": [], "usage": [{"device": "0", "used_mib": 0},
                                                     {"device": "1", "used_mib": 0}]}), ""
    )
    with patch("inferrsi.apps.host.platforms.musa.subprocess.run", side_effect=[idle, empty]):
        selected = qualify_devices(count=2, device_model="S5000")
    assert [row["index"] for row in selected] == ["0", "1"]
    # The trial maps this variable by position; record which physical card each
    # logical index actually is so the evidence cannot drift from the check.
    assert [row["logical_index"] for row in selected] == [0, 1]


def test_musa_qualification_rejects_wrong_count_and_busy_device(monkeypatch):
    monkeypatch.setenv("MUSA_VISIBLE_DEVICES", "0")
    with pytest.raises(ValueError, match="exactly 2 caller-reserved"):
        qualify_devices(count=2, device_model="S5000")
    idle = subprocess.CompletedProcess([], 0, json.dumps(DEVICES), "")
    busy = subprocess.CompletedProcess(
        [], 0, json.dumps({"processes": [{"device": "0", "pid": 4242}],
                           "usage": [{"device": "0", "used_mib": 4096}]}), ""
    )
    with patch("inferrsi.apps.host.platforms.musa.subprocess.run", side_effect=[idle, busy]):
        with pytest.raises(ValueError, match="already has a compute process"):
            qualify_devices(count=1, device_model="S5000")


def test_musa_qualification_fails_closed_when_the_process_query_cannot_answer(monkeypatch):
    monkeypatch.setenv("MUSA_VISIBLE_DEVICES", "0")
    idle = subprocess.CompletedProcess([], 0, json.dumps(DEVICES), "")
    unknown = subprocess.CompletedProcess(
        [], 3, json.dumps({"error": "pymtml unavailable: no module named pymtml"}), ""
    )
    with patch("inferrsi.apps.host.platforms.musa.subprocess.run", side_effect=[idle, unknown]):
        with pytest.raises(ValueError, match="Cannot verify that the selected MUSA devices"):
            qualify_devices(count=1, device_model="S5000")
    # A query that answers without a process list is equally unknown, not idle.
    silent = subprocess.CompletedProcess([], 0, "[]", "")
    with patch("inferrsi.apps.host.platforms.musa.subprocess.run", side_effect=[idle, silent]):
        with pytest.raises(ValueError, match="did not report a process list"):
            qualify_devices(count=1, device_model="S5000")


def test_musa_qualification_rejects_a_process_binding_that_cannot_account(monkeypatch):
    # A vendor binding can implement the query and still always answer "none".
    # The used-memory figure is the independent signal that catches it.
    monkeypatch.setenv("MUSA_VISIBLE_DEVICES", "0")
    idle = subprocess.CompletedProcess([], 0, json.dumps(DEVICES), "")
    blind = subprocess.CompletedProcess(
        [], 0, json.dumps({"processes": [], "usage": [{"device": "0", "used_mib": 4096}]}), ""
    )
    with patch("inferrsi.apps.host.platforms.musa.subprocess.run", side_effect=[idle, blind]):
        with pytest.raises(ValueError, match="process accounting cannot be trusted"):
            qualify_devices(count=1, device_model="S5000")
    # No memory figure at all is unknown, not idle.
    anonymous = subprocess.CompletedProcess(
        [], 0, json.dumps({"processes": [], "usage": [{"device": "0", "used_mib": None}]}), ""
    )
    with patch("inferrsi.apps.host.platforms.musa.subprocess.run", side_effect=[idle, anonymous]):
        with pytest.raises(ValueError, match="no used memory"):
            qualify_devices(count=1, device_model="S5000")
    # A reply without the usage list is equally unusable.
    truncated = subprocess.CompletedProcess([], 0, json.dumps({"processes": []}), "")
    with patch("inferrsi.apps.host.platforms.musa.subprocess.run", side_effect=[idle, truncated]):
        with pytest.raises(ValueError, match="no per-device memory usage"):
            qualify_devices(count=1, device_model="S5000")


def test_musa_qualification_rejects_uuid_selections(monkeypatch):
    # A UUID would pass discovery but the runtime maps MUSA_VISIBLE_DEVICES by
    # position, so the verified card and the executed card could differ.
    monkeypatch.setenv("MUSA_VISIBLE_DEVICES", "GPU-aaaa1111")
    with pytest.raises(ValueError, match="physical integer device ids"):
        qualify_devices(count=1, device_model="S5000")


def test_musa_qualification_rejects_other_sku(monkeypatch):
    monkeypatch.setenv("MUSA_VISIBLE_DEVICES", "0")
    idle = subprocess.CompletedProcess([], 0, json.dumps(DEVICES), "")
    with patch("inferrsi.apps.host.platforms.musa.subprocess.run", return_value=idle):
        with pytest.raises(ValueError, match="must all be S4000"):
            qualify_devices(count=1, device_model="S4000")


def test_probe_code_compiles_and_reads_a_pynvml_compatible_binding(monkeypatch, capsys):
    import sys
    import types

    from inferrsi.apps.host.platforms.musa import BUSY_CODE

    compile(PROBE_CODE, "musa-probe", "exec")
    compile(BUSY_CODE, "musa-busy", "exec")

    class Memory:
        total = 8 * 1024 * 1024 * 1024

    class Stub:
        initialized = 0
        shut = 0

        @staticmethod
        def nvmlInit():
            Stub.initialized += 1

        @staticmethod
        def nvmlShutdown():
            Stub.shut += 1

        @staticmethod
        def nvmlSystemGetDriverVersion():
            return b"6.1.0"

        @staticmethod
        def nvmlDeviceGetCount():
            return 1

        @staticmethod
        def nvmlDeviceGetHandleByIndex(index):
            assert index == 0
            return "handle-0"

        @staticmethod
        def nvmlDeviceGetUUID(handle):
            assert handle == "handle-0"
            return b"GPU-cccc3333"

        @staticmethod
        def nvmlDeviceGetName(handle):
            return b"MTT S5000"

        @staticmethod
        def nvmlDeviceGetMemoryInfo(handle):
            return Memory()

    module = types.ModuleType("pymtml")
    for name in ("nvmlInit", "nvmlShutdown", "nvmlSystemGetDriverVersion",
                 "nvmlDeviceGetCount", "nvmlDeviceGetHandleByIndex", "nvmlDeviceGetUUID",
                 "nvmlDeviceGetName", "nvmlDeviceGetMemoryInfo"):
        setattr(module, name, getattr(Stub, name))
    monkeypatch.setitem(sys.modules, "pymtml", module)

    exec(compile(PROBE_CODE, "musa-probe", "exec"), {"__name__": "musa_probe"})
    document = json.loads(capsys.readouterr().out)
    assert document["devices"] == [
        {
            "index": "0",
            "uuid": "GPU-cccc3333",
            "name": "MTT S5000",
            "driver_version": "6.1.0",
            "memory_total_mib": 8192,
        }
    ]
    assert Stub.initialized == 1 and Stub.shut == 1


def test_busy_probe_executes_fail_closed_when_the_binding_cannot_answer(monkeypatch, capsys):
    import sys
    import types

    from inferrsi.apps.host.platforms.musa import BUSY_CODE

    class Broken:
        @staticmethod
        def nvmlInit():
            raise RuntimeError("MTML init failed")

    module = types.ModuleType("pymtml")
    module.nvmlInit = Broken.nvmlInit
    monkeypatch.setitem(sys.modules, "pymtml", module)
    monkeypatch.setattr(sys, "argv", ["musa-busy", "0"])
    with pytest.raises(SystemExit) as failure:
        exec(compile(BUSY_CODE, "musa-busy", "exec"), {"__name__": "musa_busy"})
    assert failure.value.code == 3
    assert "nvmlInit failed" in json.loads(capsys.readouterr().out)["error"]

    # A binding without the process query is unknown, not an idle device.
    class Quiet:
        calls = 0

        @staticmethod
        def nvmlInit():
            Quiet.calls += 1

        @staticmethod
        def nvmlShutdown():
            Quiet.calls += 1

    module = types.ModuleType("pymtml")
    module.nvmlInit = Quiet.nvmlInit
    module.nvmlShutdown = Quiet.nvmlShutdown
    monkeypatch.setitem(sys.modules, "pymtml", module)
    with pytest.raises(SystemExit) as failure:
        exec(compile(BUSY_CODE, "musa-busy", "exec"), {"__name__": "musa_busy"})
    assert failure.value.code == 3
    assert "is unavailable" in json.loads(capsys.readouterr().out)["error"]


def test_musa_inspection_requires_the_mask_to_bind_a_nonzero_card(monkeypatch):
    # --device-ids 1 with no mask: the runtime's device 0 is card 0, so the
    # trial's logical index does not name the card that was verified.
    monkeypatch.delenv("MUSA_VISIBLE_DEVICES", raising=False)
    stdout = json.dumps({"devices": [{"index": "0", "uuid": "GPU-aaaa1111",
                                      "name": "MTT S5000", "driver_version": "6.1.0"},
                                     {"index": "1", "uuid": "GPU-bbbb2222",
                                      "name": "MTT S5000", "driver_version": "6.1.0"}]})
    device = inspect_device(
        "musa", device_ids=("1",), device_model=None, command=lambda argv: probe(stdout)
    )
    assert device["status"] == "unavailable"
    assert "does not bind the declared devices" in device["reason"]
    # Declaring the mask makes the binding explicit.
    monkeypatch.setenv("MUSA_VISIBLE_DEVICES", "1")
    bound = inspect_device(
        "musa", device_ids=("1",), device_model=None, command=lambda argv: probe(stdout)
    )
    assert bound["status"] == "available"
    assert bound["selection_verified"] is True
    # Card 0 needs no mask: it is the implicit device 0.
    monkeypatch.delenv("MUSA_VISIBLE_DEVICES", raising=False)
    zero = inspect_device(
        "musa", device_ids=("0",), device_model=None, command=lambda argv: probe(stdout)
    )
    assert zero["status"] == "available"


def test_musa_inspection_refuses_a_mask_that_remaps_the_selection(monkeypatch):
    # --device-ids 0 with MUSA_VISIBLE_DEVICES=1: the probe can reach physical
    # card 0, but the trial's logical musa:0 is physical card 1. Reporting that
    # as verified would let a run claim a card it never used.
    monkeypatch.setenv("MUSA_VISIBLE_DEVICES", "1")
    stdout = json.dumps({"devices": [{"index": "0", "uuid": "GPU-aaaa1111",
                                      "name": "MTT S5000", "driver_version": "6.1.0",
                                      "memory_total_mib": 8192},
                                     {"index": "1", "uuid": "GPU-bbbb2222",
                                      "name": "MTT S5000", "driver_version": "6.1.0",
                                      "memory_total_mib": 8192}]})
    device = inspect_device(
        "musa", device_ids=("0",), device_model=None, command=lambda argv: probe(stdout)
    )
    assert device["status"] == "unavailable"
    assert device["selection_verified"] is False
    assert "does not bind the declared devices" in device["reason"]
    # An identity mask keeps the selection verified: the declared id is the card
    # the trial's logical index resolves to.
    monkeypatch.setenv("MUSA_VISIBLE_DEVICES", "0")
    kept = inspect_device(
        "musa", device_ids=("0",), device_model=None, command=lambda argv: probe(stdout)
    )
    assert kept["status"] == "available"
    assert kept["selection_verified"] is True


def test_busy_probe_reports_usage_alongside_an_empty_process_list(monkeypatch, capsys):
    import sys
    import types

    from inferrsi.apps.host.platforms.musa import BUSY_CODE

    class Memory:
        used = 0
        total = 24 * 1024 * 1024 * 1024
        free = 24 * 1024 * 1024 * 1024

    class Quiet:
        @staticmethod
        def nvmlInit():
            return None

        @staticmethod
        def nvmlShutdown():
            return None

        @staticmethod
        def nvmlDeviceGetHandleByIndex(index):
            return "handle-%s" % index

        @staticmethod
        def nvmlDeviceGetComputeRunningProcesses(handle):
            return []

        @staticmethod
        def nvmlDeviceGetMemoryInfo(handle):
            return Memory()

    module = types.ModuleType("pymtml")
    for name in ("nvmlInit", "nvmlShutdown", "nvmlDeviceGetHandleByIndex",
                 "nvmlDeviceGetComputeRunningProcesses", "nvmlDeviceGetMemoryInfo"):
        setattr(module, name, getattr(Quiet, name))
    monkeypatch.setitem(sys.modules, "pymtml", module)
    monkeypatch.setattr(sys, "argv", ["musa-busy", "0"])
    exec(compile(BUSY_CODE, "musa-busy", "exec"), {"__name__": "musa_busy"})
    document = json.loads(capsys.readouterr().out)
    assert document["processes"] == []
    assert document["usage"] == [{"device": "0", "used_mib": 0}]


def test_musa_probe_drops_only_the_unreadable_device(monkeypatch):
    monkeypatch.setenv("MUSA_VISIBLE_DEVICES", "1")
    stdout = json.dumps(
        {
            "devices": [
                {"index": "0", "error": "NVMLError: no permission"},
                {
                    "index": "1",
                    "uuid": "GPU-dddd4444",
                    "name": "MTT S5000",
                    "driver_version": "6.1.0",
                    "memory_total_mib": 49152,
                },
            ]
        }
    )
    device = inspect_device(
        "musa", device_ids=("1",), device_model=None, command=lambda argv: probe(stdout)
    )
    assert device["status"] == "available"
    assert [row["id"] for row in device["devices"]] == ["1"]
    # Naming the unreadable device stays a failure rather than a silent pass.
    missing = inspect_device(
        "musa", device_ids=("0",), device_model=None, command=lambda argv: probe(stdout)
    )
    assert missing["status"] == "unavailable"
    assert "absent" in missing["reason"]
