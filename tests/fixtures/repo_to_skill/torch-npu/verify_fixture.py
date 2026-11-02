"""Check the portable candidate and helper failure contracts, without NPU claims."""

import ast
import hashlib
import json
import re
import runpy
import subprocess
import sys
import tempfile
from pathlib import Path

FIX = Path(__file__).resolve().parent
REPO = FIX.parents[3]
ROOT = REPO / "src/inferrsi/data/skill_library/frameworks/torch-npu/torch-npu"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    failures = []
    checks = []
    for skill in sorted(ROOT.rglob("SKILL.md")):
        text = skill.read_text(encoding="utf-8")
        front = text.split("---", 2)[1]
        keys = re.findall(r"^([\w-]+):", front, re.MULTILINE)
        meta = json.loads(skill.with_name("metadata.json").read_text(encoding="utf-8"))
        okay = (
            set(keys) == {"name", "description"}
            and len(keys) == 2
            and f"name: {skill.parent.name}" in front
            and re.search(r'^description: ".+"$', front, re.MULTILINE)
            and meta["profile"] == "local-skill-v1"
            and meta["license"] == "NOASSERTION"
            and meta["status"] == "candidate"
            and meta["disable-model-invocation"] is True
            and meta["metadata"]["disco-role"] == "operating"
        )
        checks.append(
            {
                "check": "native-profile",
                "file": skill.relative_to(ROOT).as_posix(),
                "passed": bool(okay),
            }
        )
        if not okay:
            failures.append(str(skill.relative_to(ROOT)))
    for path in sorted(ROOT.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", text):
            link = match.group(1)
            if "://" in link or link.startswith("#"):
                continue
            target = (path.parent / link.split("#")[0]).resolve()
            okay = target.is_relative_to(ROOT) and target.is_file()
            checks.append(
                {
                    "check": "internal-link",
                    "file": path.relative_to(ROOT).as_posix(),
                    "link": link,
                    "passed": okay,
                }
            )
            if not okay:
                failures.append(f"{path.relative_to(ROOT)} -> {link}")
    for path in ROOT.rglob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"))
    # Privacy scan excludes verbatim public source license/attribution notices.
    for path in ROOT.rglob("*"):
        if not path.is_file() or "licenses" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        okay = (
            re.search(r"(?<![A-Za-z])[A-Za-z]:[\\/]|/Users/|/home/[^<]|Bearer\s+[A-Za-z0-9]", text)
            is None
        )
        if not okay:
            failures.append(f"private-path/credential-like text: {path.relative_to(ROOT)}")
    cases = []
    for contract in sorted((FIX / "test-cases").rglob("assertions.json")):
        data = json.loads(contract.read_text(encoding="utf-8"))
        results = []
        for assertion in data["assertions"]:
            source = ROOT / assertion["file"]
            okay = (
                source.is_file()
                and assertion["contains"].casefold()
                in source.read_text(encoding="utf-8").casefold()
            )
            results.append(
                {"statement": assertion["statement"], "status": "PASS" if okay else "FAIL"}
            )
            if not okay:
                failures.append(f"{contract.parent.relative_to(FIX)}: {assertion['statement']}")
        cases.append({"case": contract.parent.relative_to(FIX).as_posix(), "results": results})
    helper_checks = []

    def execute(name, args, expected):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / name), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
        okay = result.returncode == expected
        helper_checks.append(
            {
                "helper": name,
                "arguments": args,
                "exit_code": result.returncode,
                "expected_exit_code": expected,
                "passed": okay,
                "output": result.stdout.strip(),
            }
        )
        if not okay:
            failures.append(f"helper {name} exit {result.returncode}, expected {expected}")

    for name in ("inspect_environment.py", "operator_contract.py", "runtime_smoke.py"):
        execute(name, ["--help"], 0)
    execute("inspect_environment.py", [], 0)
    for case in ("streams", "graph", "amp", "hccl", "profile"):
        execute("runtime_smoke.py", ["--case", case], 0)
    validator = runpy.run_path(str(ROOT / "scripts/operator_contract.py"))["validate"]
    valid = {
        "schema": "example::add(Tensor a, Tensor b) -> Tensor",
        "reference": "a + b",
        "dtypes": ["float32"],
        "layouts": ["contiguous"],
        "shape_cases": [[2, 2]],
        "mutates_inputs": False,
        "requires_grad": True,
        "has_autograd": True,
        "compile_requested": True,
        "has_meta": True,
    }
    assert validator(valid) == []
    for bad_schema in (None, 7, [], {}, ""):
        invalid = dict(valid, schema=bad_schema, mutates_inputs=True)
        assert validator(invalid), "invalid schema type must return errors"
    for key in ("has_meta", "has_autograd"):
        assert validator(dict(valid, **{key: False}))
    with tempfile.TemporaryDirectory() as directory:
        contract = Path(directory) / "contract.json"
        contract.write_text(json.dumps(valid), encoding="utf-8")
        # Do not persist the private temporary filename in shared reports.
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/operator_contract.py"), str(contract)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout
        contract.write_text('{"schema": null, "mutates_inputs": true}', encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/operator_contract.py"), str(contract)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 1, result.stdout
    absent = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import importlib.util; print(importlib.util.find_spec('torch') is None)",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if absent.stdout.strip() == "True":
        execute("inspect_environment.py", ["--device"], 2)
        execute("runtime_smoke.py", ["--case", "streams", "--run"], 2)
    js_report = {
        "status": "FAIL" if failures else "PASS",
        "scope": (
            "native metadata, links, source-retained bytes, helper contracts "
            "and static content assertions only"
        ),
        "checks": checks,
        "usability_cases": cases,
        "helper_checks": helper_checks,
        "negative_contract_cases": [
            "null schema",
            "integer schema",
            "list schema",
            "object schema",
            "empty schema",
            "missing Meta",
            "missing autograd",
        ],
        "failures": failures,
        "native_device_validation": "BLOCKED_REQUIRED_BACKEND",
        "agent_usability_replay": (
            "separate independent review; not performed by this static checker"
        ),
    }
    for file in (ROOT / "references/licenses/source-identities.json",):
        for retained in json.loads(file.read_text(encoding="utf-8"))["retained_files"]:
            assert (
                sha((ROOT / retained["bundled_path"]).read_bytes()) == retained["git_blob_sha256"]
            )
    output = FIX / "reports/verification/static-helper-usability-report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(js_report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": js_report["status"],
                "case_count": len(cases),
                "assertion_count": sum(len(c["results"]) for c in cases),
                "helper_checks": len(helper_checks),
                "failures": failures,
            },
            indent=2,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
