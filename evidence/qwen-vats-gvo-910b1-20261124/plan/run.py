"""Run the frozen single-worker Qwen diagnostic inside an allocated NPU environment."""

import argparse
import json
import math
import shutil
import time
from dataclasses import asdict, replace
from pathlib import Path

from inferrsi.apps.workflows.search_benchmarks import EngineEvaluator
from inferrsi.apps.workflows.search_roles import Snapshot
from inferrsi.harness.artifact_primitives import digest, sha256
from inferrsi.harness.atomic_json import atomic_write_json
from inferrsi.harness.manager.search import search_tree
from inferrsi.harness.manager.search.search_adapter import ArtifactAdapter, Edit
from inferrsi.harness.manager.search.search_campaign import (
    FinalAcceptance,
    finalize,
    import_qualified_root,
    learn,
    qualify_root,
)
from inferrsi.harness.manager.search.search_records import decode
from inferrsi.harness.manager.search.vats import Search, Settings
from inferrsi.harness.manager.search.work_control import WorkControl
from inferrsi.harness.run_store import RunStore

HERE = Path(__file__).resolve().parent


def serial(evaluator, sources, plan, root_score, directory):
    selected, best = "root", root_score
    evaluations = []
    deadline = time.time() + plan["settings"]["search_ms"] / 1000
    for index, name in enumerate(plan["serial_order"]):
        result = evaluator.evaluate(
            sources / name,
            "evaluation",
            directory / str(index),
            min(deadline, time.time() + plan["check_ms"] / 1000),
        )
        evaluations.append({"candidate": name, **result})
        if result["cleanup_verified"] is not True or result["verdict"] == "INCONCLUSIVE":
            raise ValueError(f"Incomplete serial measurement for {name}")
        if result["verdict"] == "PASS" and result["objective"] > best:
            selected, best = name, result["objective"]
    atomic_write_json(directory / "selection.json", {"candidate": selected, "objective": best})
    final = evaluator.evaluate(
        sources / selected, "evaluation", directory / "final", time.time() + plan["check_ms"] / 1000
    )
    return selected, best, final, evaluations


def campaign(control, name, spec, checkpoint, node, cap, reserve):
    control.create(
        name,
        spec,
        {"searches": {}, "checkpoint": checkpoint.document(), "stable": asdict(node)},
        cap_ms=cap,
        final_reserve_ms=reserve,
        deadline=time.time() + cap / 1000,
    )


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    plan = json.loads((HERE / "plan.json").read_text())
    shutil.copyfile(__file__, output / "driver.py")
    summary = {
        "driver_sha256": sha256(output / "driver.py"),
        "blocks": [
            {"seed": seed, "arm": arm, "status": "not_run", "final_score": None}
            for seed, arms in plan["blocks"]
            for arm in arms
        ],
    }
    atomic_write_json(output / "summary.json", summary)
    edits = [Edit(*args) for args in json.loads((HERE / "edits.json").read_text())]
    frozen = Snapshot(**plan["checkpoint"])
    settings = Settings(**plan["settings"])
    cap = plan["check_ms"]
    evaluator = EngineEvaluator(plan["task"], output / "frozen", arguments=plan["sampling"])
    adapter = ArtifactAdapter(
        output / "artifacts", edits, {"evaluation": cap}, evaluator, domain="allocated-single-npu"
    )
    control = WorkControl(RunStore(output / "store", "speculative"))
    source = output / "sources"
    baseline = evaluator.frozen / "baseline.py"
    if sha256(baseline) != plan["source_baseline_sha256"]:
        raise ValueError("Baseline differs from the frozen edit catalog")
    contents = {"root": baseline.read_text()}
    for edit in edits:
        for name, text in list(contents.items()):
            if text.count(edit.before) != 1:
                raise ValueError("Expected one exact edit location")
            child = edit.token if name == "root" else name + "+" + edit.token
            contents[child] = text.replace(edit.before, edit.after, 1)
    names = {}
    for name, text in contents.items():
        path = source / name / "candidate.py"
        path.parent.mkdir(parents=True)
        path.write_text(text)
        names[sha256(path)] = name
    node = adapter.import_root(source / "root", snapshot=digest(frozen.document()), context={})
    spec = {"plan": plan, "edits_digest": sha256(HERE / "edits.json"), "adapter": adapter.identity}
    context = search_tree.Context(
        digest(spec),
        digest(plan),
        evaluator.identity,
        adapter.domain,
        plan["task"],
        node.artifact_digest,
        evaluator.identity,
    )
    contract = search_tree.Contract(
        "qualification",
        context,
        digest(frozen.document()),
        ("evaluation",),
        "evaluation",
        "maximize",
        plan["max_candidates_including_root"],
        plan["max_depth"],
        plan["max_attempts_including_root"],
    )
    training = plan["train"]
    train_cap = (
        2 * cap
        + training["rounds"]
        * (settings.search_ms * training["group_size"] + training["training_cap_ms"])
        + 60000
    )
    campaign(control, "training", spec, frozen, node, train_cap, cap)
    started = time.monotonic()
    root = qualify_root(control, "training", adapter, node, contract)
    root_seconds = time.monotonic() - started
    root_score = search_tree.evidence(root, root.root_id)["evaluation"].objective
    print("Root qualified. Starting frozen collection and GVO update.", flush=True)
    started = time.monotonic()
    trained = learn(control, "training", adapter, root, frozen, settings, **training)
    train_seconds = time.monotonic() - started
    training_state = control.read("training")["state"]
    summary.update(
        {
            "root_score": root_score,
            "root_seconds": root_seconds,
            "training_seconds": train_seconds,
            "training": training_state["training"],
            "training_candidate_checks": sum(
                len(r["tree"]["attempts"]) - 1 for r in training_state["searches"].values()
            ),
            "initial": frozen.document(),
            "trained": trained.document(),
        }
    )
    atomic_write_json(output / "summary.json", summary)
    for row in summary["blocks"]:
        arm, seed = row["arm"], row["seed"]
        name = f"{arm}-{seed}"
        row["status"] = "incomplete"
        atomic_write_json(output / "summary.json", summary)
        print(f"Starting {name}", flush=True)
        started = time.monotonic()
        try:
            if arm == "serial":
                selected, best, final, evaluations = serial(
                    evaluator,
                    source,
                    plan,
                    root_score,
                    output / name,
                )
                row.update(
                    selected=selected,
                    search_score=best,
                    candidate_checks=len(evaluations),
                    final_verdict=final["verdict"],
                )
            else:
                snapshot = trained if arm == "trained" else frozen
                campaign(control, name, spec, snapshot, node, settings.search_ms + cap + 30000, cap)
                initial = import_qualified_root(
                    root,
                    replace(
                        contract, search_id=name, improver_snapshot=digest(snapshot.document())
                    ),
                )
                search = Search(control, name, name, snapshot, settings, adapter)
                search.start(initial, seed=seed, collect=False)
                record = search.run()
                state = decode(record["tree"])
                winner = search_tree.accept(state)
                selected = names[sha256(adapter.path(winner) / "candidate.py")]
                best = search_tree.evidence(state, winner.candidate_id)["evaluation"].objective
                row.update(
                    selected=selected, search_score=best, candidate_checks=len(state.attempts) - 1
                )
                final_record = finalize(
                    control,
                    name,
                    adapter,
                    replace(winner, parent_id=None),
                    holdout_scope=name,
                    acceptance=FinalAcceptance(),
                )
                row.update(final_verdict=final_record["verdict"], promoted=final_record["promoted"])
                if (
                    final_record["verdict"] != "PASS"
                    or final_record["promoted"] is not True
                    or final_record["candidate"] != winner.candidate_id
                ):
                    raise ValueError(
                        f"Search final did not promote the selected candidate for {name}"
                    )
                (final,) = final_record["results"]
            if final["verdict"] != "PASS" or final["cleanup_verified"] is not True:
                raise ValueError(f"Incomplete final for {name}")
            row.update(status="complete", final_score=final["objective"])
        finally:
            row["online_seconds"] = time.monotonic() - started
            atomic_write_json(output / "summary.json", summary)
        print(json.dumps(row), flush=True)
    for numerator, denominator in (
        ("trained", "frozen"),
        ("trained", "serial"),
        ("frozen", "serial"),
    ):
        rows = {(r["seed"], r["arm"]): r["final_score"] for r in summary["blocks"]}
        ratios = [rows[seed, numerator] / rows[seed, denominator] for seed, _ in plan["blocks"]]
        summary[f"{numerator}_over_{denominator}"] = {
            "paired_ratios": ratios,
            "geomean": math.exp(sum(map(math.log, ratios)) / len(ratios)),
        }
    atomic_write_json(output / "summary.json", summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output", type=Path, help="Fresh directory for all receipts and measurements"
    )
    run(parser.parse_args().output.resolve())
