"""Adapt CLI options to a shared Harness knowledge operation."""

from inferrsi.harness.manager import ReadSessionKnowledge, knowledge_operation, run_session
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
        read = ["read", "--session", str(args.session),
                "--search-ref", external["reference"]["path"], "--locator"]
        view["external"] = {**external, "items": [
            {**hit, "read_args": [*read, hit["locator"]]} for hit in external["items"]
        ]}
    return view


def find_in_session(args, reader, options):
    return _response(args, _operate(args, reader, "find", options))


def _read_external(args, source_flags, *, locator, page):
    if not locator:
        raise ValueError("External session Read requires --locator")
    if (source_flags or any(value is not None for value in (
            args.id, args.revision, args.resource, args.byte_range,
            args.layer, args.finding, args.max_bytes,
    )) or args.compact or args.material or args.omit_resources):
        raise ValueError("Use only --session, --search-ref, --locator and --page for external Read")
    if page is not None and (type(page) is not int or page < 1):
        raise ValueError("CANNBot page must be a positive integer")

    from inferrsi.harness.executor import assess_packaged_task

    return run_session(
        ReadSessionKnowledge(session=args.session, search_ref=args.search_ref,
                             locator=locator, page=1 if page is None else page),
        assess_packaged=assess_packaged_task, ranking_policy_for=managed_ranking_policy,
        external_provider_for=round_provider,
    )


def read_in_session(args, reader):
    if not args.search_ref:
        raise ValueError("A session read requires the --search-ref returned by Find")
    source_flags = [
        flag for flag, value in (
            ("--skill-root", args.skill_root), ("--store", args.store),
            ("--installed-library", args.installed_library),
        ) if value
    ]
    locator, page = getattr(args, "locator", None), getattr(args, "page", None)
    if locator is not None or page is not None:
        return _read_external(args, source_flags, locator=locator, page=page)
    if args.id is None:
        raise ValueError("A local session Read requires a knowledge ID")
    if args.layer or args.finding or args.compact or args.max_bytes is not None:
        raise ValueError("Session Find supports a pinned body or --resource read")
    options = {
        "search_ref": args.search_ref, "ref": args.id, "revision": args.revision,
        "resource": args.resource, "byte_range": args.byte_range, "source_flags": source_flags,
    }
    return _response(args, _operate(args, reader, "read", options))
