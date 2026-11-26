"""Verify bytes returned by an injected Reader and retain the selected delivery or refusal."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from inferrsi import __version__

from . import knowledge_capture

_REFUSALS = {"over_budget", "unavailable_revision", "permission_denied",
             "not_applicable", "conflict"}


def _verify_receipt(receipt, bodies, request):
    selection = receipt["selection"]
    if any(selection[key] != request[key] for key in ("ref", "revision", "layer", "finding")):
        raise ValueError("Reader receipt belongs to a different selection")
    records = receipt["delivered"]
    if not isinstance(records, list) or len(records) != len(bodies):
        raise ValueError("Reader receipt must enumerate exactly the delivered bodies")
    status = receipt["status"]
    if status == "delivered":
        if not records:
            raise ValueError("Successful delivery requires at least one atom")
    elif status not in _REFUSALS or records:
        raise ValueError("Invalid Reader refusal or nonempty refused delivery")
    seen = set()
    for body, record in zip(bodies, records):
        pin = (record["ref"], record["revision"])
        if pin in seen:
            raise ValueError("An atom may occur only once in a delivery")
        seen.add(pin)
        if not isinstance(body, bytes):
            raise ValueError("The Reader must supply the original bytes")
        digest = hashlib.sha256(body).hexdigest()
        if (record["sha256"] != digest or record["source_sha256"] != digest
                or type(record["bytes"]) is not int or record["bytes"] != len(body)):
            raise ValueError("Delivered bytes differ from the Reader receipt")
        span = record["source_byte_range"]
        if (not isinstance(span, list) or len(span) != 2
                or not all(type(offset) is int for offset in span)
                or span[0] < 0 or span[1] - span[0] != len(body)):
            raise ValueError("Source range differs from the delivered bytes")
    total = sum(map(len, bodies))
    if (type(receipt["body_bytes"]) is not int or receipt["body_bytes"] != total
            or total > request["max_bytes"]):
        raise ValueError("Invalid delivered byte count or budget")


def _resource(body, record):
    resource = {"path": record["source_path"], "sha256": record["sha256"]}
    try:
        resource["content"] = body.decode("utf-8")
    except UnicodeDecodeError:
        resource.update(content=base64.b64encode(body).decode("ascii"), content_encoding="base64")
    return resource


def verify_stored(document):
    """Check a retained atomic receipt against the resources a caller can actually recover."""
    request, receipt = document["request"], document["selection"]
    records, contexts = receipt["delivered"], document["contexts"]
    if len(records) != len(contexts) or len(records) != len(document["items"]):
        raise ValueError("Atomic capture does not match the delivered atom count")
    bodies = []
    for record, context, item in zip(records, contexts, document["items"]):
        identity = {"ref": record["ref"], "revision": record["revision"]}
        if item != identity or any(context[key] != value for key, value in identity.items()):
            raise ValueError("Retained atom does not match its receipt")
        resource, = context["resources"]
        if resource["path"] != record["source_path"] or resource["sha256"] != record["sha256"]:
            raise ValueError("Retained resource differs from its receipt")
        bodies.append(knowledge_capture.resource_bytes(resource))
    _verify_receipt(receipt, bodies, request)
    if (document["context_bytes_used"] != receipt["body_bytes"]
            or document["context_budget"] != request["max_bytes"]):
        raise ValueError("Atomic capture accounting differs from its request")


def retain_selection(root: Path, *, reader, context_id, reference, revision, layer, max_bytes,
                     context, assemble_text, finding=None, diagnosis_binding=None,
                     ranking_policy=None):
    campaign = knowledge_capture.capture_campaign(root, context_id)
    request = {"mode": "pinned_selection", "ref": reference, "revision": revision, "layer": layer,
               "finding": finding, "max_bytes": max_bytes, "context": dict(context),
               "operations": ["read", "retain"]}
    if ranking_policy is not None:
        # Session provenance. This operation reopens an explicit pin without ranking it again.
        request["ranking_policy"] = ranking_policy
    delivery = reader.read_selection(reference, revision=revision, layer=layer, finding=finding,
                                     max_bytes=max_bytes, context=context, operations=("retain",))
    receipt, bodies = delivery.receipt, delivery.bodies
    _verify_receipt(receipt, bodies, request)
    items = [{"ref": record["ref"], "revision": record["revision"]}
             for record in receipt["delivered"]]
    contexts = [{**item, "resources": [_resource(body, record)], "omissions": []}
                for item, body, record in zip(items, bodies, receipt["delivered"])]
    return knowledge_capture.store_capture(
        root, campaign_id=campaign["campaign_id"], context_id=context_id, request=request,
        selection=receipt, items=items, omissions=receipt.get("omissions", []),
        context_omissions=[],
        context_budget=max_bytes, context_bytes_used=receipt["body_bytes"], contexts=contexts,
        assembled_text=assemble_text(contexts), diagnosis_binding=diagnosis_binding,
        captured_by=f"inferrsi pinned knowledge read {__version__}",
    )
