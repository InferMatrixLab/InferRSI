"""CLI composition for the supported packaged Engine VATS/GVO profile."""

import json
import time
from dataclasses import asdict, replace

from inferrsi.apps.workflows.search_roles import Snapshot
from inferrsi.harness import candidates, search_tree
from inferrsi.harness.records import RunStore, RunStoreReader
from inferrsi.harness.records.artifact_primitives import digest
from inferrsi.harness.records.atomic_json import atomic_write_json
from inferrsi.harness.search_adapter import ArtifactAdapter, Edit
from inferrsi.harness.search_campaign import (
    FinalAcceptance,
    collect_group,
    finalize,
    learn,
    qualify_root,
)
from inferrsi.harness.search_records import decode
from inferrsi.harness.vats import Settings
from inferrsi.harness.work_control import WorkControl


def command(args):
    root = args.session.resolve()
    if args.search_action != "engine":
        location = json.loads((root / "control.json").read_text(encoding="utf-8"))
        control = WorkControl(RunStoreReader(location["store"], "speculative"))
        result = control.read(location["campaign"])
        if args.search_action == "export":
            atomic_write_json(args.output, result)
        return result
    from .search_benchmarks import EngineEvaluator

    acceptance = FinalAcceptance(minimum_objective=args.minimum_final_score)
    if root.exists():
        raise ValueError("Use a new session directory; status/export never restart work")
    if args.groups < 2 or args.rounds < 1:
        raise ValueError("GVO needs at least two independent searches and one training round")
    if args.final_reserve_seconds < args.evaluation_seconds:
        raise ValueError("Final reserve must cover the full evaluation cap")
    required = (
        args.evaluation_seconds
        + args.final_reserve_seconds
        + (args.groups * args.rounds + 2) * args.search_seconds
        + args.rounds * args.training_seconds
    )
    if args.max_seconds < required:
        raise ValueError(
            "Campaign cap must fund qualification, all search groups, training and final"
        )
    snapshot = Snapshot(**json.loads(args.checkpoint.read_text(encoding="utf-8")))
    if (
        len(snapshot.drafter) != len(args.edit)
        or len(snapshot.policy) != 8
        or len(snapshot.scorer) != 8
    ):
        raise ValueError(
            "Checkpoint needs one Drafter weight per edit and eight Policy/Scorer weights"
        )
    settings = Settings(
        args.steps,
        1,
        args.depth,
        args.targets,
        args.candidates,
        args.plans,
        args.preparation_seconds * 1000,
        args.draft_seconds * 1000,
        args.search_seconds * 1000,
    )
    root.mkdir(parents=True)
    evaluator = EngineEvaluator(
        args.task, root / "frozen", arguments=args.arguments, python=args.python
    )
    adapter = ArtifactAdapter(
        root / "artifacts",
        (Edit(*raw) for raw in args.edit),
        {"evaluation": args.evaluation_seconds * 1000},
        evaluator,
        domain=args.domain,
    )
    source = root / "initial"
    source.mkdir()
    candidates.retain(root / "frozen/baseline.py", source / "candidate.py")
    node = adapter.import_root(source, snapshot=digest(snapshot.document()), context={})
    control = WorkControl(RunStore(args.store.resolve(), "speculative"))
    campaign = args.campaign
    atomic_write_json(
        root / "control.json", {"store": str(args.store.resolve()), "campaign": campaign}
    )
    specification = {
        "adapter": adapter.identity,
        "settings": asdict(settings),
        "groups": args.groups,
        "rounds": args.rounds,
        "mode": args.mode,
        "learning_rate": args.learning_rate,
        "minimum_final_score": acceptance.minimum_objective,
        "initial_snapshot": snapshot.document(),
    }
    contract = search_tree.Contract(
        "qualification",
        search_tree.Context(
            digest(specification),
            digest(specification),
            evaluator.identity,
            args.domain,
            args.task,
            node.artifact_digest,
            evaluator.identity,
        ),
        digest(snapshot.document()),
        ("evaluation",),
        "evaluation",
        "maximize",
        args.candidates,
        args.depth,
        args.attempts,
    )
    control.create(
        campaign,
        specification,
        {"searches": {}, "checkpoint": snapshot.document(), "stable": asdict(node)},
        cap_ms=args.max_seconds * 1000,
        final_reserve_ms=args.final_reserve_seconds * 1000,
        deadline=time.time() + args.max_seconds,
    )
    initial = qualify_root(control, campaign, adapter, node, contract)
    trained = learn(
        control,
        campaign,
        adapter,
        initial,
        snapshot,
        settings,
        rounds=args.rounds,
        group_size=args.groups,
        training_cap_ms=args.training_seconds * 1000,
        learning_rate=args.learning_rate,
        seed=args.seed,
        mode=args.mode,
    )
    # A fresh post-update search demonstrates the new frozen checkpoint. Selection
    # is development-only, and never uses final results to choose another version.
    records = collect_group(
        control,
        campaign,
        adapter,
        initial,
        trained,
        settings,
        group_id="deployment",
        size=2,
        seed=args.seed,
        collect=False,
    )
    states = [decode(record["tree"]) for record in records]
    selected_state = max(states, key=search_tree.verified_gain)
    selected = replace(search_tree.accept(selected_state), parent_id=None)
    finalize(
        control,
        campaign,
        adapter,
        selected,
        deployment_search=selected_state.contract.search_id,
        holdout_scope=args.final_scope,
        acceptance=acceptance,
    )
    return control.read(campaign)
