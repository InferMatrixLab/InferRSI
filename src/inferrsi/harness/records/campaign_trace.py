"""Opt-in correlation envelope for existing agent event callbacks."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .evidence import STAGES


class CampaignTrace:
    """Append original events with correlation fields; callers own their IDs."""

    def __init__(self, path: Path, *, campaign_id: str, candidate_id: str, stage: str,
                 run_id: str | None = None, round_number: int | None = None):
        if (not isinstance(campaign_id, str) or not campaign_id
                or not isinstance(candidate_id, str) or not candidate_id or stage not in STAGES):
            raise ValueError("campaign, candidate and a known stage are required")
        if run_id is not None and (not isinstance(run_id, str) or not run_id):
            raise ValueError("run_id must be a nonempty string when supplied")
        if round_number is not None and (
            isinstance(round_number, bool) or not isinstance(round_number, int) or round_number < 1
        ):
            raise ValueError("round_number must be a positive integer")
        self.path = Path(path)
        self.context = {"schema_version": 1, "campaign_id": campaign_id,
                        "candidate_id": candidate_id, "stage": stage,
                        "run_id": run_id, "round": round_number}

    def __call__(self, event: dict) -> None:
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise ValueError("an event object with a type is required")
        if set(event) & (set(self.context) | {"time"}):
            raise ValueError("event already contains correlation fields")
        record = {**event, **self.context, "time": datetime.now(timezone.utc).isoformat()}
        line = json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(line)
