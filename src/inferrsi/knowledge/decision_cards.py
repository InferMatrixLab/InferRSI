"""L1 decision views of a single verified bundle. No external reads or inference."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from ._skill_selection import indexed_skill
from .catalog import _skill_search_source
from .knowledge_operations import Bundle, _json


@dataclass(frozen=True)
class DecisionSource:
    ref: str
    revision: str
    kind: str
    resource: str | None
    body: str
    record: dict

    @classmethod
    def from_bundle(cls, ref: str, bundle: Bundle, view: dict) -> DecisionSource:
        """Project only the resource bytes covered by the supplied Bundle view."""
        body = view["entrypoint"]
        kind = view["kind"]
        resource = body
        if kind == "knowledge":
            kind = "record"
            resource = body if ref.startswith("package:") else None
            # Package records expose their authored schema in record.json.
            # Store entries declare metadata on bundles with arbitrary bodies.
            record = json.loads(bundle.content[body]) if resource else bundle.metadata
            if not isinstance(record, dict):
                raise ValueError("Record decision source must be an object")
            if resource and record.get("index_type") == "packaged-skill":
                body, _, _ = indexed_skill(
                    record, {**view, "authority": ref.partition(":")[0]}, bundle.content,
                )
                kind = "skill"
        if kind == "skill":
            resource = body
            _, record = _skill_search_source(bundle.content[body].decode("utf-8"))
            sidecar = str(PurePosixPath(body).with_name("metadata.json"))
            if sidecar in bundle.content:
                if record is not None:
                    raise ValueError("Skill declares metadata in two resources")
                resource = sidecar
                record = json.loads(bundle.content[sidecar])
            if record is None:
                record = {}
        elif kind == "case":
            resource = "case.json"
            if resource not in bundle.content:
                raise ValueError("Case decision cards require the original case.json")
            record = json.loads(bundle.content[resource])
        if not isinstance(record, dict):
            raise ValueError("Decision source must be a JSON object")
        return cls(ref, view["revision"], kind, resource, body, record)

    def _findings(self) -> list[dict]:
        findings = self.record.get("findings", [])
        if not isinstance(findings, list) or any(not isinstance(f, dict) for f in findings):
            raise ValueError("Case findings must be an array of objects")
        return findings

    def finding_locator(self, index: int) -> str:
        findings = self._findings()
        identity = findings[index].get("id")
        if isinstance(identity, str) and identity.strip():
            if sum(f.get("id") == identity for f in findings) == 1:
                return f"id:{identity}"
        return f"case.json#/findings/{index}"

    def finding(self, selector: str) -> tuple[int, dict]:
        findings = self._findings()
        if selector.startswith("id:") and selector[3:].strip():
            indices = [i for i, f in enumerate(findings) if f.get("id") == selector[3:]]
            if len(indices) == 1:
                index = indices[0]
                return index, findings[index]
        match = re.fullmatch(r"case\.json#/findings/(0|[1-9][0-9]*)", selector)
        if match and (index := int(match[1])) < len(findings):
            return index, findings[index]
        raise ValueError(f"Unknown or ambiguous finding at {self.revision}: {selector}")

    def project(
        self, *, finding: str | None = None, max_bytes: int | None = None, compact: bool = False,
    ) -> dict:
        if max_bytes is not None and (type(max_bytes) is not int or max_bytes < 0):
            raise ValueError("L1 max_bytes must be a nonnegative integer")
        if (self.kind == "case") != (finding is not None):
            raise ValueError("Select one --finding for a Case L1 read; omit it for other kinds")

        record = self.record
        atom = {"kind": self.kind, "resource": self.resource}
        declared = {key: record[key] for key in (
            "origin", "sources", "provenance_readsets", "source_pins", "attribution",
            "status", "state", "verification", "empirical_validation", "limitations",
            "applicability", "recommendations", "validation_plan", "claims", "downstream_impact",
        ) if key in record}
        applies = record.get("applicability")
        conditions = applies if isinstance(applies, dict) else {}
        refusal_or_limits = {key: conditions[key] for key in ("refusal_point", "failure_modes")
                             if conditions.get(key)}
        if record.get("limitations"):
            refusal_or_limits["limitations"] = record["limitations"]
        decision = {
            "applicability": applies,
            "prerequisites": conditions.get("prerequisites") or conditions.get("conditions"),
            "refusal_or_limits": refusal_or_limits,
            "recommendation": record.get("recommendations"),
            "validation": record.get("validation_plan"),
        }
        if finding is not None:
            index, item = self.finding(finding)
            atom.update(kind="case_finding", selector=self.finding_locator(index),
                        pointer=f"case.json#/findings/{index}")
            declared["finding"] = item
            decision.update(
                prerequisites=item.get("bounds") or decision["prerequisites"]
                or (applies if isinstance(applies, list) else None),
                recommendation={
                    k: item[k] for k in ("direction", "outcome", "reason") if k in item
                },
                validation=item.get("revisit_when"),
            )
        missing = [name for name, value in decision.items() if not value]
        if finding is not None:
            missing.extend(key for key in ("direction", "outcome", "reason") if not item.get(key))
        card = {
            "schema_version": 1, "layer": "L1", "ref": self.ref, "revision": self.revision,
            "atom": atom, "decision": decision, "declared": declared,
            "status": "partial" if missing else "complete", "missing_fields": missing,
        }
        full_read = None
        if compact:
            # Preserve the entire decision and its source's actual evidence vocabulary.
            # Lists of sources, claims and duplicate raw fields stay on the full pin.
            context = ("origin", "status", "state", "downstream_impact")
            retained = {key: declared[key] for key in context if key in declared}
            evidence = {key: declared[key] for key in ("verification", "empirical_validation")
                        if key in declared}
            omitted = sorted(declared.keys() - retained.keys() - evidence.keys())
            card.update(view="compact", declared=retained, validation_evidence=evidence or None,
                        omitted_declared_fields=omitted)
            full_read = {"reference": self.ref, "revision": self.revision}
            if finding is not None:
                full_read["finding"] = atom["selector"]
                # Keep finding-specific scope and any additional authored qualifiers.
                card["finding_context"] = {key: value for key, value in item.items() if key not in (
                    "direction", "outcome", "reason", "revisit_when", "bounds", "id", "keywords",
                )}
        size = len(_json(card))
        result = {"ref": self.ref, "revision": self.revision, "card_bytes": size,
                  "body_resource": self.body, "source_resource": self.resource}
        if full_read is not None:
            result["full_read"] = full_read
        if max_bytes is not None and size > max_bytes:
            return {**result, "status": "over_budget", "max_bytes": max_bytes,
                    "missing_fields": missing}
        return {**result, "status": card["status"], "card": card}
