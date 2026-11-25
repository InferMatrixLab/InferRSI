"""Read-only checks of real managed campaigns, not an optimization engine.

Harness owns execution, assessment and selection. This case recomputes those
facts and checks the additional user-journey evidence from issue #479. Observer
receipts are outputs of supervision, never extra instructions sent to Codex.
"""

import hashlib
import json
import math
from pathlib import Path
from statistics import median

from inferrsi.harness import candidates, project
from inferrsi.harness.artifact_primitives import digest, sha256
from inferrsi.harness.optimization import read_records


class EvidenceViolation(ValueError):
    """Complete retained facts contradict an identity or order requirement."""


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def inside(root, name):
    path = root / name
    if Path(name).is_absolute() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Evidence reference escapes its root")
    if any(p.is_symlink() for p in (path, *path.parents) if p.is_relative_to(root)):
        raise ValueError("Evidence reference traverses a symbolic link")
    return path


class Report:
    def __init__(self):
        self.findings = []
        self.rounds = []
        self.results = {}

    def add(self, code, verdict="INCONCLUSIVE", **details):
        self.findings.append({"code": code, "verdict": verdict, **details})

    def document(self):
        verdict = "PASS"
        if self.findings:
            verdict = ("FAIL" if any(f["verdict"] == "FAIL" for f in self.findings)
                       else "INCONCLUSIVE")
        return {"workflow_verdict": verdict, "findings": self.findings,
                "rounds": self.rounds, **self.results}


def reference(root, ref):
    path = inside(root, ref["path"])
    if sha256(path) != ref["sha256"]:
        raise EvidenceViolation("Evidence reference hash mismatch")
    return path


def check_timing_aa(observer_root, observer, preparation, plan, report):
    """Recompute the declared noise estimator from two arms running the baseline."""
    try:
        policy_path = reference(observer_root, preparation["timing_policy"])
        if sha256(policy_path) not in plan["frozen_files"].values():
            raise EvidenceViolation("Timing policy was not frozen")
        policy = read(policy_path)
        if policy.get("adoption_comparator") != "current_best":
            report.add("timing_aa_adoption_comparator_unqualified")
            return
        trace_path = reference(observer_root, observer["timing_aa"])
        if policy["aa_sha256"] != sha256(trace_path):
            raise EvidenceViolation("Timing trace differs from the frozen record")
        if policy["estimator"] != "maximum_absolute_paired_change_pct":
            report.add("timing_aa_estimator_not_supported")
            return
        settings = plan["evaluation_settings"]
        rows = read(trace_path)
        steps = [step for step in project.steps(settings) if step["phase"] != "quality"]
        if [row["step"] for row in rows] != [step["id"] for step in steps]:
            raise EvidenceViolation("Missing or reordered timing A/A steps")
        arms = {"baseline": [], "candidate": []}
        environment = observer["baseline_repeat"]["environment_identity"]
        previous_end = None
        for row, step in zip(rows, steps, strict=True):
            path = reference(observer_root, row["result"])
            raw = read(path)
            if (raw["loaded_source_sha256"] != plan["baseline_sha256"]
                    or raw["workload_sha256"] != preparation["workload"]["sha256"]
                    or raw["effective_scheduler"] != preparation["expected_scheduler"]
                    or raw["environment_identity"] != environment):
                report.add("timing_aa_environment_or_source_unqualified")
                return
            start, end = raw["process"]["started_at"], raw["process"]["finished_at"]
            if not (math.isfinite(start) and math.isfinite(end)
                    and start <= end <= preparation["protocol_frozen_at"]
                    and (previous_end is None or previous_end <= start)):
                raise EvidenceViolation("Timing A/A was not completed in order before freeze")
            previous_end = end
            image_requests(path.parent, raw)
            if step["phase"] == "measurement":
                arms[step["side"]].append(raw["median_ms"])
        pairs = zip(arms["baseline"], arms["candidate"], strict=True)
        noise = max(100 * abs(b - a) / a for a, b in pairs)
        gate = policy["adoption_threshold_pct"]
        if (type(gate) not in (float, int) or not math.isfinite(gate)
                or not math.isclose(noise, policy["observed_noise_pct"], abs_tol=1e-9)
                or gate != settings["min_improvement_pct"] or gate < noise):
            raise EvidenceViolation("Frozen rule disagrees with actual A/A measurements")
        report.results["timing_aa"] = {"paired_groups": len(arms["baseline"]),
                                       "observed_noise_pct": noise, "adoption_threshold_pct": gate}
    except EvidenceViolation:
        report.add("timing_aa_frozen_rule_contradicted", "FAIL")
    except (OSError, ImportError, ValueError, TypeError, KeyError):
        report.add("timing_aa_evidence_unavailable")


def check_preparation(observer_root, observer, plan, state, report):
    try:
        preparation = read(reference(observer_root, observer["preparation"]))
        check_timing_aa(observer_root, observer, preparation, plan, report)
        runspec = preparation["runspec"]
        if (runspec["repository"] != "vllm-project/vllm-omni"
                or runspec["backend"] != "ascend" or runspec["device_class"] != "A2"
                or runspec["device_count"] != 1
                or runspec["model"] != "Qwen-Image-2.1-Turbo"
                or runspec["revision"] != preparation["baseline_revision"]):
            report.add("prepared_environment_does_not_match_case")
        if (len(preparation["baseline_revision"]) != 40
                or not preparation["input_version"]
                or preparation["plan_digest"] != digest(plan)):
            report.add("preparation_does_not_bind_frozen_plan")
        for key in ("client", "version", "model", "configuration_sha256"):
            if not preparation["codex"].get(key):
                report.add("codex_environment_not_pinned", field=key)
        for section, keys in (("inferrsi", ("version", "runtime_digest")),
                              ("a2_skill", ("name", "sha256"))):
            if any(not preparation[section].get(key) for key in keys):
                report.add("prepared_tool_identity_missing", tool=section)
        if preparation["inferrsi"]["runtime_digest"] != digest(plan["runtime_identity"]):
            report.add("prepared_inferrsi_runtime_mismatch")
        for key in ("noninteractive_login", "healthy_exclusive_device", "model_bytes_verified",
                    "baseline_repeat_before_search", "owned_resources_cleaned"):
            if preparation["checks"].get(key) is not True:
                report.add("preparation_or_cleanup_unqualified", check=key)
        if not preparation["protocol_frozen_at"] <= state["rounds"][0]["started_at"]:
            report.add("protocol_not_frozen_before_search", "FAIL")
        # Case identities and prompts are in the Agent's frozen protocol, rather
        # than a hidden replacement task supplied by this test.
        cases_path = reference(observer_root, preparation["quality_cases"])
        cases = read(cases_path)
        if (sorted(c["seed"] for c in cases) != list(range(42, 48))
                or any(not c.get("prompt") for c in cases)):
            report.add("six_frozen_prompt_seed_cases_missing")
        if sha256(cases_path) not in plan["frozen_files"].values():
            report.add("quality_cases_not_frozen_before_search", "FAIL")
        workload_path = reference(observer_root, preparation["workload"])
        workload = read(workload_path)
        required = {"width": 1280, "height": 704, "dtype": "bfloat16", "batch_size": 1,
                    "concurrency": 1, "tensor_parallel_size": 1, "guidance_scale": 1,
                    "num_inference_steps": 8, "timing_scope": "Omni.generate_to_decoded_image"}
        if any(workload.get(key) != value for key, value in required.items()):
            report.add("baseline_workload_not_the_intended_turbo_case")
        if workload.get("requests") != cases:
            report.add("workload_requests_do_not_match_quality_cases")
        if (sha256(workload_path) not in plan["frozen_files"].values()
                or observer["baseline_repeat"]["workload_sha256"] != sha256(workload_path)):
            report.add("workload_identity_not_bound_to_frozen_inputs")
        scheduler = preparation["expected_scheduler"]
        if (scheduler != observer["baseline_repeat"]["effective_scheduler"]
                or scheduler.get("num_steps") != 8 or len(scheduler.get("timesteps", [])) != 8
                or not scheduler.get("sigmas")):
            report.add("baseline_did_not_run_intended_scheduler")
        report.results["input_version"] = preparation["input_version"]
        report.results["baseline_revision"] = preparation["baseline_revision"]
    except EvidenceViolation:
        report.add("preparation_evidence_hash_mismatch", "FAIL")
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        report.add("preparation_evidence_unavailable")


def recompute(directory, settings, execution, identities=None):
    """Use the existing assessor, with an explicit cross-arm ordering check."""
    expected = project.steps(settings)
    actual = execution.get("steps", [])
    if [s.get("id") for s in actual] != [s["id"] for s in expected[:len(actual)]]:
        raise EvidenceViolation("Cross-arm execution order differs from the frozen protocol")
    checks = execution.get("source_checks", [])
    for step, check in zip(actual, checks):
        if check.get("step") != step["id"]:
            raise EvidenceViolation("Source check is bound to a different execution step")
        if identities and check.get("expected") and check.get("actual"):
            if check["expected"] != identities or check["actual"] != identities:
                raise EvidenceViolation("Loaded source differs from retained candidate identity")
    return project.assess(directory, settings, execution)


def select_patch_round(rounds):
    """Even if baseline wins, independently test an actual, quality-valid patch.

    Stable min retains the first attempt on a tie. Eligibility for an improvement
    claim is deliberately separate from suitability for this independent check.
    """
    valid = [r for r in rounds if r["assessment"]["status"] == "completed"
             and r["assessment"].get("quality_passed") is True]
    if not valid:
        raise ValueError("No complete quality-valid Agent candidate to retest")
    return min(valid, key=lambda r: r["assessment"]["score"])


def audit_selection(plan, state, root, report):
    settings = plan["evaluation_settings"]
    best = {"sha256": plan["baseline_sha256"], "score": None, "kind": "baseline"}
    seen = {best["sha256"]}
    recalculated = []
    for record in state["rounds"]:
        directory = inside(root, record["path"])
        execution = read(directory / "execution/execution.json")
        assessment = recompute(directory, settings, execution, {
            "baseline": plan["baseline_sha256"], "candidate": record["candidate_sha256"]})
        if assessment != record["assessment"]:
            report.add("assessment_disagrees_with_raw_evidence", "FAIL",
                       candidate=record["candidate_id"])
        candidate = record["candidate_sha256"]
        if candidate in seen:
            report.add("unchanged_or_repeated_candidate", "FAIL",
                       candidate=record["candidate_id"])
        seen.add(candidate)
        if best["score"] is None and assessment["status"] == "completed":
            best["score"] = assessment["baseline_score"]
        previous = dict(best)
        score = assessment.get("score")
        increment = ((previous["score"] - score) / previous["score"] * 100
                     if score is not None and previous["score"] is not None else None)
        adopted = (assessment["status"] == "completed"
                   and assessment.get("eligible") is True and increment is not None
                   and increment > 0 and increment >= settings["min_improvement_pct"])
        if adopted:
            best = {"sha256": candidate, "score": assessment["score"], "kind": "candidate"}
        if any(record["best_after"].get(key) != value for key, value in best.items()):
            report.add("wrong_adopt_reject_decision", "FAIL", candidate=record["candidate_id"])
        if assessment["status"] == "infrastructure_failure":
            report.add("round_evidence_incomplete", candidate=record["candidate_id"])
        report.rounds.append({
            "candidate": record["candidate_id"], "attempt": record["path"],
            "source_sha256": candidate, "starting_best_sha256": previous["sha256"],
            "decision": "adopt" if adopted else "keep_previous_best",
            "baseline_ms": assessment.get("baseline_score"), "candidate_ms": score,
            "total_improvement_pct": assessment.get("improvement_pct"),
            "incremental_improvement_pct": increment,
            "quality_passed": assessment.get("quality_passed"),
        })
        recalculated.append({**record, "assessment": assessment})
    if any(state["best"].get(key) != value for key, value in best.items()):
        report.add("final_best_chain_mismatch", "FAIL")
    final = state.get("final")
    if final is None:
        report.add("missing_session_final")
    else:
        if final["candidate_sha256"] != best["sha256"]:
            report.add("session_final_retested_wrong_source", "FAIL")
        directory = inside(root, final["path"])
        assessment = recompute(directory, settings, read(directory / "execution/execution.json"), {
            "baseline": plan["baseline_sha256"], "candidate": final["candidate_sha256"]})
        if assessment != final["assessment"]:
            report.add("session_final_assessment_mismatch", "FAIL")
        if assessment["status"] != "completed":
            report.add("session_final_incomplete")
        report.results["session_final"] = metrics(assessment)
    return recalculated


def metrics(assessment):
    before, after = assessment.get("baseline_score"), assessment.get("score")
    return {"baseline_ms": before, "candidate_ms": after,
            "delta_ms": before - after if before and after else None,
            "improvement_pct": assessment.get("improvement_pct"),
            "performance_verdict": assessment["verdict"],
            "quality_passed": assessment.get("quality_passed")}


def check_choices(observer_root, observer, rounds, report):
    """Ordering is mechanical; applicability requires attributable independent review."""
    choices = observer.get("round_choices", {})
    for record, row in zip(rounds, report.rounds):
        choice = choices.get(record["candidate_id"])
        if not choice:
            report.add("missing_pre_edit_choice", candidate=record["candidate_id"])
            continue
        try:
            # The observer exports three host events, each with an ordered sequence
            # and original bytes. File mtimes and retrospective prose do not count.
            events = [read(reference(observer_root, choice[key]))
                      for key in ("plan_event", "first_edit_event", "measurement_event")]
            if (any(not event.get("raw") for event in events)
                    or len({event.get("host_session_id") for event in events}) != 1
                    or not events[0].get("host_session_id")):
                report.add("missing_original_host_choice_events")
            if not (events[0]["sequence"] < events[1]["sequence"] < events[2]["sequence"]):
                report.add("choice_recorded_after_edit_or_measurement", "FAIL")
            declaration = events[0]["choice"]
            if declaration["starting_best_sha256"] != row["starting_best_sha256"]:
                report.add("round_started_from_wrong_best", "FAIL")
            for key in ("alternatives", "chosen_measure", "reason", "expected_effect",
                        "risk", "sources", "feedback_or_initial_analysis"):
                if not declaration.get(key):
                    report.add("incomplete_pre_edit_choice", field=key)
            review = read(reference(observer_root, choice["review"]))
            for ref in review.get("diff_refs", []):
                reference(observer_root, ref)
            if (review.get("independent") is not True or not review.get("reviewer")
                    or not review.get("basis") or not review.get("diff_refs")
                    or review.get("candidate_sha256") != record["candidate_sha256"]):
                report.add("missing_independent_choice_review")
            elif review.get("verdict") == "FAIL":
                report.add("choice_or_patch_not_supported_by_review", "FAIL")
            elif review.get("verdict") != "PASS":
                report.add("choice_rationale_unresolved")
            if review.get("expectation") not in ("supported", "refuted", "inconclusive"):
                report.add("optimization_expectation_not_reviewed")
            row["chosen_measure"] = declaration.get("chosen_measure")
            row["expectation_review"] = review.get("expectation", "unknown")
        except EvidenceViolation:
            report.add("choice_evidence_hash_mismatch", "FAIL")
        except (OSError, ValueError, KeyError, TypeError):
            report.add("choice_evidence_unavailable", candidate=record["candidate_id"])


def image_requests(directory, document):
    """Hash decoded RGBA pixels and recompute the metric from original request times."""
    from PIL import Image

    requests = document["requests"]
    if sorted(r["seed"] for r in requests) != list(range(42, 48)):
        raise ValueError("Expected the six frozen seed cases, exactly once each")
    pixels, times = {}, []
    for request in requests:
        value = request["latency_ms"]
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError("Invalid original request latency")
        with Image.open(inside(directory, request["file"])) as image:
            if image.size != (1280, 704):
                raise ValueError("Wrong generated image dimensions")
            digest = hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest()
        if digest != request["pixel_sha256"]:
            raise EvidenceViolation("PNG bytes disagree with recorded decoded pixels")
        pixels[request["seed"]] = digest
        times.append(value)
    if median(times) != document["median_ms"]:
        raise EvidenceViolation("Metric disagrees with raw request times")
    return pixels


def check_loaded_source(document, expected, report, attempt, step):
    """Compare what the executing worker loaded with the frozen arm identity."""
    actual = document.get("loaded_source_sha256")
    if not actual:
        report.add("loaded_source_identity_missing", attempt=attempt, step=step)
    elif actual != expected:
        report.add("wrong_source_loaded", "FAIL", attempt=attempt, step=step,
                   expected=expected, actual=actual)


def check_outputs(root, plan, state, observer_root, observer, report):
    """No generic similarity threshold; the case freezes exact RGBA equality."""
    try:
        repeat = observer["baseline_repeat"]
        references = [reference(observer_root, ref) for ref in repeat["results"]]
        if len(references) < 2 or len(set(repeat["fresh_process_ids"])) != len(references):
            report.add("baseline_repeat_not_across_fresh_processes")
            return
        baseline_pixels = [image_requests(path.parent, read(path)) for path in references]
        if any(pixels != baseline_pixels[0] for pixels in baseline_pixels[1:]):
            report.add("baseline_pixel_reference_unqualified")
            return
        expected_grid = repeat["effective_scheduler"]
        expected_environment = repeat["environment_identity"]
        expected_workload = repeat["workload_sha256"]
        if (len(set(repeat["source_sha256"])) != 1
                or len(repeat["source_sha256"]) != len(references)):
            report.add("baseline_repeat_source_not_verified")
            return
        if repeat["source_sha256"][0] != plan["baseline_sha256"]:
            report.add("baseline_repeat_wrong_source", "FAIL")
        for index, path in enumerate(references):
            document = read(path)
            check_loaded_source(document, plan["baseline_sha256"], report, "baseline-repeat", index)
            if (document.get("effective_scheduler") != expected_grid
                    or document.get("environment_identity") != expected_environment
                    or document.get("workload_sha256") != expected_workload):
                report.add("baseline_repeat_protocol_mismatch")
                return
        if (max(read(path)["process"]["finished_at"] for path in references)
                >= repeat["search_started_at"]):
            report.add("baseline_repeat_not_before_search")
            return
        if [read(path)["process"]["id"] for path in references] != repeat["fresh_process_ids"]:
            report.add("baseline_repeat_process_receipt_mismatch")
            return
        if state["rounds"] and repeat["search_started_at"] != state["rounds"][0]["started_at"]:
            report.add("baseline_repeat_search_boundary_mismatch")
            return
        if not expected_grid or not expected_environment or not expected_workload:
            report.add("missing_effective_environment_or_scheduler")
            return
        for record in [*state["rounds"], *([state["final"]] if state.get("final") else [])]:
            directory = inside(root, record["path"])
            execution = read(directory / "execution/execution.json")
            candidate_bad = False
            for step in execution["steps"]:
                path = inside(directory, "execution/" + step["id"] + "/result.json")
                document = read(path)
                side = step["id"].rsplit("-", 1)[-1]
                expected_sha = (plan["baseline_sha256"] if side == "baseline"
                                else record["candidate_sha256"])
                check_loaded_source(document, expected_sha, report, record["path"], step["id"])
                if (document.get("status") == "candidate_failure"
                        or (step["id"] == "quality-candidate" and project._value(
                            document, plan["evaluation_settings"]["quality_key"]) is False)):
                    continue
                if document.get("effective_scheduler") != expected_grid:
                    report.add("effective_scheduler_changed", "FAIL" if side == "candidate"
                               and "effective_scheduler" in document else "INCONCLUSIVE")
                if (document.get("environment_identity") != expected_environment
                        or document.get("workload_sha256") != expected_workload):
                    report.add("environment_or_workload_not_comparable")
                pixels = image_requests(path.parent, document)
                if pixels != baseline_pixels[0]:
                    if side == "baseline":
                        report.add("baseline_pixel_reference_unqualified")
                    else:
                        candidate_bad = True
            if candidate_bad and record["assessment"].get("quality_passed") is True:
                report.add("incorrect_candidate_was_accepted_as_quality_valid", "FAIL")
    except ImportError:
        report.add("image_dependency_unavailable")
    except EvidenceViolation:
        report.add("raw_quality_or_timing_evidence_contradicted", "FAIL")
    except (OSError, ValueError, KeyError, TypeError):
        report.add("raw_quality_or_timing_evidence_unavailable")


def check_independent(root, observer, selected, plan, report):
    try:
        directory = inside(root, observer["independent_directory"])
        seal = read(directory / "seal.json")
        submission = read(reference(root, observer["submission"]))
        fields = ("candidate_id", "attempt", "candidate_sha256", "patch_sha256")
        if any(submission[key] != seal[key] for key in fields):
            report.add("independent_retest_differs_from_original_submission", "FAIL")
            return
        if (seal["candidate_id"] != selected["candidate_id"]
                or seal["attempt"] != selected["path"]
                or seal["candidate_sha256"] != selected["candidate_sha256"]
                or seal["baseline_sha256"] != plan["baseline_sha256"]
                or seal["plan_digest"] != digest(plan)):
            report.add("independent_selection_binding_mismatch", "FAIL")
            return
        if (report.results.get("baseline_revision") is not None
                and seal["baseline_revision"] != report.results["baseline_revision"]):
            report.add("independent_git_baseline_revision_mismatch", "FAIL")
            return
        if (sha256(directory / "candidate.patch") != seal["patch_sha256"]
                or candidates.identity(directory / "attempt/candidate")
                != seal["candidate_sha256"]
                or candidates.identity(directory / "frozen/baseline")
                != seal["baseline_sha256"]):
            report.add("independent_sealed_source_changed", "FAIL")
            return
        for name, expected in plan["frozen_files"].items():
            if sha256(inside(directory / "frozen", name)) != expected:
                report.add("independent_protocol_or_baseline_drift", "FAIL")
                return
        receipt = read(directory / "receipt.json")
        if (receipt["seal_sha256"] != sha256(directory / "seal.json")
                or not seal["sealed_at"] < receipt["started_at"]):
            report.add("independent_seal_not_before_measurement", "FAIL")
        execution = read(directory / "attempt/execution/execution.json")
        assessment = recompute(directory / "attempt", plan["evaluation_settings"], execution, {
            "baseline": seal["baseline_sha256"], "candidate": seal["candidate_sha256"]})
        if assessment != receipt["assessment"]:
            report.add("independent_assessment_mismatch", "FAIL")
        if assessment["status"] != "completed":
            report.add("independent_retest_incomplete")
        report.results["independent_patch_retest"] = metrics(assessment)
        # Recheck the independent PNGs/grid too, against the same qualified A/A reference.
        attempt = {"path": "attempt", "assessment": assessment,
                   "candidate_sha256": seal["candidate_sha256"]}
        check_outputs(directory, plan, {"rounds": [], "final": attempt}, root, observer, report)
    except EvidenceViolation:
        report.add("independent_execution_identity_or_order_violation", "FAIL")
    except (OSError, ValueError, KeyError, TypeError):
        report.add("independent_retest_unavailable")


def check_final_reply(root, observer, report, host_reply=None):
    try:
        reply = reference(root, observer["final_reply"]).read_bytes()
        if host_reply is not None and reply != Path(host_reply).read_bytes():
            report.add("observer_reply_differs_from_host_output", "FAIL")
        elif not reply.decode("utf-8-sig").strip():
            report.add("empty_final_reply", "FAIL")
        else:
            report.results["final_reply_sha256"] = hashlib.sha256(reply).hexdigest()
    except EvidenceViolation:
        report.add("final_reply_evidence_hash_mismatch", "FAIL")
    except (OSError, ValueError, KeyError, TypeError):
        report.add("final_reply_evidence_unavailable")


def audit(root, observer_path, *, host_reply=None):
    report = Report()
    observer_path = Path(observer_path)
    try:
        observer = read(observer_path)
        plan, state, _ = read_records(Path(root))
        if (plan["task_source"] != "project"
                or plan["evaluation_settings"]["direction"] != "minimize"
                or plan["evaluation_settings"]["metric_unit"] != "ms"):
            report.add("wrong_case_or_metric", "FAIL")
            return report.document()
        if len(state["rounds"]) < 2:
            if not state["rounds"] and state.get("state") == "completed":
                report.add("completed_without_candidate", "FAIL")
            report.add("multiple_optimization_rounds_not_demonstrated")
        rounds = audit_selection(plan, state, Path(root), report)
        check_preparation(observer_path.parent, observer, plan, state, report)
        check_choices(observer_path.parent, observer, rounds, report)
        check_outputs(Path(root), plan, state, observer_path.parent, observer, report)
        try:
            selected = select_patch_round(rounds)
            check_independent(observer_path.parent, observer, selected, plan, report)
        except ValueError:
            report.add("no_valid_agent_patch_to_retest")
        interventions = observer.get("interventions")
        if interventions is None:
            report.add("user_intervention_record_missing")
        else:
            for event in interventions:
                if (event.get("kind") not in ("assistance", "answer", "approval")
                        or any(key not in event for key in (
                            "stage", "at_seconds", "reason", "action"))):
                    report.add("incomplete_intervention_record")
            assisted = [event for event in interventions if event["kind"] == "assistance"]
            if assisted:
                report.add("observer_intervention_required", "FAIL")
            report.results["completion_mode"] = "assisted" if assisted else "unassisted"
            report.results["first_blocked_step"] = assisted[0]["stage"] if assisted else None
            report.results["interventions"] = interventions
        check_final_reply(observer_path.parent, observer, report, host_reply)
        report.results["scope"] = "offline Omni.generate to decoded image; no service/SLO claim"
    except EvidenceViolation:
        report.add("execution_identity_or_order_violation", "FAIL")
    except (OSError, ValueError, KeyError, TypeError) as error:
        report.add("campaign_or_observer_evidence_unavailable", error_type=type(error).__name__)
    return report.document()
