"""CPU-only probe of the installed Cache-DiT consecutive-step counter."""

import hashlib
import importlib.metadata
import inspect
import json
from pathlib import Path

from cache_dit.caching.cache_contexts.cache_context import CachedContext

context = CachedContext()
observations = []
for step in (4, 6, 7):
    if step == 6:
        # The manager resets the counter when the MC1 limit rejects step 5.
        context.continuous_cached_steps = 0
    context.get_current_step = lambda step=step: step
    context.add_cached_step()
    observations.append({"step": step, "counter": context.continuous_cached_steps})
source = Path(inspect.getfile(CachedContext))
print(
    json.dumps(
        {
            "cache_dit_version": importlib.metadata.version("cache-dit"),
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "observations": observations,
            "cached_steps": context.cached_steps,
            "scope": (
                "Counter transition only; manager reset is explicitly simulated. "
                "Not a performance measurement."
            ),
        },
        indent=2,
    )
)
