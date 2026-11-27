"""Adapt CLI options to a shared Harness knowledge operation."""

from inferrsi.harness.optimization import knowledge_operation
from inferrsi.harness.records.knowledge_capture import scoped_response
from inferrsi.knowledge.context_projection import assemble_context_text
from inferrsi.knowledge.ranking_policy import DEFAULT_RANKING_POLICY, managed_ranking_policy

from ..integrations.external_channels import round_provider


def _operate(args, reader, action, options):
    return knowledge_operation(
        args.session, reader, action, options, default_policy=DEFAULT_RANKING_POLICY,
        ranking_policy_for=managed_ranking_policy,
        assemble_context=assemble_context_text, external_provider_for=round_provider,
    )


def _response(args, saved):
    view = scoped_response(
        saved["context"], saved["reference"], str(args.session),
        skill_root=args.skill_root, store=args.store,
    )
    if "external" in saved:
        external = saved["external"]
        prefix = ["benchmarks", "session"] if saved["task_source"] == "benchmark" else ["campaign"]
        read = [*prefix, "knowledge-read", "--session", str(args.session),
                "--search-ref", external["reference"]["path"], "--locator"]
        view["external"] = {**external, "items": [
            {**hit, "read_args": [*read, hit["locator"]]} for hit in external["items"]
        ]}
    return view


def find_in_session(args, reader, options):
    return _response(args, _operate(args, reader, "find", options))


def read_in_session(args, reader):
    if not args.search_ref:
        raise ValueError("A session read requires the --search-ref returned by Find")
    if args.layer or args.finding or args.compact or args.max_bytes is not None:
        raise ValueError("Session Find supports a pinned body or --resource read")
    source_flags = [
        flag for flag, value in (
            ("--skill-root", args.skill_root), ("--store", args.store),
            ("--installed-library", args.installed_library),
        ) if value
    ]
    options = {
        "search_ref": args.search_ref, "ref": args.id, "revision": args.revision,
        "resource": args.resource, "byte_range": args.byte_range, "source_flags": source_flags,
    }
    return _response(args, _operate(args, reader, "read", options))
