"""OpenAI-style image requests; the campaign supplies model and sampling settings."""

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path

from ...infra.http import post_json


@dataclass(frozen=True)
class ImageProtocol:
    model: str
    width: int
    height: int
    parameters: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.model or any(
            isinstance(v, bool) or not isinstance(v, int) or v <= 0
            for v in (self.width, self.height)
        ):
            raise ValueError("A model name and positive integer image dimensions are required")
        reserved = {"model", "prompt", "seed", "n", "size", "response_format"}
        if reserved.intersection(self.parameters):
            raise ValueError("Sampling parameters cannot override the request identity or format")
        # Own a JSON snapshot, independent of the caller's parameter container.
        object.__setattr__(
            self, "parameters", json.loads(json.dumps(self.parameters, allow_nan=False))
        )

    def payload(self, item: dict) -> dict:
        return {
            "model": self.model,
            "prompt": item["prompt"],
            "seed": item["seed"],
            "n": 1,
            "size": f"{self.width}x{self.height}",
            "response_format": "b64_json",
            **self.parameters,
        }

    def request(self, base_url: str, item: dict, destination: Path, *, timeout=900) -> float:
        elapsed, data = post_json(
            base_url.rstrip("/") + "/v1/images/generations",
            self.payload(item),
            timeout=timeout,
        )
        images = json.loads(data)["data"]
        if len(images) != 1:
            raise ValueError("Expected exactly one completed image")
        png = base64.b64decode(images[0]["b64_json"], validate=True)
        if not png.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Expected lossless PNG")
        Path(destination).write_bytes(png)
        return elapsed
