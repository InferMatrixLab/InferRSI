"""The four reviewed handwritten cases, with deterministic output-size padding."""

import hashlib
from pathlib import Path

import contract


def payloads():
    # A comment-only prefix makes the retained result exceed the old 1 MiB cap.
    padding = "#" + "fixed-fixture-padding " * 52000 + "\n"
    solutions = {
        "Synthetic/correct": padding + "def f(x):\n    return x + 1\n",
        "Synthetic/plus_wrong": "def f(x):\n    return 1\n",
        "Synthetic/exception": "def f(x):\n    raise ArithmeticError('synthetic')\n",
        "Synthetic/input_timeout": "import time\ndef f(x):\n    time.sleep(5)\n    return x + 1\n",
    }
    dataset = b"".join(
        contract.canonical(
            {
                "task_id": identity,
                "prompt": "def f(x):\n",
                "canonical_solution": "    return x + 1\n",
                "contract": "",
                "entry_point": "f",
                "base_input": [[0]],
                "plus_input": [[1]],
                "atol": 0,
            }
        )
        + b"\n"
        for identity in solutions
    )
    samples = b"".join(
        contract.canonical({"task_id": identity, "solution": solution}) + b"\n"
        for identity, solution in solutions.items()
    )
    export = (
        contract.canonical(
            {
                "samples_sha256": contract.sha(samples),
                "dataset_sha256": contract.sha(dataset),
                "evalplus_dataset_md5": hashlib.md5(dataset).hexdigest(),
                "task_ids": sorted(solutions),
                "generated_code_executed": False,
            }
        )
        + b"\n"
    )
    return dict(zip(contract.INPUT_NAMES, (samples, dataset, export), strict=True))


def create(directory):
    Path(directory).mkdir()
    values = payloads()
    for name, raw in values.items():
        with (Path(directory) / name).open("xb") as stream:
            stream.write(raw)
    return {
        "export_sha256": contract.sha(values["human-export.json"]),
        "cohort_sha256": contract.sha(
            contract.canonical(contract.decode(values["human-export.json"])["task_ids"])
        ),
    }
