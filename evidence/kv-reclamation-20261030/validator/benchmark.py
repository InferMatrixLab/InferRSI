"""Independent expected output for the separately pinned synthetic CPU workload.

Evaluator-only. This closed-form projection imports neither candidate nor control
and makes no timing or performance claim. It omits intermediate pending snapshots
only; the full contract verifier remains independently required.
"""


def benchmark_expected(count):
    if type(count) is not int or count < 1:
        raise ValueError("count must be a positive integer")
    observations = [{"reclaimed": []} for _ in range(3 * count)]
    for frontier in range(257):
        observations.append({
            "reclaimed": [
                block
                for index in range(frontier, count, 257)
                for block in (2 * index, 2 * index + 1)
            ]
        })
    return {"observations": observations, "pending": []}
