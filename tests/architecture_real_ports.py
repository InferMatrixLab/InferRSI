"""One CPU/offline connection injected into the closed-loop handoff.

This is the test-local assembler for that connection. It is not an Apps
package. Knowledge, Harness, and Benchmark stay in their current modules and
do not import one another here. ``KnowledgeReader.read`` is the read.
``collect`` and ``search_knowledge`` stay unused. ``MemoryArchive`` still
holds prepared and assessment bytes; this module does not choose a run store.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

from inferrsi.evaluation import evaluate
from inferrsi.harness.scenarios.external import execute_trial
from inferrsi.knowledge_operations import KnowledgeReader
from inferrsi.runspec import RunSpec
from tests.architecture_closed_loop import _canonical, _digest

# Installed package card. Its bundle is record.json only, so this read does
# not pull the skill library. The id is a catalog key, not a revision pin.
PACKAGE_READ = "transformers.common.llm.kv_cache_strategy_contracts"

_PROBE = (
    "import json\n"
    "import os\n"
    "from pathlib import Path\n"
    "\n"
    "Path(os.environ['INFERRSI_RESULT_PATH']).write_text(\n"
    "    json.dumps({'probe': 'cpu-offline', 'device': None}),\n"
    "    encoding='utf-8',\n"
    ")\n"
)


class PackageKnowledgeRead:
    """One ``KnowledgeReader.read`` of an installed package card."""

    def __init__(self, reference: str = PACKAGE_READ) -> None:
        self.reference = reference
        self.calls = 0
        self.revision: str | None = None
        self.record_id: str | None = None

    def deliver(self) -> dict:
        self.calls += 1
        bundle = KnowledgeReader().read(self.reference)
        if set(bundle.content) != {"record.json"}:
            raise RuntimeError("this connection reads one record.json card")
        self.revision = bundle.revision
        self.record_id = bundle.metadata["id"]
        return {
            "id": self.record_id,
            "revision": self.revision,
            "kind": bundle.metadata["kind"],
        }


class CpuOfflineHarnessRecord:
    """One local ``execute_trial`` record. No device and no ``evaluate`` call."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.attempt_id = "cpu-offline-1"
        self.executes = 0
        self.fact: dict | None = None
        self.execution: dict | None = None

    def allocate_attempt(self) -> dict:
        return {"attempt_id": self.attempt_id, "retry_of": None}

    def execute(self, spec: dict) -> dict:
        self.executes += 1
        script = self.workspace / "cpu_offline_probe.py"
        script.write_text(_PROBE, encoding="utf-8")
        trial = self.workspace / "trial"
        record = execute_trial(
            (sys.executable, str(script)),
            self.workspace,
            trial,
            time.monotonic() + 30,
            None,
        )
        self.execution = record
        if record.get("status") != "completed" or record.get("returncode") != 0:
            return {"kind": "no_record"}
        probe = json.loads(Path(record["result_path"]).read_text(encoding="utf-8"))
        fact = {
            "attempt_id": spec["attempt_id"],
            "prepared_digest": spec["prepared_digest"],
            "status": record["status"],
            "returncode": record["returncode"],
            "probe": probe["probe"],
            "device": probe["device"],
        }
        self.fact = fact
        return {
            "kind": "completed",
            "record_ref": {
                "attempt_id": spec["attempt_id"],
                "record_version": 1,
                "digest": _digest(_canonical(fact)),
            },
            "evidence": {
                "status": record["status"],
                "returncode": record["returncode"],
                "exit_code": record["returncode"],
                "samples": "retained",
                "probe": probe["probe"],
                "device": probe["device"],
                "integrity_checks": ["local_process_returncode"],
            },
        }


class OfflineBenchmarkAssessment:
    """Freeze the read, then ``evaluate`` the retained record without a process."""

    def __init__(self) -> None:
        self.prepares = 0
        self.assesses = 0
        self.last: dict | None = None

    def prepare(self, delivered: dict) -> dict:
        self.prepares += 1
        return {
            "task": "cpu-offline-connection",
            "knowledge_id": delivered["id"],
            "knowledge_revision": delivered["revision"],
            "kind": delivered["kind"],
            "candidate": "unbound",
            "repetitions": 1,
            "direction": "minimize",
            "metric_key": "metrics.latency_ms",
            "metric_unit": "ms",
            "comparison_scope": "cpu_offline_record",
            "min_improvement_pct": 0.0,
        }

    def assess(self, prepared_bytes: bytes, evidence: dict) -> dict:
        self.assesses += 1
        prepared = json.loads(prepared_bytes)
        spec = RunSpec(
            repo=".",
            repetitions=prepared["repetitions"],
            direction=prepared["direction"],
            metric_key=prepared["metric_key"],
            metric_unit=prepared["metric_unit"],
            comparison_scope=prepared["comparison_scope"],
            min_improvement_pct=prepared["min_improvement_pct"],
        )
        observed = {
            "status": evidence.get("status"),
            "metric": None,
            "metric_error": "one CPU record is not a paired measurement",
        }

        def refuse(*_args, **_kwargs):
            raise AssertionError("offline assess started a process")

        with patch.object(subprocess, "run", refuse), patch.object(subprocess, "Popen", refuse):
            result = evaluate(
                spec,
                [observed],
                [],
                None,
                {"verified": False, "reason": "cpu offline record has no source snapshot"},
            )
        self.last = result
        return {
            "verdict": result["verdict"],
            "knowledge_id": prepared["knowledge_id"],
            "knowledge_revision": prepared["knowledge_revision"],
            "record_status": evidence.get("status"),
            "record_returncode": evidence.get("returncode"),
            "reasons": result["reasons"],
        }
