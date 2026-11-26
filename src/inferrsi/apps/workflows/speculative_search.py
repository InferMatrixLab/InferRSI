"""Connect the Engine CLI, role checkpoint and packaged evaluator to Harness."""

import json

from inferrsi.apps.workflows.search_roles import Snapshot
from inferrsi.harness.manager import EngineSearchPlan, read_engine_search, run_engine_search
from inferrsi.harness.records.atomic_json import atomic_write_json


def command(args):
    if args.search_action != "engine":
        result = read_engine_search(args.session)
        if args.search_action == "export":
            atomic_write_json(args.output, result)
        return result

    from .search_benchmarks import EngineEvaluator

    plan = EngineSearchPlan(
        campaign=args.campaign,
        task=args.task,
        domain=args.domain,
        edits=tuple(tuple(edit) for edit in args.edit),
        max_seconds=args.max_seconds,
        evaluation_seconds=args.evaluation_seconds,
        final_reserve_seconds=args.final_reserve_seconds,
        search_seconds=args.search_seconds,
        preparation_seconds=args.preparation_seconds,
        draft_seconds=args.draft_seconds,
        training_seconds=args.training_seconds,
        candidates=args.candidates,
        depth=args.depth,
        attempts=args.attempts,
        steps=args.steps,
        plans=args.plans,
        targets=args.targets,
        groups=args.groups,
        rounds=args.rounds,
        learning_rate=args.learning_rate,
        seed=args.seed,
        mode=args.mode,
        final_scope=args.final_scope,
        minimum_final_score=args.minimum_final_score,
    )
    return run_engine_search(
        plan,
        session=args.session,
        store=args.store,
        load_snapshot=lambda: Snapshot(**json.loads(args.checkpoint.read_text(encoding="utf-8"))),
        prepare_evaluator=lambda frozen: EngineEvaluator(
            args.task, frozen, arguments=args.arguments, python=args.python
        ),
    )
