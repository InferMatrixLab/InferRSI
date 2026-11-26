"""Pinned input for ordinary and managed Reader contract tests."""

import hashlib
import json

from inferrsi.knowledge.atomic_reader import AtomPin
from inferrsi.knowledge.knowledge_operations import Bundle


def metadata(identity, kind, entrypoint, source):
    return {"id": identity, "kind": kind, "entrypoint": entrypoint, "state": "candidate",
            "applicability": {}, "limitations": [], "sources": [source],
            "attribution": "Synthetic Reader contract fixture"}


def composition(nodes, routes, *, findings=None):
    path = "case.json" if findings is not None else "navigation.json"
    data = json.dumps({"findings": findings} if findings is not None else {},
                      ensure_ascii=False).encode()
    source = {"type": "fixture", "sha256": hashlib.sha256(data).hexdigest()}
    kind = "case" if findings is not None else "skill"
    fields = metadata("selection-fixture", kind, path, source)
    fields["composition"] = {
        "nodes": nodes, "routes": routes, "when": {}, "license": "Apache-2.0",
        "permissions": {"read": True, "retain": True, "redistribute": True},
    }
    return Bundle(fields, {path: data}, {})


def node(pin, *requires):
    return {"ref": pin.ref, "revision": pin.revision, "requires": list(requires)}


def case_fixture(store):
    findings = [
        {"id": "target", "reason": "范围 A", "outcome": "one"},
        {"reason": "sibling scope B", "outcome": "two"},
    ]
    document = json.dumps({"findings": findings}, ensure_ascii=False).encode()
    attachment = bytes([0xff, 0, 0xef, 0x7f])
    nodes, routes, expected = {}, {}, {}
    for index, finding in enumerate(findings):
        key = f"finding-{index}"
        for layer in ("L0", "L1", "L2", "L3"):
            name = key + "-" + layer.lower()
            if layer == "L3":
                path = f"assets/{key}.bin"
                body = attachment + bytes([index])
                source, start = body, 0
            else:
                # A byte span from the original JSON, pinned before content projection.
                path = "case.json"
                body = json.dumps(finding, ensure_ascii=False).encode()
                source = document
                start = source.index(body)
            digest = hashlib.sha256(body).hexdigest()
            fields = metadata(name, "knowledge", "body",
                              {"type": "fixture", "sha256": hashlib.sha256(source).hexdigest()})
            fields["atom"] = {
                "layer": layer, "when": {}, "license": "Apache-2.0",
                "permissions": {"read": True, "retain": True, "redistribute": True},
                "source_span": {"source_index": 0, "path": path, "sha256": digest,
                                "byte_range": [start, start + len(body)]},
            }
            content = {"body": body}
            if layer == "L3":
                fields["atom"]["resource"] = path
                content = {"body": b"Attachment", path: body}
            pin = AtomPin(f"store:{name}", store.create(Bundle(fields, content, {})))
            nodes[name] = node(pin)
            routes[name] = {"layer": layer, "required": [name],
                            "finding": f"case.json#/findings/{index}"}
            expected[index, layer] = (pin, body)
    bundle = composition(nodes, routes, findings=findings)
    pin = AtomPin("store:" + bundle.metadata["id"], store.create(bundle))
    return pin, expected
