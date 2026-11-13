"""Execution observations, separate from budgeted item and resource payloads."""


def observation(*, entrypoint, request, selection, items, counts, assembly):
    from .. import __version__

    return {
        "schema_version": 1, "entrypoint": entrypoint, "calls": [entrypoint],
        "implementation": {"package": "inferrsi", "version": __version__},
        "request": request, "selection": selection, "items": items, "counts": counts,
        "assembly": assembly,
        "candidate_details": "not_recorded",
    }
