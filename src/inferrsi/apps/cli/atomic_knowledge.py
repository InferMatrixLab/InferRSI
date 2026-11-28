"""Public find and read against an explicitly pinned installed generation."""

from __future__ import annotations

import base64
import json
import os
import re
import sys
from argparse import Namespace
from pathlib import Path, PurePosixPath

from ...knowledge.atomic_generation import InstalledGeneration
from ...knowledge.atomic_reader import AtomicReader, GroupDelivery
from ...knowledge.catalog import _skill_search_source
from ...knowledge.decision_cards import DecisionSource
from ...knowledge.knowledge_find import Corpus, Document, launcher


class AtomicKnowledgeCLI:
    def __init__(self, installed: InstalledGeneration) -> None:
        self.generation = installed.generation
        self.catalog = installed.compositions
        self.source = installed
        self._navigation_bytes: dict[str, int] = {}
        # The public CLI supplies no caller grants. Reader still checks every
        # composition, route and atom with an empty applicability context.
        self.reader = AtomicReader(installed, permits=lambda _pin, operation: operation == "read")

    @classmethod
    def installed(cls) -> AtomicKnowledgeCLI | None:
        expected = os.environ.get("INFERRSI_KNOWLEDGE_GENERATION")
        if expected is None:
            return None
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", expected):
            raise ValueError("INFERRSI_KNOWLEDGE_GENERATION requires a full SHA-256 generation")
        root = Path(__file__).resolve().parents[2] / "_atomic"
        return cls(InstalledGeneration(root, expected=expected))

    def corpus(self, kinds: tuple[str, ...]) -> Corpus:
        documents = []
        for reference, entry in self.catalog.items():
            kind = {"case": "case", "skill": "skill", "knowledge": "record"}.get(entry["kind"])
            if kind not in kinds:
                continue
            revision = entry["revision"]
            delivery = self.reader.read_selection(
                reference, revision=revision, layer="L0", max_bytes=sys.maxsize, context={},
            )
            if delivery.receipt["status"] != "delivered":
                continue
            self._navigation_bytes[reference] = delivery.receipt["body_bytes"]
            _, bundle = self.source.read_resolved(reference, revision=revision)
            view = bundle.view()
            identity = view["id"]
            title = view.get("title", identity)
            summary = view.get("summary", "")
            body = "\n".join(item.decode("utf-8", errors="replace") for item in delivery.bodies)
            documents.append(Document(
                identity=identity, qualified=reference, kind=kind, state=view["state"],
                path=view.get("entrypoint"), title=title, summary=summary,
                fields={
                    "title": f"{title} {identity.replace('.', ' ').replace('-', ' ')}",
                    "summary": summary,
                    "body": body,
                },
                applicability=view.get("applicability"),
                limitations=tuple(view.get("limitations", ())),
                source_location="installed", locally_verified=True,
            ))
        return Corpus(documents)

    def find_view(
        self, document: Document, score: float, query_tokens: list[str], decision_cards: bool,
    ) -> dict:
        ref = document.qualified
        revision = self.catalog[ref]["revision"]
        view = document.view(
            score=score, query_tokens=query_tokens, read_args=_read_args(ref, revision, "L0"),
        )
        view["knowledge_generation"] = self.generation
        view["next_read_content_bytes"] = self._navigation_bytes[ref]
        if decision_cards:
            decision = self.reader.read_selection(
                ref, revision=revision, layer="L1", max_bytes=sys.maxsize, context={},
            )
            if decision.receipt["status"] == "delivered":
                args = _read_args(ref, revision, "L1")
                entrypoint = self._skill_entrypoint(ref, revision)
                card_bytes = decision.receipt["body_bytes"]
                if entrypoint:
                    card_bytes = _skill_decision(ref, revision, entrypoint, decision).project()["card_bytes"]
                view["decision_card"] = {
                    "ref": ref, "revision": revision, "status": "available",
                    "card_bytes": card_bytes,
                    "read_args": list(args), "open_argv": [*launcher(), *args],
                }
            else:
                view["decision_card"] = {
                    "status": "unavailable", "reason": decision.receipt["status"],
                }
        return view

    def _skill_entrypoint(self, ref: str, revision: str) -> str | None:
        entry = self.catalog[ref]
        if entry["kind"] != "skill" or entry["revision"] != revision:
            return None
        _, bundle = self.source.read_resolved(ref, revision=revision)
        skill = bundle.metadata["composition"].get("skill") or {}
        if skill.get("directory_entry"):
            return bundle.view()["entrypoint"]
        return None

    def read(self, args: Namespace) -> dict:
        if args.skill_root is not None or args.store is not None:
            raise ValueError("A pinned installed generation is the only local read source")
        if args.resource is not None or args.compact or args.material or args.omit_resources:
            raise ValueError("Pinned generation reads accept --layer, --finding and --max-bytes")
        if not args.revision:
            raise ValueError("Pinned generation reads require --revision from find")
        if args.id not in self.catalog:
            raise ValueError("Read requires a public composition reference from find")
        layer = args.layer or "L0"
        entrypoint = self._skill_entrypoint(args.id, args.revision) if layer == "L1" else None
        budget = sys.maxsize if args.max_bytes is None else args.max_bytes
        delivery = self.reader.read_selection(
            args.id, revision=args.revision, layer=layer, finding=args.finding,
            max_bytes=sys.maxsize if entrypoint and budget >= 0 else budget, context={},
        )
        if entrypoint and delivery.receipt["status"] == "delivered":
            card = _skill_decision(args.id, args.revision, entrypoint, delivery)
            return {**card.project(max_bytes=args.max_bytes), "knowledge_generation": self.generation}
        return {
            "knowledge_generation": self.generation,
            "receipt": delivery.receipt,
            "bodies": [_encode_body(body) for body in delivery.bodies],
        }


def _skill_decision(ref: str, revision: str, entrypoint: str, delivery: GroupDelivery) -> DecisionSource:
    if len(delivery.bodies) != 1:
        raise ValueError("A directory skill requires one authorized L1 source")
    resource = delivery.receipt["delivered"][0]["source_path"].removeprefix(
        "src/inferrsi/knowledge/data/skill_library/"
    )
    if resource == str(PurePosixPath(entrypoint).with_name("metadata.json")):
        record = json.loads(delivery.bodies[0])
    elif resource == entrypoint:
        _, record = _skill_search_source(delivery.bodies[0].decode("utf-8"))
    else:
        raise ValueError("The authorized L1 source does not match the skill entrypoint")
    if not isinstance(record, dict):
        raise ValueError("The authorized L1 source has no decision metadata")
    return DecisionSource(ref, revision, "skill", resource, entrypoint, record)


def _read_args(reference: str, revision: str, layer: str) -> tuple[str, ...]:
    return ("read", reference, "--revision", revision, "--layer", layer)


def _encode_body(body: bytes) -> dict[str, str]:
    try:
        return {"text": body.decode("utf-8")}
    except UnicodeDecodeError:
        return {"base64": base64.b64encode(body).decode("ascii")}
