"""#412 R3: the two in-process evaluator loaders give fresh, unregistered modules.

Frozen-file identity is checked by their callers (MoE ``_adjudicate`` and the Qwen21
``main``/protocol ``assess``); these tests pin the loaders' own contract.
"""

import sys

import pytest

from tests.engineering_task_support import load_task_module

grader = load_task_module("moe-forward-npu", "grader")
qwen = load_task_module("qwen21-denoise-npu", "benchmark")


def source(tmp_path, body, name="candidate.py"):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_moe_grader_load_returns_a_fresh_compute_each_time(tmp_path):
    path = source(tmp_path, "STATE = []\ndef compute(x, params, *, config, group):\n"
                            "    STATE.append(x)\n    return STATE\n")
    first = grader.load(path, "evaluated_candidate")
    second = grader.load(path, "evaluated_candidate")
    assert first is not second and first.__globals__ is not second.__globals__
    assert first(1, {}, config={}, group=None) == [1]
    assert second(2, {}, config={}, group=None) == [2]
    assert "evaluated_candidate" not in sys.modules


@pytest.mark.parametrize("body", ["", "compute = 3\n"])
def test_moe_grader_load_requires_a_callable_compute(tmp_path, body):
    with pytest.raises(ValueError, match="Candidate must define compute"):
        grader.load(source(tmp_path, body), "evaluated_candidate")


def test_qwen21_load_returns_a_fresh_unregistered_module_each_time(tmp_path):
    path = source(tmp_path, "STATE = []\n", "workload.py")
    first = qwen.load(path, "task_workload")
    second = qwen.load(path, "task_workload")
    first.STATE.append(1)
    assert first is not second and second.STATE == []
    assert "task_workload" not in sys.modules


@pytest.mark.parametrize("body, message", [
    ("", "Candidate must define callable compute"),
    ("compute = 3\n", "Candidate must define callable compute"),
    ("def compute(x):\n    pass\n", "compute does not accept the task arguments"),
    ("def compute(:\n", "invalid syntax"),
])
def test_qwen21_candidate_entry_requires_the_task_compute(tmp_path, body, message):
    with pytest.raises(qwen.CandidateContractError, match=message):
        qwen.candidate_function(source(tmp_path, body))
    assert "submitted_candidate" not in sys.modules
