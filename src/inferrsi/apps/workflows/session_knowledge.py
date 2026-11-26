"""Find and read knowledge as separate, attributable operations in a campaign."""

from __future__ import annotations

import json
import shutil
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from inferrsi import __version__
from inferrsi.harness import optimization, project_service
from inferrsi.harness.atomic_json import atomic_write_json
from inferrsi.harness.optimization_session import _runtime_identity
from inferrsi.harness.records.evidence import bounded_record_bytes, sanitized_text
from inferrsi.harness.records.knowledge_capture import (
    MAX_CONTEXT_CAPTURE_BYTES,
    capture_campaign,
    scoped_response,
    store_capture,
)
from inferrsi.knowledge._skill_selection import FIND_RELEVANCE, skill_procedure
from inferrsi.knowledge.catalog import (
    SCENARIO_ALIASES,
    _catalog_corpus,
    knowledge_records,
)
from inferrsi.knowledge.channels import no_match_across_sources
from inferrsi.knowledge.context_projection import assemble_context_text
from inferrsi.knowledge.knowledge_find import rank
from inferrsi.knowledge.knowledge_operations import service_body, service_resources
from inferrsi.knowledge.ranking_policy import DEFAULT_RANKING_POLICY, managed_ranking_policy

from ..integrations.external_channels import round_provider
from .knowledge import read_continuation, read_page

# Only portable Find data goes in an immutable capture. The installed launcher and
# session directory belong to this invocation, not the material's identity.
_HIT = (
    "material_ref", "revision", "body_resource", "material_read_args", "id", "authority", "kind",
    "path", "title", "summary", "state", "score", "source", "source_location", "applicability",
    "limitations", "limitations_withheld", "findings", "findings_withheld",
    "next_read_content_bytes", "matched", "unreadable",
    "repo", "backend", "scenario", "tier", "sources", "locally_verified",
)


@contextmanager
def _campaign(root):
    manifest = capture_campaign(root, "find")
    with optimization._locked(root):
        if not manifest.get("managed_optimization"):
            yield manifest, {}, None, None, DEFAULT_RANKING_POLICY
            return
        plan, state = optimization._load(root)
        service = plan.get("evaluation_mode") == "service_reuse"
        active = state if not service else {
            **state, "deadline": optimization._service_deadline(state),
            "state": "active" if state["state"] == "needs_baseline" else state["state"],
        }
        number = optimization._knowledge_round(plan, active)
        binding = optimization._context_diagnosis(plan, state)
        if not service and plan["runtime_identity"] != _runtime_identity():
            raise ValueError("Optimization runtime changed, use its frozen runtime to resume")
        policy = optimization.resolve_frozen_ranking(plan, managed_ranking_policy)
        yield manifest, plan, state, (number, binding), policy


def _save(root, campaign, state, step, *, context_id, action, request, items, display, contexts=()):
    number, binding = step or (None, None)
    service = campaign.get("evaluation_mode") == "service_reuse"
    captured_by = f"inferrsi {action} {__version__}"
    selection = {"method": FIND_RELEVANCE, "ranking_applied": action == "find",
                 "state": "applied" if action == "find" else "explicit_ids",
                 "ranking_policy": request["ranking_policy"]}
    observation = {"schema_version": 1, "entrypoint": action, "calls": [action],
                   "request": request, "selection": selection, "display": display,
                   "counts": {"matched": display.get("matched"), "returned": len(items)},
                   "items": [{k: row[k] for k in ("ref", "revision") if k in row} for row in items]}
    facts = {
        "request": request, "selection": selection, "items": items, "omissions": [],
        "context_omissions": [], "context_budget": None,
        "context_bytes_used": sum(c["content_bytes"] for c in contexts),
        "contexts": list(contexts), "retrieval": observation,
    }
    kind = "knowledge_search" if action == "find" else "delivered_context"
    path = f"knowledge/{context_id}.json"
    reference = {"path": path, "kind": kind}
    if service:
        document = {**facts, "kind": "service_knowledge_context", "context_id": context_id,
                    "captured_by": captured_by, "prepared_not_consumed": True}
        if action == "find":
            document["source_snapshot"] = f"knowledge/sources/{context_id}"
        if binding:
            document["diagnosis_binding"] = binding
        project_service.no_fingerprints(document)
        (root / "knowledge").mkdir(exist_ok=True)
        atomic_write_json(project_service.safe_path(root, path), document)
    else:
        target, digest = store_capture(
            root, campaign_id=campaign["campaign_id"], context_id=context_id,
            captured_by=captured_by, diagnosis_binding=binding,
            assembled_text=assemble_context_text(list(contexts)),
            **facts,
        )
        reference["sha256"] = digest
        document = json.loads(target.read_bytes())
    if state is not None:
        retained = {**reference, "round": number}
        if binding:
            retained["diagnosis_id"] = binding["diagnosis_id"]
        if action == "read":
            retained["search_ref"] = request["search_ref"]
        state["contexts"].append(retained)
    return reference, document


def _retain_service_sources(root, context_id, selections):
    """Publish only complete, byte-consistent source sets before their search receipt."""
    relative = f"knowledge/sources/{context_id}"
    destination = project_service.safe_path(root, relative)
    temporary = destination.with_name("." + context_id)
    temporary.mkdir(parents=True)
    try:
        for record, document in selections:
            resources = service_resources(record)
            primary = record.get("skill_documents", {}).get("original") or "record.json"
            if document.kind == "skill":
                if (primary != "data/skill_library/" + document.path
                        or record["skill_metadata"]["name"] != document.identity
                        or record["backend"] != document.backend):
                    raise ValueError(
                        "Knowledge ownership changed while finding material; run Find again"
                    )
                raw = resources[primary].decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
                body, _ = skill_procedure(primary, raw.encode("utf-8"))
                if body.decode("utf-8") != document.fields["body"]:
                    raise ValueError("Knowledge changed while finding material; run Find again")
            directory = temporary / record["id"]
            for path, content in resources.items():
                target = project_service.safe_path(directory, path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                target.chmod(target.stat().st_mode & ~0o222)
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _service_find(args, policy, backend, root, context_id):
    if not args.query:
        raise ValueError("Service-reuse Find requires a question")
    kinds = {item.strip() for item in args.kinds.split(",") if item.strip()}
    if not kinds or kinds - {"case", "skill", "record"}:
        raise ValueError("--kinds takes a subset of case,skill,record")
    records = knowledge_records(file_fingerprints=False)
    scenario = SCENARIO_ALIASES.get(args.scenario, args.scenario)

    def matches(record):
        skill = record.get("index_type") == "packaged-skill"
        declared = record.get("scenario", "")
        applicable = (not scenario or declared == scenario
                      or (skill and declared == "skills.discovery")
                      or (declared.endswith(".*") and scenario.startswith(declared[:-1])))
        return (("skill" if skill else "record") in kinds
                and (not backend or record["backend"] in ("common", backend))
                and (not args.tier or record.get("tier", "contribution") == args.tier)
                and (not args.repo_type or record["repo"] == args.repo_type)
                and applicable)

    records = [record for record in records if matches(record)]
    corpus, records = _catalog_corpus(records, file_fingerprints=False)
    _, _, ranked = rank(args.query, corpus, policy)
    items = []
    selections = []
    for score, _, index, components in ranked[:args.limit]:
        record = records[index]
        selections.append((record, corpus.documents[index]))
        ref = "package:" + record["id"]
        revision = record["sources"][0]["commit"]
        path = record.get("skill_documents", {}).get("original") or "record.json"
        items.append({
            "id": record["id"], "authority": "package", "title": record["title"],
            "kind": "skill" if record.get("index_type") == "packaged-skill" else "record",
            "repo": record["repo"], "tier": record.get("tier", "contribution"),
            "backend": record["backend"], "scenario": record["scenario"],
            "score": round(score, 2), "material_ref": ref, "revision": revision,
            "body_resource": path, "material_read_args": ["read", ref, "--revision", revision],
            **({"matched": components} if args.explain else {}),
        })
    _retain_service_sources(root, context_id, selections)
    return {"query": args.query, "matched": len(ranked), "no_match": not ranked, "items": items,
            "ranking_policy": policy.configuration(), "sources": ["package"]}


def _service_read(root, search, hit, resource):
    snapshot = f"knowledge/sources/{search['context_id']}"
    if search.get("source_snapshot") != snapshot:
        raise ValueError("This Find has no retained source bytes; run Find again before reading")
    source_root = project_service.safe_path(root, snapshot + "/" + hit["id"])
    record = project_service.read(project_service.safe_path(source_root, "record.json"))
    if record.get("id") != hit["id"] or record["sources"][0]["commit"] != hit["revision"]:
        raise ValueError("The retained source does not match this Find")
    primary = hit["body_resource"]
    path, data, locator = service_body(record, resource, source_root=source_root)
    ref, revision = hit["material_ref"], hit["revision"]
    selected = {"path": path, "role": "core" if path == primary else "reference",
                "content": data.decode("utf-8"), **locator}
    context = {"ref": ref, "revision": revision, "resources": [selected],
               "content_bytes": len(data), "omissions": [], "sources": record["sources"]}
    view = {"ref": ref, "id": hit["id"], "revision": revision, "entrypoint": primary,
            "content_resource": path, "content": selected["content"], "sources": record["sources"]}
    if resource is not None and path != resource:
        view["body_resource"] = primary
    if locator:
        view["content_view"] = locator
    return view, context


def find_in_session(args, find_local):
    root = args.session.resolve()
    if args.limit < 1:
        raise ValueError("--limit must be positive")
    if (args.decision_cards or args.input or args.external_source is not None
            or args.platform
            or args.searchspace_coordinate or args.show_searchspace_coordinates
            or args.external_limit is not None or args.external_timeout != 8.0):
        raise ValueError("Session Find provides body reads and uses its frozen external source")
    with _campaign(root) as (campaign, plan, state, step, policy):
        if state is not None and (args.skill_root or args.store or args.revisions):
            raise ValueError("Managed Find uses the session's installed corpus")
        query = args.query
        backend = args.backend or campaign.get("backend")
        settings = plan.get("external_knowledge")
        external_enabled = (settings and not args.no_external
                            and (backend is None or backend == settings["backend"]))
        if external_enabled:
            if step[0] is None:
                raise ValueError("Round budget consumed, run independent final evaluation")
            query = sanitized_text(query, "", limit=None)
            args.query = query
        service = campaign.get("evaluation_mode") == "service_reuse"
        context_id = "find-" + uuid4().hex
        result = (_service_find(args, policy, backend, root, context_id) if service else
                  find_local(args, ranking_policy=policy, backend=backend, local_only=True))
        request = {"query": query, "relevance": query, "relevance_method": FIND_RELEVANCE,
                   "ranking_policy": result["ranking_policy"],
                   "backend": backend, "scenario": args.scenario, "limit": args.limit,
                   "kinds": args.kinds, "repo": args.repo_type,
                   "tier": args.tier, "sources": result["sources"]}
        if args.no_external:
            request["external_source"] = "none"
        if args.revisions:
            request["revisions"] = dict(pin.split("=", 1) for pin in args.revisions)
        if plan:
            optimization._check_context_ranking(plan, {"request": request})
        items = [{key: hit[key] for key in _HIT if key in hit} for hit in result["items"]]
        # Some Find hits (for instance unavailable sources) have no material to open.
        for item in items:
            item["ref"] = item.get("material_ref") or f"{item['authority']}:{item['id']}"
            argv = list(item.get("material_read_args", ()))
            for flag in ("--skill-root", "--store"):
                if flag in argv:
                    argv[argv.index(flag) + 1] = flag[2:].upper().replace("-", "_")
            if argv:
                item["material_read_args"] = argv
        external = None
        if external_enabled:
            remaining = optimization._knowledge_time(plan, state)
            external = (round_provider(plan).search(query, settings=settings, limit=args.limit,
                                                   timeout=remaining) if remaining > 0 else
                        {"state": "timeout", "items": [], "count": 0})
            result["no_match"] = no_match_across_sources(result["matched"], [external])
        display = {key: value for key, value in result.items()
                   if key not in ("items", "external", "searchspace_source")}
        reference, document = _save(
            root, campaign, state, step, context_id=context_id,
            action="find", request=request, items=items, display=display,
        )
        response = scoped_response(document, reference, str(args.session),
                                   skill_root=args.skill_root, store=args.store)
        if external is not None:
            number = step[0]
            search = {**external, **settings, "context_ref": reference["path"]}
            extra = optimization._store_knowledge(root, "external_search", number, search)
            state["contexts"].append(extra)
            prefix = (["benchmarks", "session"] if plan["task_source"] == "benchmark"
                      else ["campaign"])
            read = [*prefix, "knowledge-read", "--session", str(args.session),
                    "--search-ref", extra["path"], "--locator"]
            response["external"] = {**search, "reference": extra, "items": [
                {**hit, "read_args": [*read, hit["locator"]]} for hit in search["items"]
            ]}
        if state is not None:
            atomic_write_json(root / "state.json", state)
        return response


def _open_search(root, campaign, state, step, location):
    path = Path(location)
    if path.parent.as_posix() != "knowledge" or path.suffix != ".json":
        raise ValueError("Supply a search reference from this campaign")
    if state is not None:
        number, binding = step
        ref = next((entry for entry in state["contexts"] if entry["path"] == location
                    and entry["kind"] == "knowledge_search" and entry.get("round") == number
                    and entry.get("diagnosis_id") == (binding or {}).get("diagnosis_id")), None)
        if ref is None:
            raise ValueError("Supply a Find reference from the current round and diagnosis")
        search = (project_service.read(project_service.safe_path(root, location))
                  if campaign.get("evaluation_mode") == "service_reuse" else
                  optimization._read_context(root, ref))
    else:
        from .campaign import verify_capture

        raw, _ = bounded_record_bytes(root, location, MAX_CONTEXT_CAPTURE_BYTES)
        search = verify_capture(raw)[0] if raw else None
        if not search or search["campaign_id"] != campaign["campaign_id"]:
            raise ValueError("Supply a verified Find reference from this campaign")
    if search.get("retrieval", {}).get("entrypoint") != "find":
        raise ValueError("The reference must identify a Find result")
    return search


def read_in_session(args, read_hit):
    if not args.search_ref:
        raise ValueError("A session read requires the --search-ref returned by Find")
    if (args.layer or args.finding or args.compact or args.max_bytes is not None):
        raise ValueError("Session Find supports a pinned body or --resource read")
    root = args.session.resolve()
    with _campaign(root) as (campaign, _, state, step, _):
        search = _open_search(root, campaign, state, step, args.search_ref)
        hit = next((item for item in search["items"] if item.get("material_ref") == args.id), None)
        if not hit or not hit.get("revision") or hit["revision"] != args.revision:
            raise ValueError("Read requires a hit and revision returned by this Find")
        argv = list(hit["material_read_args"])
        for flag, value in (("--skill-root", args.skill_root), ("--store", args.store)):
            if (flag in argv) != (value is not None):
                raise ValueError("Use the source arguments returned by the original Find")
            if value is not None:
                argv[argv.index(flag) + 1] = str(value)
        if args.installed_library != ("--installed-library" in argv):
            raise ValueError("Use the source arguments returned by the original Find")
        resource = args.resource
        service = campaign.get("evaluation_mode") == "service_reuse"
        view, context = (_service_read(root, search, hit, resource) if service else
                         read_hit({**hit, "material_read_args": argv}, resource=resource))
        delivered, = context["resources"]
        read_page(view, args.byte_range,
                  source_hash=delivered.get("source_sha256", delivered.get("sha256")),
                  source_ranges=delivered.get("source_byte_ranges"))
        if "content_range" in view:
            delivered.update(content=view["content"], content_range=view["content_range"])
            delivered.update(view.get("content_view", {}))
            context["content_bytes"] = len(view["content"].encode("utf-8"))
        path = view["content_resource"]
        request = {**search["request"], "search_ref": args.search_ref, "resource": path}
        if args.byte_range is not None:
            request["byte_range"] = args.byte_range
        request.pop("context_bytes", None)  # A manual campaign may reopen an earlier Find.
        display = {key: view[key] for key in (
            "id", "ref", "revision", "kind", "title", "entrypoint", "content_resource",
            "body_resource", "content_view", "content_range", "next_byte_range",
            "sources", "limitations", "applicability",
        ) if key in view}
        if continuation := read_continuation(args, view):
            for flag, replacement in (("--session", "."), ("--skill-root", "SKILL_ROOT"),
                                      ("--store", "STORE")):
                if flag in continuation:
                    continuation[continuation.index(flag) + 1] = replacement
            display["next_read_args"] = continuation
        material = {key: hit[key] for key in ("ref", "revision", "title", "kind") if key in hit}
        prefix = "read-" + search["context_id"][:64] + "-"
        reference, doc = _save(
            root, campaign, state, step, context_id=prefix + uuid4().hex, action="read",
            request=request, items=[material], display=display, contexts=[context],
        )
        if state is not None:
            atomic_write_json(root / "state.json", state)
        return scoped_response(doc, reference, str(args.session),
                               skill_root=args.skill_root, store=args.store)
