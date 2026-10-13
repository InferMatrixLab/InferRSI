"""Warmups and artifact collection shared by image/video request adapters."""

import json
from pathlib import Path
from statistics import mean

from ...infra.artifacts import sha256


def collect_samples(
    request,
    *,
    prompts,
    warmup_seeds,
    repetitions: int,
    media: Path,
    record: dict,
    suffix: str,
    before_measure=None,
) -> None:
    """Mutate the caller's record so partial evidence survives request failure.

    ``request(item, path)`` owns protocol/transport. This loop owns only seed
    ordering, timing records and artifacts; it does not know models or devices.
    """
    if (
        isinstance(repetitions, bool)
        or not isinstance(repetitions, int)
        or repetitions < 1
        or not prompts
    ):
        raise ValueError("Positive repetitions and at least one prompt are required")
    ids = [item["id"] for item in prompts]
    if len(set(ids)) != len(ids) or any(
        not isinstance(name, str) or not name or "/" in name or "\\" in name for name in ids
    ):
        raise ValueError("Prompt IDs must be unique nonempty filename components")
    if not suffix.startswith(".") or "/" in suffix or "\\" in suffix:
        raise ValueError("The artifact suffix must be a filename extension")
    if any(len(seeds) != len(prompts) for seeds in warmup_seeds):
        raise ValueError("Warmup seeds must cover every prompt")
    for seeds in warmup_seeds:
        for item, seed in zip(prompts, seeds):
            path = media / ("warmup" + suffix)
            latency = request({**item, "seed": seed}, path)
            record["warmup_samples_ms"].append(
                {"prompt": item["prompt"], "seed": seed, "latency_ms": latency}
            )
            if "first_request" not in record:
                first = media / ("first-request" + suffix)
                path.rename(first)
                record["first_request"] = {
                    "path": str(first),
                    "sha256": sha256(first),
                    "seed": seed,
                    "latency_ms": latency,
                }
            else:
                path.unlink()
    if before_measure is not None:
        before_measure()
    for group in range(repetitions):
        values = []
        for item in prompts:
            path = media / f"group-{group + 1:03d}-{item['id']}{suffix}"
            latency = request(item, path)
            values.append(latency)
            record["samples_ms"].append(
                {"group": group + 1, "id": item["id"], "latency_ms": latency}
            )
            record["artifacts"].append(
                {"group": group + 1, "id": item["id"], "path": str(path), "sha256": sha256(path)}
            )
            print(
                json.dumps({"group": group + 1, "id": item["id"], "latency_ms": latency}),
                flush=True,
            )
        record["groups_ms"].append(mean(values))
