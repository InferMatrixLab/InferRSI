"""CLI composition for the supported packaged Engine VATS/GVO profile."""

import json
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

from inferrsi.harness import candidates, search_tree
from inferrsi.harness.artifact_primitives import digest
from inferrsi.harness.atomic_json import atomic_write_json
from inferrsi.harness.run_store import RunStore, RunStoreReader
from inferrsi.harness.search_adapter import ArtifactAdapter, Edit
from inferrsi.harness.search_campaign import collect_group, finalize, learn, qualify_root
from inferrsi.harness.search_records import decode
from inferrsi.harness.vats import Settings
from inferrsi.harness.work_control import WorkControl
from inferrsi.model.search_roles import Snapshot

from .search_benchmarks import EngineEvaluator


def add_arguments(commands):
    search = commands.add_parser("search", help="Bounded SpecRSI search and role training")
    actions = search.add_subparsers(dest="search_action", required=True)
    run = actions.add_parser("engine", help="Run a supplied packaged Engine protocol")
    run.add_argument("--session", type=Path, required=True)
    run.add_argument("--store", type=Path, required=True, help="Shared resource/holdout RunStore")
    run.add_argument("--campaign", required=True, help="Unique campaign ID in the shared store")
    run.add_argument("--task", required=True)
    run.add_argument(
        "--edit",
        nargs=4,
        action="append",
        required=True,
        metavar=("TOKEN", "FILE", "BEFORE", "AFTER"),
    )
    run.add_argument(
        "--checkpoint",
        type=Path,
        required=True,
        help="Initial trainable finite-edit role snapshot with provenance",
    )
    run.add_argument("--domain", required=True, help="Caller-owned exclusive measurement domain")
    run.add_argument("--max-seconds", type=int, required=True)
    run.add_argument("--evaluation-seconds", type=int, required=True)
    run.add_argument("--final-reserve-seconds", type=int, required=True)
    run.add_argument("--search-seconds", type=int, required=True)
    run.add_argument("--preparation-seconds", type=int, required=True)
    run.add_argument("--draft-seconds", type=int, required=True)
    run.add_argument("--training-seconds", type=int, required=True)
    run.add_argument("--candidates", type=int, required=True)
    run.add_argument("--depth", type=int, required=True)
    run.add_argument("--attempts", type=int, required=True)
    run.add_argument("--steps", type=int, required=True)
    run.add_argument("--plans", type=int, required=True)
    run.add_argument("--targets", type=int, required=True)
    run.add_argument("--groups", type=int, required=True, help="Independent searches per round")
    run.add_argument("--rounds", type=int, required=True)
    run.add_argument("--learning-rate", type=float, required=True)
    run.add_argument("--seed", type=int, default=0)
    run.add_argument("--mode", choices=("reset", "carry"), default="reset")
    run.add_argument("--final-scope", required=True)
    run.add_argument("--minimum-final-score", type=float, required=True)
    run.add_argument("--python", default=sys.executable)
    run.add_argument("arguments", nargs="*", help="Task protocol arguments after --")
    for action in ("status", "export"):
        read = actions.add_parser(action)
        read.add_argument("--session", type=Path, required=True)
        if action == "export":
            read.add_argument("--output", type=Path, required=True)


def command(args):
    root = args.session.resolve()
    if args.search_action != "engine":
        location = json.loads((root / "control.json").read_text(encoding="utf-8"))
        control = WorkControl(RunStoreReader(location["store"], "speculative"))
        result = control.read(location["campaign"])
        if args.search_action == "export":
            atomic_write_json(args.output, result)
        return result
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
        "minimum_final_score": args.minimum_final_score,
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
        holdout_scope=args.final_scope,
        accept_result=lambda values: all(
            v["objective"] >= args.minimum_final_score for v in values
        ),
    )
    return control.read(campaign)
