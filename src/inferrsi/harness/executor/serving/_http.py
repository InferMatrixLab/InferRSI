"""HTTP transport timing excludes request encoding and response interpretation."""

import json
import time
import urllib.request


def post_json(url: str, payload: dict, *, timeout: float) -> tuple[float, bytes]:
    body = json.dumps(payload, allow_nan=False).encode()
    request = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    start = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise ValueError("Image endpoint failed")
        data = response.read()
    return 1000 * (time.perf_counter() - start), data
