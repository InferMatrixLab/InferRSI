"""Verify six completed InferRSI trial artifacts before evaluating throughput."""
import json
import sys
from pathlib import Path

files = sorted(Path(sys.argv[1]).glob("*/*/trial-*/result.json"))
assert len(files) == 6, files
rows = [json.loads(path.read_text()) for path in files]
for field, count in (("token_ids", 8), ("held_out_token_ids", 1)):
    reference = rows[0][field]
    assert len(reference) == count and all(len(ids) == 32 for ids in reference.values())
    assert all(row[field] == reference for row in rows)
for row in rows:
    assert len(row["round_tokens"]) == 5
    assert all(batch == rows[0]["token_ids"] for batch in row["round_tokens"]), "Across-round greedy token mismatch"
assert all(len(row["samples"]) == 3 and min(row["samples"]) > 0 for row in rows)
print("All eight timed requests and the held-out request match exactly across six trials.")
