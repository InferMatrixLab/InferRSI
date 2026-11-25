"""contract-v1 schema patterns match the whole value, not a value plus a line ending.

In Python ``re``, which ``jsonschema`` uses, ``$`` also matches before one trailing LF.
So every pattern except ``Path`` ends with ``(?![\\s\\S])``, which matches only at the end
of input in Python ``re`` and in ECMA-262. The paired vectors in
``docs/contracts/fixtures/pattern-boundary-cases.json`` are validated through the named
schema definitions, never through a separate regex or ``fullmatch`` helper.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path

import jsonschema
import pytest

CONTRACTS = Path(__file__).resolve().parents[2] / "docs" / "contracts"
SCHEMA = json.loads((CONTRACTS / "schemas" / "contract-v1.schema.json").read_text("utf-8"))
VECTORS = json.loads(
    (CONTRACTS / "fixtures" / "pattern-boundary-cases.json").read_text("utf-8")
)
END = VECTORS["end_assertion"]
CASES = VECTORS["cases"]
IDS = [f"{case['pattern']}={case['valid']}" for case in CASES]
# ECMA-262 compiles each pattern as written. Ajv uses the u flag; check both forms.
ECMA_PROBE = """
const cases = JSON.parse(require("fs").readFileSync(0, "utf8"));
const out = cases.map(([pattern, texts]) => ["u", ""].map(
  (flags) => texts.map((text) => new RegExp(pattern, flags).test(text))));
process.stdout.write(JSON.stringify(out));
"""


def patterns(node: object, pointer: str = "") -> dict[str, str]:
    found: dict[str, str] = {}
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{pointer}/{key}"
            if key == "pattern" and isinstance(value, str):
                found[child] = value
            else:
                found.update(patterns(value, child))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.update(patterns(value, f"{pointer}/{index}"))
    return found


SCHEMA_PATTERNS = patterns(SCHEMA)


def place(case: dict, text: str) -> object:
    if case["slot"] == "value":
        return text
    if case["slot"] == "key":
        (value,) = case["instance"].values()
        return {text: value}
    instance = copy.deepcopy(case["instance"])
    instance[case["property"]] = text
    return instance


def leaves(errors) -> list:
    flat = []
    for error in errors:
        flat.append(error)
        flat.extend(leaves(error.context))
    return flat


def test_every_schema_pattern_has_paired_vectors_and_only_path_keeps_dollar() -> None:
    assert END == "(?![\\s\\S])"
    assert {case["pattern"] for case in CASES} == set(SCHEMA_PATTERNS)
    assert len(SCHEMA_PATTERNS) == 12
    for pointer, pattern in SCHEMA_PATTERNS.items():
        if pointer == "/$defs/Path/pattern":
            (control,) = [case for case in CASES if case.get("control")]
            assert control["pattern"] == pointer and pattern == control["pattern_text"]
        else:
            assert pattern.startswith("^") and pattern.endswith(END), pointer
            assert "$" not in pattern, pointer
    for pointer in set(SCHEMA_PATTERNS):
        kinds = set().union(*(case["invalid"] for case in CASES if case["pattern"] == pointer))
        assert kinds == set(VECTORS["variants"]), pointer


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_variants_differ_from_the_valid_value_only_by_the_line_ending(case: dict) -> None:
    valid = case["valid"]
    expected = {"trailing_lf": valid + "\n", "leading_lf": "\n" + valid}
    if len(valid) > 1:
        expected["embedded_lf"] = valid[:1] + "\n" + valid[1:]
    expected |= {"trailing_crlf": valid + "\r\n", "trailing_cr": valid + "\r"}
    assert case["invalid"] == expected
    assert place(case, valid) == case["instance"]


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_named_definition_accepts_the_valid_value_and_rejects_each_variant(case: dict) -> None:
    validator = jsonschema.Draft202012Validator(
        {**SCHEMA, "$ref": f"#/$defs/{case['definition']}"}
    )
    # The valid counterpart must pass first, so a negative cannot pass on another error.
    assert not list(validator.iter_errors(case["instance"]))
    for kind, text in case["invalid"].items():
        errors = leaves(validator.iter_errors(place(case, text)))
        assert errors, (kind, text)
        assert any(error.validator == "pattern" for error in errors), (kind, text)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js runs the ECMA-262 check")
def test_schema_patterns_have_the_same_outcome_in_ecma_262() -> None:
    cases = [
        [SCHEMA_PATTERNS[case["pattern"]], [case["valid"], *case["invalid"].values()]]
        for case in CASES
    ]
    result = subprocess.run(
        [shutil.which("node"), "-e", ECMA_PROBE], input=json.dumps(cases),
        capture_output=True, text=True, check=True, timeout=60,
    )
    for case, outcome in zip(CASES, json.loads(result.stdout), strict=True):
        expected = [True] + [False] * len(case["invalid"])
        assert outcome == [expected, expected], case["pattern"]
