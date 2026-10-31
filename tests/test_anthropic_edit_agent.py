"""Scripted protocol/callback tests only: no credentials, network or candidate exec."""

import copy
import hashlib
from dataclasses import replace

import pytest

from inferrsi.model import anthropic_agent as provider
from inferrsi.model import anthropic_edit_agent as edit

MODEL = "claude-opus-5-5"
PLAN_HASH = "a" * 64
CHECKS = {"verdict": "PASS", "checks": {"public-one": True, "public-two": True},
          "reason": "none"}
BENCHMARK = {"verdict": "PASS", "baseline_values": [2.0, 2.2],
             "candidate_values": [1.0, 1.1], "quality_verdict": "PASS",
             "improvement_pct": 50.0, "reason": "none"}


def call(name, value=None, identifier=None):
    return {"type": "tool_use", "id": identifier or name, "name": name,
            "input": {} if value is None else value}


def response(*calls, **changes):
    return {"type": "message", "role": "assistant", "model": MODEL,
            "stop_reason": "tool_use", "content": list(calls),
            "usage": {"input_tokens": 10, "output_tokens": 5,
                      "cache_read_input_tokens": 2, "cache_creation_input_tokens": 1},
            **changes}


def read_task(identifier="read-task"):
    return response(call("read_file", {"path": "task.json"}, identifier))


def work(source="# candidate revision\n", suffix=""):
    return response(call("write_candidate", {"source": source}, "write" + suffix),
                    call("run_visible_checks", identifier="check" + suffix),
                    call("run_visible_benchmark", identifier="bench" + suffix))


def submit():
    return response(call("submit_candidate"))


@pytest.fixture
def fixture(tmp_path):
    root = tmp_path / "exposed"
    root.mkdir()
    (root / "task.json").write_text('{"request":"optimize public synthetic CPU work"}\n')
    (root / "candidate.py").write_text("# initial visible linear scan\n")
    (root / "contract.md").write_text("Public candidate contract.\n")
    (tmp_path / "oracle.py").write_text("hidden oracle sentinel\n")
    spec = {"kind": edit.KIND, "provider": "yibuapi", "endpoint": provider.ENDPOINT,
            "api_version": "2023-06-01", "max_requests": 8, "max_output_tokens": 4096,
            "max_request_bytes": 1048576, "max_read_bytes": 65536, "max_tool_calls": 24}
    limits = edit.EditLimits(65536, 4096, 8, 8, 4, 2, 600)
    plan = edit.EditPlan(edit.freeze_files(root, ["task.json", "candidate.py", "contract.md"]),
                         limits, ("public-one", "public-two"), "elapsed_seconds", "seconds",
                         "minimize", "b" * 64)
    return root, plan, spec


def slots():
    return edit.RequestSlots(PLAN_HASH, {"A2": 8, "A3": 8}, 10170000, 162720000,
                              execution_id="offline-attempt-1")


def run(fixture, responses, *, events=None, pool=None, arm="A2", deadline=600,
        clock=lambda: 0, authorize=None, send=None, checks=None, benchmark=None, retain=None):
    root, plan, spec = fixture
    requests, grants, observations = [], [], []
    events = [] if events is None else events
    pool = slots() if pool is None else pool

    def approval(grant, end):
        grants.append((dict(grant), end))
        return True

    def transport(payload, settings, timeout):
        requests.append(copy.deepcopy(payload))
        assert timeout > 0
        value = responses[len(requests) - 1]
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)

    def checker(source, end):
        observations.append(("check", source, end))
        return copy.deepcopy(CHECKS)

    def measure(source, end):
        observations.append(("benchmark", source, end))
        return copy.deepcopy(BENCHMARK)

    answer = edit.run_edit_agent(root, plan, "Optimize the visible task.", MODEL, spec,
                                 deadline, events.append, arm=arm, slots=pool,
                                 authorize=authorize or approval, send=send or transport,
                                 visible_checks=checks or checker,
                                 visible_benchmark=benchmark or measure,
                                 retain_revision=retain or (lambda *_: True),
                                 input_token_ceiling=1000000, clock=clock)
    return answer, requests, grants, observations, events, pool


def test_real_write_check_measure_feedback_rewrite_and_exact_final_snapshot(fixture):
    first, second = "# source one\n", "# source two\n"
    answer, requests, grants, observations, events, pool = run(
        fixture, [read_task(), work(first, "1"), work(second, "2"), submit()])
    assert fixture[0].joinpath("candidate.py").read_text() == second
    assert answer["artifact_source"] == second and answer["revision"] == 2
    assert (answer["plan_sha256"], answer["execution_id"], answer["arm"]) == (
        PLAN_HASH, "offline-attempt-1", "A2")
    assert answer["sha256"] == hashlib.sha256(second.encode()).hexdigest()
    assert [entry[0:2] for entry in observations] == [
        ("check", first.encode()), ("benchmark", first.encode()),
        ("check", second.encode()), ("benchmark", second.encode())]
    assert {entry[2] for entry in observations} == {600}
    assert [g[0]["slot"] for g in grants] == [1, 2, 3, 4]
    assert all(g[1] == 600 and g[0]["reserved_microusd"] == 10170000 for g in grants)
    assert pool.usage() == {"A2": 4, "A3": 0}
    assert {t["name"] for t in requests[0]["tools"]} == {
        "read_file", "write_candidate", "run_visible_checks", "run_visible_benchmark",
        "submit_candidate"}
    feedback = requests[2]["messages"][-1]["content"]
    assert '"improvement_pct":50.0' in feedback[2]["content"]
    assert '"public-one":true' in feedback[1]["content"]
    assert "hidden oracle sentinel" not in provider.canonical(requests)
    assert first not in provider.canonical(events) and second not in provider.canonical(events)
    assert events[-1] == {"type": "agent.completed", "usage": {
        "input_tokens": 52, "output_tokens": 20, "cached_input_tokens": 8}, "requests": 4}
    receipts = [e["receipt"] for e in events if "receipt" in e]
    assert len(receipts) == 4
    for value in receipts:
        assert (value["plan_sha256"], value["execution_id"], value["arm"]) == (
            PLAN_HASH, "offline-attempt-1", "A2")
        raw = {k: v for k, v in value.items() if k != "receipt_sha256"}
        assert value["receipt_sha256"] == edit.fingerprint({
            **raw, "actor_sha256": answer["actor_sha256"]})


def test_all_actual_revision_bytes_retained_before_checks(fixture):
    retained = []
    def retain(source, metadata, deadline):
        assert type(source) is bytes and deadline == 600
        retained.append((source, dict(metadata)))
        return True
    def checks(source, deadline):
        assert retained[-1][0] == source
        return CHECKS
    answer, *_ = run(fixture, [read_task(), work("# first\n", "1"), work("# final\n", "2"),
                              submit()], retain=retain, checks=checks)
    assert [m["revision"] for _, m in retained] == [0, 1, 2]
    assert [s for s, _ in retained] == [b"# initial visible linear scan\n", b"# first\n",
                                      b"# final\n"]
    assert retained[-1][1]["sha256"] == answer["sha256"]


def test_uncertain_retention_sends_nothing_and_does_not_leak_exception(fixture):
    events = []
    def retain(*_):
        raise provider.AgentError("private filesystem error")
    with pytest.raises(provider.AgentError, match="revision_retention_error"):
        run(fixture, [], retain=retain, events=events)
    assert "private filesystem" not in provider.canonical(events)
    assert not any(e["type"] == "agent.request" for e in events)


def test_source_is_never_executed_by_protocol(fixture):
    source = "raise AssertionError('This must never execute on host')\n"
    answer, *_ = run(fixture, [read_task(), work(source), submit()])
    assert answer["artifact_source"] == source


def test_failed_candidate_may_finish_but_never_becomes_a_passing_check(fixture):
    failing = {"verdict": "FAIL", "checks": {"public-one": False, "public-two": True},
               "reason": "check_failed"}
    answer, requests, *_ = run(fixture, [read_task(), work(), submit()],
                               checks=lambda *_: failing)
    assert answer["sha256"]
    assert '"verdict":"FAIL"' in requests[-1]["messages"][-1]["content"][1]["content"]


def test_write_invalidates_both_receipts_including_unchanged_source(fixture):
    responses = [read_task(), work(), response(call("write_candidate", {
        "source": "# candidate revision\n"}, "new-write")), submit()]
    with pytest.raises(provider.AgentError, match="stale_or_missing_receipt"):
        run(fixture, responses)


@pytest.mark.parametrize("tool", ["run_visible_checks", "run_visible_benchmark"])
def test_both_current_revision_receipts_required(fixture, tool):
    with pytest.raises(provider.AgentError, match="stale_or_missing_receipt"):
        run(fixture, [read_task(), response(call(tool)), submit()])


@pytest.mark.parametrize("path", ["../oracle.py", "/etc/passwd", "oracle.py", "contract.md/..",
                                   "..\\oracle.py", 1])
def test_only_exact_manifest_files_are_readable(fixture, path):
    with pytest.raises(provider.AgentError, match="unexposed_path"):
        run(fixture, [response(call("read_file", {"path": path}))])


@pytest.mark.parametrize("name,args", [
    ("write_candidate", {"source": "x", "path": "contract.md"}),
    ("run_visible_checks", {"command": "anything"}),
    ("run_visible_benchmark", {"events": []}),
    ("submit_candidate", {"sha256": "c" * 64}),
    ("exec", {"command": "anything"}),
])
def test_no_arbitrary_commands_paths_or_workloads(fixture, name, args):
    with pytest.raises(provider.AgentError, match="unsupported_tool"):
        run(fixture, [read_task(), response(call(name, args))])


@pytest.mark.parametrize("change", ["protected", "extra", "symlink", "fifo", "hardlink"])
def test_workspace_changes_and_special_nodes_fail_closed(fixture, tmp_path, change):
    root = fixture[0]
    if change == "protected":
        (root / "contract.md").write_text("changed")
    elif change == "extra":
        (root / "extra").mkdir()
    elif change == "symlink":
        (root / "candidate.py").unlink()
        (root / "candidate.py").symlink_to(tmp_path / "oracle.py")
    elif change == "fifo":
        import os
        os.mkfifo(root / "extra")
    else:
        import os
        os.link(root / "contract.md", tmp_path / "hardlink")
    events = []
    with pytest.raises(provider.AgentError):
        run(fixture, [], events=events)
    assert not any(e["type"] in {"agent.request", "edit.slot"} for e in events)


def test_root_symlink_rejected(fixture, tmp_path):
    root, plan, spec = fixture
    link = tmp_path / "link"
    link.symlink_to(root, target_is_directory=True)
    with pytest.raises(provider.AgentError, match="workspace_symlink"):
        run((link, plan, spec), [])


@pytest.mark.parametrize("source", ["", "x" * 65537, "\ud800", None, 3])
def test_invalid_candidate_bytes_rejected(fixture, source):
    with pytest.raises(provider.AgentError):
        run(fixture, [read_task(), response(call("write_candidate", {"source": source}))])


def test_callback_cannot_swap_source_or_protected_fixture(fixture):
    def corrupt(source, deadline):
        (fixture[0] / "candidate.py").write_text("# different bytes\n")
        return CHECKS
    with pytest.raises(provider.AgentError, match="protected_workspace_changed"):
        run(fixture, [read_task(), work()], checks=corrupt)


@pytest.mark.parametrize("value", [
    {**CHECKS, "stderr": "private host path"},
    {**CHECKS, "checks": {"hidden-grader-id": True}},
    {**CHECKS, "checks": {"public-one": 1, "public-two": True}},
    {**CHECKS, "reason": "secret text"},
    {**CHECKS, "checks": {"public-one": False, "public-two": True}},
])
def test_feedback_does_not_pass_raw_text_unknown_or_hidden_ids(fixture, value):
    events = []
    with pytest.raises(provider.AgentError, match="invalid_visible_feedback"):
        run(fixture, [read_task(), work()], checks=lambda *_: value, events=events)
    assert "private host path" not in provider.canonical(events)
    assert "hidden-grader-id" not in provider.canonical(events)


@pytest.mark.parametrize("updates", [
    {"candidate_values": [float("nan")]}, {"candidate_values": [True, 1]},
    {"candidate_values": [0, 1]}, {"candidate_values": [1, 2, 3]},
    {"candidate_values": []}, {"quality_verdict": "FAIL"},
    {"improvement_pct": float("inf")}, {"stderr": "private"},
])
def test_benchmark_feedback_is_fixed_finite_and_bounded(fixture, updates):
    with pytest.raises(provider.AgentError, match="invalid_visible_feedback"):
        run(fixture, [read_task(), work()], benchmark=lambda *_: {**BENCHMARK, **updates})


def test_request_growth_rejected_before_next_slot_or_send(fixture):
    root, plan, spec = fixture
    events = []
    small = {**spec, "max_request_bytes": 3000}
    pool = slots()
    with pytest.raises(provider.AgentError, match="request_bytes_limit"):
        run((root, plan, small), [read_task(), work("# " + "x" * 3000)],
            events=events, pool=pool)
    assert pool.usage()["A2"] == 2
    assert len([e for e in events if e["type"] == "agent.request"]) == 2


def test_feedback_wrapper_counted_in_byte_bound(fixture):
    root, plan, spec = fixture
    plan = replace(plan, limits=replace(plan.limits, max_feedback_bytes=200))
    with pytest.raises(provider.AgentError, match="feedback_bytes_limit"):
        run((root, plan, spec), [read_task(), work()])


def test_request_limit_is_eight_attempts_no_retry_and_other_arm_cannot_lend(fixture):
    pool, events = slots(), []
    responses = [read_task(str(i)) for i in range(8)]
    with pytest.raises(provider.AgentError, match="request_limit"):
        run(fixture, responses, pool=pool, events=events)
    assert pool.usage() == {"A2": 8, "A3": 0}
    assert len([e for e in events if e["type"] == "agent.request"]) == 8
    with pytest.raises(provider.AgentError, match="request_allocation_unavailable"):
        run(fixture, [], pool=pool)


def test_unknown_transport_failure_burns_slot_and_never_retries(fixture):
    pool, events = slots(), []
    with pytest.raises(provider.AgentError, match="provider_transport_error"):
        run(fixture, [OSError("credential-bearing transport error")], pool=pool, events=events)
    assert pool.usage() == {"A2": 1, "A3": 0}
    assert "credential-bearing" not in provider.canonical(events)
    with pytest.raises(provider.AgentError, match="request_allocation_unavailable"):
        run(fixture, [], pool=pool)
    with pytest.raises(provider.AgentError, match="request_allocation_unavailable"):
        run(fixture, [], pool=pool, arm="A3")


@pytest.mark.parametrize("updates", [
    {"usage": None}, {"model": "wrong"}, {"stop_reason": "end_turn"},
    {"usage": {"input_tokens": 1000001, "output_tokens": 1,
               "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}},
    {"usage": {"input_tokens": 1, "output_tokens": 4097,
               "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}},
])
def test_unknown_or_out_of_bound_response_cost_stops_both_arms(fixture, updates):
    pool = slots()
    with pytest.raises(provider.AgentError):
        run(fixture, [{**read_task(), **updates}], pool=pool)
    assert pool.usage() == {"A2": 1, "A3": 0}
    with pytest.raises(provider.AgentError, match="request_allocation_unavailable"):
        run(fixture, [], pool=pool, arm="A3")


def test_late_unaccounted_provider_response_stops_both_arms(fixture):
    pool, now = slots(), [0]
    def send(*_):
        now[0] = 600
        return read_task()
    with pytest.raises(provider.AgentError, match="timeout"):
        run(fixture, [], pool=pool, clock=lambda: now[0], send=send)
    assert pool.usage() == {"A2": 1, "A3": 0}
    with pytest.raises(provider.AgentError, match="request_allocation_unavailable"):
        run(fixture, [], pool=pool, arm="A3")


@pytest.mark.parametrize("failure", [KeyboardInterrupt, SystemExit])
def test_cancellation_cannot_resume_other_arm_after_an_unaccounted_send(fixture, failure):
    pool, events = slots(), []
    def send(*_):
        raise failure("private cancellation detail")
    with pytest.raises(failure):
        run(fixture, [], pool=pool, events=events, send=send)
    assert pool.usage() == {"A2": 1, "A3": 0}
    assert "private cancellation" not in provider.canonical(events)
    with pytest.raises(provider.AgentError, match="request_allocation_unavailable"):
        run(fixture, [], pool=pool, arm="A3")


def test_authorization_failure_consumes_grant_stops_pool_and_sends_nothing(fixture):
    pool, events = slots(), []
    with pytest.raises(provider.AgentError, match="request_authorization_denied"):
        run(fixture, [], pool=pool, events=events, authorize=lambda *_: None)
    assert pool.usage() == {"A2": 1, "A3": 0}
    assert not any(e["type"] == "agent.request" for e in events)
    with pytest.raises(provider.AgentError, match="request_allocation_unavailable"):
        run(fixture, [], pool=pool, arm="A3")


def test_slots_burn_before_authorization(fixture):
    pool = slots()
    def approval(grant, deadline):
        assert pool.usage()["A2"] == grant["slot"]
        assert grant["reserved_microusd"] == 10170000 and deadline == 600
        return True
    run(fixture, [read_task(), work(), submit()], pool=pool, authorize=approval)
    assert pool.reserved_microusd == 162720000  # No automatic cost refund on success.


@pytest.mark.parametrize("stage", ["before", "authorization", "transport", "check", "benchmark"])
def test_one_absolute_deadline_never_restarts_and_rejects_late_results(fixture, stage):
    now, events, pool = [600 if stage == "before" else 0], [], slots()
    def approval(*_):
        if stage == "authorization":
            now[0] = 600
        return True
    def check(source, deadline):
        assert deadline == 600
        if stage == "check":
            now[0] = 600
        return CHECKS
    def benchmark(source, deadline):
        assert deadline == 600
        if stage == "benchmark":
            now[0] = 600
        return BENCHMARK
    def transport(*_):
        now[0] = 600
        return read_task()
    with pytest.raises(provider.AgentError, match="timeout"):
        run(fixture, [read_task(), work(), submit()], pool=pool, events=events,
            clock=lambda: now[0], authorize=approval, checks=check, benchmark=benchmark,
            send=transport if stage == "transport" else None)
    assert not any(e["type"] == "agent.completed" for e in events)
    assert pool.usage()["A2"] == (0 if stage == "before" else
                                  1 if stage in {"authorization", "transport"} else 2)


def test_allowance_passed_to_transport_excludes_authorization_time(fixture):
    now, remaining = [1], []
    def approval(*_):
        now[0] += 20
        return True
    def transport(*args):
        remaining.append(args[-1])
        return [read_task(), work(), submit()][len(remaining) - 1]
    run(fixture, [], clock=lambda: now[0], authorize=approval, send=transport)
    assert remaining == [579, 559, 539]


def test_deadline_cannot_extend_frozen_limit(fixture):
    events = []
    with pytest.raises(provider.AgentError, match="deadline_exceeds_frozen_limit"):
        run(fixture, [], deadline=601, events=events)
    assert not any(e["type"] == "edit.slot" for e in events)


def test_callback_exception_text_does_not_cross_evidence_boundary(fixture):
    events = []
    def callback(*_):
        raise provider.AgentError("secret from candidate-controlled stderr")
    with pytest.raises(provider.AgentError, match="visible_callback_error"):
        run(fixture, [read_task(), work()], checks=callback, events=events)
    assert "secret from" not in provider.canonical(events)


@pytest.mark.parametrize("bad", [submit(), work(), response(call("run_visible_checks"))])
def test_no_actions_before_task_read_feedback_roundtrip(fixture, bad):
    with pytest.raises(provider.AgentError, match="task_not_read"):
        run(fixture, [bad])


@pytest.mark.parametrize("position", [0, 1, 2])
def test_redundant_task_read_preserves_completed_roundtrip(fixture, position):
    source = "# edited after an earlier task-read round trip\n"
    later = work(source)
    later["content"].insert(position, call("read_file", {"path": "task.json"}, "reread"))
    answer, requests, _, observations, _, pool = run(
        fixture, [read_task(), later, submit()])
    assert answer["artifact_source"] == source and answer["revision"] == 1
    assert [entry[:2] for entry in observations] == [
        ("check", source.encode()), ("benchmark", source.encode())]
    assert len(requests) == 3 and pool.usage() == {"A2": 3, "A3": 0}
    assert requests[1]["messages"][-1]["content"][0]["tool_use_id"] == "read-task"


@pytest.mark.parametrize("action", [
    call("write_candidate", {"source": "# must not be written\n"}),
    call("run_visible_checks"), call("run_visible_benchmark"), call("submit_candidate"),
])
def test_first_task_read_cannot_authorize_actions_in_same_response(fixture, action):
    initial = (fixture[0] / "candidate.py").read_bytes()
    events = []
    with pytest.raises(provider.AgentError, match="task_not_read"):
        run(fixture, [response(call("read_file", {"path": "task.json"}), action)],
            events=events, checks=lambda *_: pytest.fail("no check before read round trip"),
            benchmark=lambda *_: pytest.fail("no measurement before read round trip"))
    assert (fixture[0] / "candidate.py").read_bytes() == initial
    assert [e["revision"] for e in events if e["type"] == "edit.artifact"] == [0]


def test_reused_tool_id_rejected_across_requests(fixture):
    with pytest.raises(provider.AgentError, match="invalid_tool_call"):
        run(fixture, [read_task(), read_task()])


def test_legacy_adapter_is_not_relabelled_and_existing_tools_unchanged(fixture):
    root, _, spec = fixture
    with pytest.raises(ValueError, match="separate bounded"):
        provider.run_agent(root, {"type": "object"}, "", MODEL, spec, 600, lambda _: None,
                           send=lambda *_: pytest.fail("must not send"))
    with pytest.raises(ValueError, match="separate bounded"):
        provider.AnthropicAgentClient(MODEL, spec, 600)


def test_offline_identity_binds_implementation_and_tool_dependencies(fixture):
    _, plan, spec = fixture
    identity = edit.frozen_identity(plan, MODEL, spec, 1000000)
    assert identity["request_policy"]["retries"] == 0
    assert set(identity["sources"]) == {
        "anthropic_edit_agent.py", "anthropic_agent.py", "request_guard.py"}
    changed = edit.frozen_identity(replace(plan, callbacks_sha256="c" * 64),
                                    MODEL, spec, 1000000)
    assert edit.fingerprint(changed) != edit.fingerprint(identity)
    assert identity["plan"]["limits"]["max_seconds"] == 600


def test_full_context_cost_bound_reused_without_token_conversion(fixture):
    pricing = {"currency": "USD", "unit": "per_million_tokens", "model": MODEL,
               "group": "offline-fixture", "rates": {"input": "8", "output": "40",
               "cache_read": "0.4", "cache_write": "10"}, "request_fee": "0",
               "max_input_tokens": 1000000, "rate_evidence":
               "https://github.com/InferMatrixLab/InferRSI/issues/1#issuecomment-1",
               "expires_at": 9999999999}
    bound = provider.reservation(MODEL, fixture[2], pricing,
                                  {"currency": "USD", "amount": "200"}, 2, now=0)
    assert (bound["per_request"], bound["amount"], bound["requests"]) == ("10.17", "162.72", 16)


@pytest.mark.parametrize("field,value", [
    ("max_writes", 0), ("max_checks", True), ("max_benchmarks", -1),
    ("max_source_bytes", 65537), ("max_feedback_bytes", float("inf")),
])
def test_limits_are_explicit_positive_and_frozen(fixture, field, value):
    with pytest.raises(ValueError):
        replace(fixture[1].limits, **{field: value})


def test_manifest_requires_task_candidate_safe_paths_and_no_duplicates(fixture):
    root, plan, _ = fixture
    for name in ("../oracle.py", "/oracle.py", "a/../b", "./task.json", "a//b", "a\\b"):
        with pytest.raises(ValueError):
            edit.ExposedFile(name, 0, "c" * 64)
    with pytest.raises(ValueError):
        edit.freeze_files(root, ["task.json", "task.json"])
    with pytest.raises(ValueError):
        replace(plan, files=(plan.files[-1],))


def test_reservation_identity_and_exact_slot_allocation_required():
    with pytest.raises(ValueError):
        edit.RequestSlots(PLAN_HASH, {"A2": 8, "A3": 8}, 10170000, 1,
                           execution_id="offline-attempt-1")
    pool = slots()
    with pytest.raises(provider.AgentError):
        pool.start("A2", 9)
    with pytest.raises(provider.AgentError):
        pool.consume("A2", "a" * 64, "b" * 64)
