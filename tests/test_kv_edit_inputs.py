import json
from copy import deepcopy

import pytest

from tools import kv_edit_inputs as inputs


def test_common_inputs_and_prompt_are_shared_without_expected_or_hidden_data():
    development = [{"id": "visible", "split": "development", "events": [{}],
                    "expected": [{"trusted_expected_canary": True}]}]
    public, prompt, suite = inputs.build_inputs(
        b"# starter\n", b"# neutral contract\n", development, [], {"benchmark_canary": True}, 0
    )
    assert set(public) == inputs.COMMON
    assert prompt == inputs.PROMPT
    assert json.loads(public["development.json"])["traces"] == [{"id": "visible", "events": [{}]}]
    assert all(b"trusted_expected_canary" not in data and b"benchmark_canary" not in data
               for data in public.values())
    assert suite.read()["development"] == development
    assert inputs.build_inputs(b"# starter\n", b"# neutral contract\n", development,
                               [], {"benchmark_canary": True}, 0)[:2] == (public, prompt)


def test_hidden_split_is_never_accepted_as_public_input():
    with pytest.raises(ValueError, match="split"):
        inputs.build_inputs(b"# starter\n", b"# contract\n",
                            [{"id": "secret", "split": "grader", "events": [], "expected": []}],
                            [], {}, 0)


@pytest.mark.parametrize("field", ["arm", "suite_sha256", "baseline_sha256", "client",
                                  "model", "input_token_ceiling", "prompt", "files", "limits",
                                  "check_ids", "metric_key", "metric_unit", "direction"])
def test_common_contract_binds_all_non_transport_actor_inputs(field):
    config = {k: k for k in ("arm", "model", "client", "input_token_ceiling", "prompt",
                             "suite_sha256", "baseline_sha256")}
    config["edit_plan"] = {k: k for k in ("files", "limits", "check_ids", "metric_key",
                                          "metric_unit", "direction", "callbacks_sha256")}
    original = inputs.common_actor_contract_sha256(config)
    changed = deepcopy(config)
    (changed["edit_plan"] if field in config["edit_plan"] else changed)[field] = "changed"
    assert inputs.common_actor_contract_sha256(changed) != original
    scripted = deepcopy(config)
    scripted["edit_plan"]["callbacks_sha256"] = "different-response-fixture-binding"
    scripted["responses_sha256"] = "scripted-only"
    scripted["plan_sha256"] = "separate-campaign"
    scripted["actor_sha256"] = "different-transport-identity"
    assert inputs.common_actor_contract_sha256(scripted) == original
