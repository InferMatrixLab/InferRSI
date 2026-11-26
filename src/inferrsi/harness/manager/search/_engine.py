"""Admission, candidate selection and final validation for a bounded Engine search."""

import json
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path


@dataclass(frozen=True, kw_only=True)
class EngineSearchPlan:
    """Inputs frozen by the caller before starting an independent search campaign."""

    campaign: str
    task: str
    domain: str
    edits: tuple[tuple[str, str, str, str], ...]
    max_seconds: int
    evaluation_seconds: int
    final_reserve_seconds: int
    search_seconds: int
    preparation_seconds: int
    draft_seconds: int
    training_seconds: int
    candidates: int
    depth: int
    attempts: int
    steps: int
    plans: int
    targets: int
    groups: int
    rounds: int
    learning_rate: float
    seed: int
    mode: str
    final_scope: str
    minimum_final_score: int | float

    def __post_init__(self):
        for field in (
            "max_seconds", "evaluation_seconds", "final_reserve_seconds", "search_seconds",
            "preparation_seconds", "draft_seconds", "training_seconds", "candidates",
            "depth", "attempts", "steps", "plans", "targets", "groups", "rounds",
        ):
            value = getattr(self, field)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{field} must be a positive integer")


def read_engine_search(session: Path) -> dict:
    """Read the durable campaign snapshot through a read-only store."""
    from inferrsi.harness.run_store import RunStoreReader

    from .work_control import WorkControl

    location = json.loads((session.resolve() / "control.json").read_text(encoding="utf-8"))
    control = WorkControl(RunStoreReader(location["store"], "speculative"))
    return control.read(location["campaign"])


def run_engine_search(
    plan: EngineSearchPlan, *, session: Path, store: Path, load_snapshot, prepare_evaluator
) -> dict:
    """Admit the plan, train and select using development evidence, then verify the winner.

    Apps supplies a snapshot loader and an evaluator factory. The factory receives the
    frozen-input directory and retains the baseline there after budget admission.
    """
    from inferrsi.harness import candidates
    from inferrsi.harness.artifact_primitives import digest
    from inferrsi.harness.atomic_json import atomic_write_json
    from inferrsi.harness.run_store import RunStore

    from . import search_tree
    from .search_adapter import ArtifactAdapter, Edit
    from .search_campaign import (
        FinalAcceptance,
        collect_group,
        finalize,
        learn,
        qualify_root,
    )
    from .search_records import decode
    from .vats import Settings
    from .work_control import WorkControl

    root = session.resolve()
    store = store.resolve()
    acceptance = FinalAcceptance(minimum_objective=plan.minimum_final_score)
    if root.exists():
        raise ValueError("Use a new session directory; status/export never restart work")
    if plan.groups < 2:
        raise ValueError("GVO needs at least two independent searches and one training round")
    if plan.final_reserve_seconds < plan.evaluation_seconds:
        raise ValueError("Final reserve must cover the full evaluation cap")
    required = (
        plan.evaluation_seconds
        + plan.final_reserve_seconds
        + (plan.groups * plan.rounds + 2) * plan.search_seconds
        + plan.rounds * plan.training_seconds
    )
    if plan.max_seconds < required:
        raise ValueError(
            "Campaign cap must fund qualification, all search groups, training and final"
        )
    snapshot = load_snapshot()
    if (
        len(snapshot.drafter) != len(plan.edits)
        or len(snapshot.policy) != 8
        or len(snapshot.scorer) != 8
    ):
        raise ValueError(
            "Checkpoint needs one Drafter weight per edit and eight Policy/Scorer weights"
        )
    settings = Settings(
        plan.steps,
        1,
        plan.depth,
        plan.targets,
        plan.candidates,
        plan.plans,
        plan.preparation_seconds * 1000,
        plan.draft_seconds * 1000,
        plan.search_seconds * 1000,
    )
    root.mkdir(parents=True)
    evaluator = prepare_evaluator(root / "frozen")
    adapter = ArtifactAdapter(
        root / "artifacts",
        (Edit(*raw) for raw in plan.edits),
        {"evaluation": plan.evaluation_seconds * 1000},
        evaluator,
        domain=plan.domain,
    )
    source = root / "initial"
    source.mkdir()
    candidates.retain(root / "frozen/baseline.py", source / "candidate.py")
    node = adapter.import_root(source, snapshot=digest(snapshot.document()), context={})
    control = WorkControl(RunStore(store, "speculative"))
    campaign = plan.campaign
    atomic_write_json(
        root / "control.json", {"store": str(store), "campaign": campaign}
    )
    specification = {
        "adapter": adapter.identity,
        "settings": asdict(settings),
        "groups": plan.groups,
        "rounds": plan.rounds,
        "mode": plan.mode,
        "learning_rate": plan.learning_rate,
        "minimum_final_score": acceptance.minimum_objective,
        "initial_snapshot": snapshot.document(),
    }
    contract = search_tree.Contract(
        "qualification",
        search_tree.Context(
            digest(specification),
            digest(specification),
            evaluator.identity,
            plan.domain,
            plan.task,
            node.artifact_digest,
            evaluator.identity,
        ),
        digest(snapshot.document()),
        ("evaluation",),
        "evaluation",
        "maximize",
        plan.candidates,
        plan.depth,
        plan.attempts,
    )
    control.create(
        campaign,
        specification,
        {"searches": {}, "checkpoint": snapshot.document(), "stable": asdict(node)},
        cap_ms=plan.max_seconds * 1000,
        final_reserve_ms=plan.final_reserve_seconds * 1000,
        deadline=time.time() + plan.max_seconds,
    )
    initial = qualify_root(control, campaign, adapter, node, contract)
    trained = learn(
        control,
        campaign,
        adapter,
        initial,
        snapshot,
        settings,
        rounds=plan.rounds,
        group_size=plan.groups,
        training_cap_ms=plan.training_seconds * 1000,
        learning_rate=plan.learning_rate,
        seed=plan.seed,
        mode=plan.mode,
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
        seed=plan.seed,
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
        holdout_scope=plan.final_scope,
        acceptance=acceptance,
    )
    return control.read(campaign)
