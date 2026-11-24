"""Exercise a generated candidate under a distinct, saved CLI evaluation attempt."""

import json
from pathlib import Path

from inferrsi.apps.cli import main
from inferrsi.benchmark import cpu_smoke
from inferrsi.benchmark.workers import fixture_worker as worker
from inferrsi.harness import execution_service
from tests.test_apps_evaluate_cli import arguments, execute_request, save, target_config
from tests.test_apps_generation_plan import generation as generation
from tests.test_harness_generation_lineage import lineage as lineage
from tests.test_harness_generation_seal import cpu_generation as cpu_generation


def test_generated_candidate_through_saved_commands(lineage, tmp_path, capsys):
    config = lineage["config"]
    runtime = target_config({"target": lineage["evaluation_target"]})
    code = Path(worker.__file__)
    protocol = cpu_smoke.protocol(
        code.read_bytes(), control_domain=execution_service._CONTROL_DOMAIN,
    )
    runtime["benchmark"] = {
        "protocol": str(save(tmp_path, "protocol.json", protocol)), "worker_role": "worker-code",
        "resources": {"worker-code": str(code), "baseline-code": str(code)},
    }
    prepare = {"schema_version": 1, "request": cpu_smoke.default_request()}
    assert main(arguments(tmp_path, "prepare", prepare, config, runtime, output="cli-prepare")) == 0
    request = execute_request(lineage)
    request["prepared_ref"] = json.loads(capsys.readouterr().out)["prepared_ref"]
    generation_ref = lineage["generated"]["record_ref"]
    assert request["attempt"]["attempt_id"] != generation_ref["attempt_id"]

    assert main(arguments(tmp_path, "execute", request, config, runtime, output="cli-execute")
                + ["--capture-evidence"]) == 0
    executed = json.loads(capsys.readouterr().out)
    assert executed["execution"]["generation_record_ref"] == generation_ref
    assert executed["record_ref"]["attempt_id"] == request["attempt"]["attempt_id"]
    assessment = {"schema_version": 1, "record_ref": executed["record_ref"],
                  "primary_scope": "p1", "primary_claim_id": "C"}
    assert main(arguments(tmp_path, "assess", assessment, config, output="cli-assess")) == 8
    assessed = json.loads(capsys.readouterr().out)["assessment"]
    assert assessed["record_ref"] == executed["record_ref"]
    assert [(item["claim_id"], item["verdict"]) for item in assessed["claims"]] == [
        ("F", "PASS"), ("C", "FAIL"), ("M", "PASS"),
    ]
