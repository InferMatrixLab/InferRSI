"""Public CLI projection for self-contained Records in an installed generation."""

from __future__ import annotations

import json
import sys
from argparse import Namespace

from ...knowledge.atomic_generation import InstalledGeneration
from ...knowledge.atomic_reader import AtomicReader, GroupDelivery
from ...knowledge.decision_cards import DecisionSource
from ...knowledge.knowledge_find import Document, _record_documents, launcher
from ...knowledge.knowledge_operations import Bundle, _json, _sources


class InstalledRecords:
    def __init__(self, source: InstalledGeneration, reader: AtomicReader) -> None:
        self.source = source
        self.reader = reader

    def supports(self, ref: str) -> bool:
        entry = self.source.compositions.get(ref)
        if not ref.startswith("package:") or entry is None or entry["kind"] != "knowledge":
            return False
        _, bundle = self.source.read_resolved(ref, revision=entry["revision"])
        return (
            bundle.metadata.get("entrypoint") == "record.json"
            and set(bundle.content) == {"record.json"}
            and not bundle.metadata.get("skill_documents")
            and not bundle.dependencies
            and bundle.metadata.get("required_resources") == ["record.json"]
            and bundle.metadata.get("index_type") != "packaged-skill"
        )

    def _selection(self, ref: str, revision: str, layer: str) -> GroupDelivery:
        return self.reader.read_selection(
            ref,
            revision=revision,
            layer=layer,
            max_bytes=sys.maxsize,
            context={},
        )

    def _material(self, ref: str, revision: str) -> dict | None:
        delivery = self._selection(ref, revision, "L3")
        if delivery.receipt["status"] != "delivered":
            return None
        _, bundle = self.source.read_resolved(ref, revision=revision)
        if len(delivery.bodies) != 1:
            raise ValueError(f"Installed Record material does not match its selection: {ref}")
        record = json.loads(delivery.bodies[0])
        if not isinstance(record, dict) or record.get("id") != ref.removeprefix("package:"):
            raise ValueError(f"Invalid installed Record identity: {ref}")
        if _json(record) != _json(json.loads(bundle.content["record.json"])):
            raise ValueError(f"Installed Record material does not match its selection: {ref}")
        return record

    def document(self, ref: str, revision: str) -> tuple[Document, int] | None:
        record = self._material(ref, revision)
        if record is None:
            return None
        documents = _record_documents((record,))
        return (documents[0], len(_json(record))) if documents else None

    def decision_source(self, ref: str, revision: str) -> DecisionSource | None:
        delivery = self._selection(ref, revision, "L1")
        if delivery.receipt["status"] != "delivered":
            return None
        fields: dict = {}
        claims: dict[int, object] = {}
        for atom, body in zip(delivery.receipt["delivered"], delivery.bodies, strict=True):
            _, bundle = self.source.read_resolved(atom["ref"], revision=atom["revision"])
            pointers = bundle.metadata["atom"]["source_pointers"]
            if pointers == [""] and len(delivery.bodies) == 1:
                fields = json.loads(body)
            elif len(pointers) == 1 and pointers[0].startswith("/claims/"):
                index = int(pointers[0].removeprefix("/claims/"))
                if index in claims or "claims" in fields:
                    raise ValueError(f"Invalid installed Record claim pointers: {ref}")
                claims[index] = json.loads(body)
            else:
                fragment = json.loads(b"{" + body + b"}")
                actual = ["/" + key.replace("~", "~0").replace("/", "~1") for key in fragment]
                if (
                    actual != pointers
                    or fields.keys() & fragment.keys()
                    or (claims and "claims" in fragment)
                ):
                    raise ValueError(f"Invalid installed Record field pointers: {ref}")
                fields.update(fragment)
        if claims:
            if set(claims) != set(range(len(claims))):
                raise ValueError(f"Incomplete installed Record claim pointers: {ref}")
            fields["claims"] = [claims[index] for index in range(len(claims))]
        if not isinstance(fields, dict):
            raise ValueError(f"Invalid installed Record decision fields: {ref}")
        return DecisionSource(ref, revision, "record", "record.json", "record.json", fields)

    def find_view(
        self,
        document: Document,
        score: float,
        query_tokens: list[str],
        decision_cards: bool,
        material_bytes: int,
    ) -> dict:
        ref = document.qualified
        revision = self.source.compositions[ref]["revision"]
        args = ("read", ref, "--revision", revision, "--material", "--omit-resources")
        view = document.view(score=score, query_tokens=query_tokens, read_args=args)
        view["knowledge_generation"] = self.source.generation
        view["next_read_content_bytes"] = material_bytes
        if decision_cards:
            source = self.decision_source(ref, revision)
            if source is None:
                view["decision_card"] = {"status": "unavailable", "reason": "read_denied"}
            else:
                projected = source.project(finding=None, max_bytes=None, compact=False)
                card_args = ("read", ref, "--revision", revision, "--layer", "L1")
                view["decision_card"] = {
                    "ref": ref,
                    "revision": revision,
                    "status": "available",
                    "card_bytes": projected["card_bytes"],
                    "read_args": list(card_args),
                    "open_argv": [*launcher(), *card_args],
                }
        return view

    def read(self, args: Namespace) -> dict:
        ref, revision = args.id, args.revision
        if args.layer == "L1":
            return self._decision(args)
        if args.compact or args.finding is not None or args.max_bytes is not None:
            raise ValueError("--compact, --finding and --max-bytes require --layer L1")
        if args.resource not in (None, "record.json"):
            raise ValueError(f"Resource not found in {ref}: {args.resource}")
        record = self._material(ref, revision)
        if record is None:
            raise ValueError(f"Revision unavailable in this snapshot: {ref} at {revision}")
        content = _json(record)
        metadata = {
            "id": record["id"],
            "kind": "knowledge",
            "entrypoint": "record.json",
            "origin": record.get("origin", ["external"]),
            "sources": _sources(record["sources"]),
            "applicability": record.get("applicability", {}),
            "state": record["status"],
            "limitations": record.get("limitations", [])
            + [
                "Imported guidance; reading does not validate or execute it.",
                "Historical revisions require the matching installed snapshot or a retained store.",
            ],
            "attribution": record["sources"],
            "verification": record["verification"],
            "tier": record.get("tier", "contribution"),
            "repo": record["repo"],
            "backend": record["backend"],
            "scenario": record["scenario"],
            "title": record["title"],
            "skill_documents": record.get("skill_documents", {}),
            "required_resources": ["record.json"],
        }
        bundle = Bundle(metadata, {"record.json": content}, {})
        view = bundle.view(material=args.material and args.resource is None)
        view["revision"] = revision
        if args.resource is not None:
            view["content"] = bundle.content[args.resource].decode("utf-8")
            view["content_resource"] = args.resource
        if args.omit_resources:
            view.pop("resources", None)
            view.pop("required_resources", None)
        view["ref"] = ref
        return view

    def _decision(self, args: Namespace) -> dict:
        ref, revision = args.id, args.revision
        if args.material or args.resource is not None or args.omit_resources:
            raise ValueError(
                "--layer L1 cannot be combined with --material, --resource or --omit-resources"
            )
        if args.finding is not None:
            raise ValueError("--finding applies to case selections")
        if revision != self.source.compositions[ref]["revision"]:
            return {
                "ref": ref,
                "revision": revision,
                "status": "unavailable_revision",
                "detail": f"Revision unavailable in this snapshot: {ref} at {revision}",
            }
        source = self.decision_source(ref, revision)
        if source is None:
            raise ValueError(f"Installed Record decision denied: {ref}")
        result = source.project(finding=None, max_bytes=args.max_bytes, compact=args.compact)
        read_args = ["read", ref, "--revision", revision]
        if args.installed_library:
            read_args.append("--installed-library")
        if "full_read" in result:
            result["full_read_args"] = [*read_args, "--layer", "L1"]
        if "body_resource" in result:
            result["next_read_args"] = [*read_args, "--omit-resources", "--resource", "record.json"]
        return result
