"""Synthetic CLI host exercising exact prompt delivery, not an actual Agent."""

import json
import sys
from pathlib import Path

if sys.argv[1:] == ["--version"]:
    print("synthetic-codex-control")
else:
    prompt = sys.stdin.buffer.read().decode("utf-8")
    reply = Path(sys.argv[sys.argv.index("--output-last-message") + 1])
    reply.write_text(prompt, encoding="utf-8")
    for event in ({"type": "thread.started", "thread_id": "synthetic-session"},
                  {"type": "turn.completed"}):
        print(json.dumps(event), flush=True)
