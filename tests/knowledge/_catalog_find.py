"""Use Find over the exact package inventory for record content assertions."""

import sys

from inferrsi.knowledge.catalog import _catalog_corpus, list_knowledge
from inferrsi.knowledge.knowledge_find import find


def find_package_records(query, *, limit=10, **filters):
    inventory = list_knowledge(limit=sys.maxsize, **filters)
    corpus, records = _catalog_corpus(inventory)
    by_ref = {doc.qualified: record for doc, record in zip(corpus.documents, records, strict=True)}
    hits = find(query, corpus, limit=limit)
    return [by_ref[f"{hit['authority']}:{hit['id']}"] for hit in hits["items"]]
