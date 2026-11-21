"""Read the installed MindIE graded catalog using its own retrieval engine.

Run this worker with the approved MindIE interpreter. Its SQLite connection is
read-only, and delivery accounting belongs to the caller's local receipts.
"""

import json
import sqlite3
import sys
from contextlib import closing
from importlib.metadata import version
from pathlib import Path
from threading import RLock
from time import perf_counter
from types import SimpleNamespace


def read(engine_path, domain, action, arguments):
    component = version("mindie-knowledge")
    if component != "0.13.13":
        raise ValueError("The project reader supports mindie-knowledge 0.13.13")
    from mindie_knowledge.graded.index import RoutingIndex
    from mindie_knowledge.graded.repository import GradedRepository
    from mindie_knowledge.state_layout import state_root

    class ReadOnlyRepository(GradedRepository):
        def observe_delivered(self, index, payload, *, delivery, run_id=None):
            """Leave MindIE's delivery counters and feedback state untouched."""

        def _rebuild_index(self, catalog, started):
            # The caller's read transaction already holds one consistent
            # generation. A missing derived index can be rebuilt in memory.
            index = RoutingIndex(self._read(item) for item in catalog["units"])
            if index.generation != catalog["generation"]:
                raise ValueError("MindIE catalog generation mismatch")
            index.build_elapsed_ms = (perf_counter() - started) * 1000
            return index

    engine = json.loads(Path(engine_path).read_text(encoding="utf-8"))
    if engine.get("domain") != domain:
        raise ValueError("The installed MindIE domain differs from the project grant")
    root = state_root(engine["root"], domain)
    database = (root / "state-v4.sqlite3").as_uri() + "?mode=ro"
    with closing(sqlite3.connect(database, uri=True, timeout=3)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        store = SimpleNamespace(db=db, root=root, domain=domain, lock=RLock())
        repository = ReadOnlyRepository(store)
        if action == "describe":
            if not repository.available():
                raise ValueError("The approved MindIE domain has no synced graded catalog")
            repository._load()
            return {"domain": domain, "component_version": component}
        if action == "query":
            return repository.query(**arguments, navigation_only=True)
        if action == "explain":
            return repository.explain(**arguments)
        raise ValueError("Unknown MindIE read action")


if __name__ == "__main__":
    try:
        result = read(*sys.argv[1:], json.load(sys.stdin))
    except ValueError as exc:
        # Only emit the detail for our fixed errors. Corpus and library errors
        # can contain private paths or material.
        detail = str(exc)
        if detail not in {
            "The project reader supports mindie-knowledge 0.13.13",
            "The installed MindIE domain differs from the project grant",
            "The approved MindIE domain has no synced graded catalog",
        }:
            detail = "MindIE rejected the read"
        print(json.dumps({"isError": True, "error": detail}))
        raise SystemExit(1) from None
    except (OSError, RuntimeError, ImportError, KeyError, TypeError, sqlite3.Error):
        print(json.dumps({"isError": True, "error": "The local MindIE catalog is unavailable"}))
        raise SystemExit(1) from None
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
