"""Replay the Find arms on a pinned main checkout using its native paginated reader."""
import argparse
import hashlib
import json
from pathlib import Path

from inferrsi.knowledge.knowledge_operations import KnowledgeReader


def read_pages(reader, hit, resource, remaining):
    """Read contiguous UTF-8 pages until the resource ends or the budget runs out."""
    parts = []
    start = 0
    while remaining:
        view, _ = reader.read_hit(hit, resource=resource, byte_range=(start, remaining))
        text = view["content"]
        size = len(text.encode())
        parts.append(text)
        remaining -= size
        if "next_byte_range" not in view:
            break
        start = view["next_byte_range"][0]
    return "".join(parts), view


def replay(cases, rows):
    reader = KnowledgeReader()
    results = []
    for row in rows:
        if not row["arm"].startswith("find"):
            continue
        case = cases[row["pilot"]]
        hits = {}
        for query in row["queries"]:
            for hit in reader.find(query, limit=5, pin_material=True)["items"]:
                hits[hit["material_ref"]] = hit
        if len(hits) != row["candidates"]:
            raise ValueError("Find candidate counts differ between revisions")
        choices = ([] if "selection_error" in row else json.loads(row["response"])["selections"])
        direct, extra = 65536, 32768
        resources = []
        links = []
        for choice in choices:
            hit = hits[choice["ref"]]
            if not direct:
                break
            body, view = read_pages(reader, hit, None, direct)
            direct -= len(body.encode())
            resources.append((hit, view["content_resource"], body))
            for path in dict.fromkeys(view.get("skill_documents", {}).values()):
                if path != view["content_resource"]:
                    links.append((hit, path))
        for hit, path in links[:5]:
            if not extra:
                break
            body, view = read_pages(reader, hit, path, extra)
            extra -= len(body.encode())
            resources.append((hit, view["content_resource"], body))
        matches = [
            [{"ref": hit["material_ref"], "revision": hit["revision"], "path": path,
              "delivered_sha256": hashlib.sha256(text.encode()).hexdigest(), "quote": phrase}
             for hit, path, text in resources for phrase in alternatives if phrase in text]
            for alternatives in case["passages"]
        ]
        results.append({"pilot": row["pilot"], "arm": row["arm"],
                        "coverage": [bool(m) for m in matches], "evidence": matches,
                        "delivered_bytes": 65536 - direct + 32768 - extra})
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_results", type=Path)
    args = parser.parse_args()
    cases = json.loads(Path(__file__).with_name("pilots.json").read_text(encoding="utf-8"))
    rows = json.loads(args.model_results.read_text(encoding="utf-8"))["rows"]
    print(json.dumps(replay({c["id"]: c for c in cases}, rows), ensure_ascii=False, indent=2))
