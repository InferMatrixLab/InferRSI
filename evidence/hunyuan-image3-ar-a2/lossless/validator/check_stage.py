"""Enforce exact outputs for all batches, all matched arms, and the separate prompt."""
import json
import sys
from pathlib import Path

run = max(Path(sys.argv[1]).glob("*/"),key=lambda p:p.stat().st_mtime_ns)
paths = sorted(run.glob("*/trial-*/result.json"))
assert len(paths) == 6
rows = [json.loads(p.read_text()) for p in paths]
base = rows[0]["round_tokens"][0]
held = rows[0]["held_out_token_ids"]
assert len(base)==8 and len(held)==1 and all(len(t)==32 for t in [*base.values(),*held.values()])
for row in rows:
    assert len(row["round_tokens"]) == 5 and len(row["samples"])==3
    assert all(batch==base for batch in row["round_tokens"]) and row["held_out_token_ids"]==held
print("All eight timed requests and the held-out request match across every round and every trial.")
