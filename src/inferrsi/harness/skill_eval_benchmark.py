"""Shared CPU tasks for SkillEval's captured-artifact path.

The trusted parent owns inputs and the scalar oracle. Submitted source runs only
inside the existing Linux bubblewrap boundary, without the repository or grader.
This adapter grades correctness, never child-reported timing or performance.
"""

import base64
import binascii
import hashlib
import json
import os
import signal
import subprocess
import tempfile
from pathlib import Path

from . import skill_eval_engineering as engineering
from .benchmarks import numpy_task
from .benchmarks.contract import TaskPackage, load_builtin_task

ADAPTER = "engineering-benchmark-v1"
ARTIFACT = "implementation.py"
MAX_SOURCE_BYTES = engineering.MAX_SOURCE_BYTES
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
SandboxUnavailable = engineering.SandboxUnavailable
read_regular = engineering.read_regular
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["artifact", "summary"],
    "properties": {
        "artifact": {"type": "string", "enum": [ARTIFACT]},
        "summary": {"type": "string"},
    },
}
PROMPT = (
    "Read task.json and the assigned knowledge. Change only implementation.py, "
    "implementing compute(x, *, eps) under the public shared CPU task contract. "
    "Use NumPy, math and self-contained helpers; preserve input contents. "
    "Do not change frozen inputs or create other files. No network, installs, "
    "other agents, commits or publication. Return artifact='implementation.py' "
    "and a concise summary, not a verdict or claimed speedup. The controller "
    "retains the actual file and independently checks its behavior in isolation."
)


def task_package(name: str) -> TaskPackage:
    """The artifact sandbox supports only the packaged NumPy CPU contract."""
    package = load_builtin_task(name)
    manifest = package.manifest
    if (manifest["adapter"] != "numpy-axis1-v2"
            or manifest["environment"] != {
                "backend": "cpu", "runtime": "numpy", "dtype": "float32"}):
        raise ValueError("Formal benchmark artifacts require the NumPy CPU adapter")
    return package


def task_descriptor(name: str) -> dict:
    package = task_package(name)
    manifest = package.manifest
    return {
        "id": name,
        "split": "development",
        "request": (
            manifest["description"] + " Implement compute(x, *, eps) in implementation.py. "
            "Inputs and output are NumPy float32 arrays; preserve shape and input bytes. "
            "Reduce axis 1; RMSNorm workloads include four-dimensional inputs. Use eps for "
            "RMSNorm. Public finite inputs include strided layouts, zeros, large and tiny "
            "values and singleton reductions. The shared task's base and distinct-per-call "
            "input sequence is checked. This SkillEval adapter grades correctness only; "
            "no latency, hardware, holdout generalization or skill-benefit claim follows."
        ),
        "provenance": manifest["source"]["url"],
        "contract": manifest,
        "benchmark": {
            "task_id": name,
            "task_sha256": package.task_sha256,
            "grader_sha256": package.grader_sha256,
        },
    }


def validate_task(task):
    if not isinstance(task, dict) or not isinstance(task.get("benchmark"), dict):
        raise ValueError("Shared benchmark task requires a canonical descriptor")
    name = task["benchmark"].get("task_id")
    if not isinstance(name, str) or task != task_descriptor(name):
        raise ValueError("Shared benchmark descriptor or frozen task identity changed")


def starter(task) -> bytes:
    validate_task(task)
    return (task_package(task["benchmark"]["task_id"]).root / "candidate.py").read_bytes()


def input_hashes(workspace: Path) -> dict:
    return engineering.input_hashes(workspace, editable=ARTIFACT)


def _numpy():
    try:
        import numpy as np
    except (ImportError, OSError):
        raise SandboxUnavailable("Shared benchmark verification requires NumPy") from None
    return np


# Expected outputs, task packages, and the grader are never mounted in the child.
# All arrays remain alive and compute is loaded once for the complete sequence.
RUNNER = '''import base64, json, platform, resource, sys
resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
resource.setrlimit(resource.RLIMIT_AS, (1073741824, 1073741824))
resource.setrlimit(resource.RLIMIT_FSIZE, (33554432, 33554432))
resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
sys.path.insert(0, "/runtime")
import numpy as np
if sys.argv[1:] == ["probe"]:
    print(json.dumps({"ready": True, "numpy": np.__version__,
                      "python": platform.python_version(), "machine": platform.machine()}))
else:
    print("INFERRSI_BENCHMARK_READY", file=sys.stderr, flush=True)
    request = json.loads(sys.stdin.read(16777217))
    arrays = []
    for record in request["inputs"]:
        x = np.frombuffer(base64.b64decode(record["data"], validate=True),
                          dtype=np.float32).reshape(record["shape"]).copy()
        if record["layout"] == "strided":
            storage = np.empty((*x.shape[:-1], x.shape[-1] * 2), dtype=np.float32)
            view = storage[..., ::2]
            view[...] = x
            x = view
        arrays.append(x)
    namespace = {"__name__": "benchmark_candidate", "__file__": "/work/implementation.py"}
    with open("/work/implementation.py", encoding="utf-8") as source:
        exec(compile(source.read(), "implementation.py", "exec"), namespace)
    compute = namespace["compute"]
    outputs = []
    for x in arrays:
        y = compute(x, eps=request["eps"])
        output = None
        if isinstance(y, np.ndarray) and y.shape == x.shape and y.dtype == np.float32:
            output = {"shape": list(y.shape), "dtype": str(y.dtype),
                      "data": base64.b64encode(y.tobytes()).decode("ascii")}
        outputs.append({"output": output,
                        "input_after": base64.b64encode(x.tobytes()).decode("ascii")})
    print(json.dumps({"outputs": outputs}, allow_nan=False))
'''


def sandbox_command(work: Path, *, probe=False):
    # Reuse the established system-Python namespaces and read-only mount policy.
    command = engineering.sandbox_command(work, probe=probe)
    np = _numpy()

    query = (
        "import json,numpy,pathlib; "
        "print(json.dumps({'version':numpy.__version__,"
        "'root':str(pathlib.Path(numpy.__file__).resolve().parent)}))"
    )
    try:
        runtime = subprocess.run(
            ["/usr/bin/python3", "-I", "-c", query], check=True,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=5, env={"PATH": "/usr/bin:/bin", "LANG": "C"},
        )
        info = json.loads(runtime.stdout)
        root = Path(info["root"])
        if (info["version"] != np.__version__ or root.name != "numpy"
                or not root.is_absolute() or not root.is_dir()):
            raise ValueError("Unsupported NumPy runtime")
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        raise SandboxUnavailable("Matching system Python NumPy runtime is required") from None
    mounts = ["--ro-bind", str(root), "/runtime/numpy"]
    libraries = root.parent / "numpy.libs"
    if libraries.is_dir():
        mounts += ["--ro-bind", str(libraries.resolve()), "/runtime/numpy.libs"]
    mounts += ["--setenv", "OPENBLAS_NUM_THREADS", "1", "--setenv", "OMP_NUM_THREADS", "1"]
    # Create the narrow mount destinations before the final read-only root remount.
    position = command.index("--remount-ro")
    return command[:position] + mounts + command[position:]


def _invoke(work, request=None, *, probe=False):
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            process = subprocess.Popen(
                sandbox_command(work, probe=probe), stdin=subprocess.PIPE,
                stdout=stdout, stderr=stderr,
                env={"PATH": "/usr/bin:/bin", "LANG": "C"}, start_new_session=True,
            )
        except OSError:
            raise SandboxUnavailable("Cannot start benchmark artifact sandbox") from None
        timed_out = False
        try:
            process.communicate(json.dumps(request).encode(), timeout=15)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            timed_out = True
        if not probe:
            stderr.seek(0)
            if not stderr.read(128).startswith(b"INFERRSI_BENCHMARK_READY\n"):
                raise SandboxUnavailable("Benchmark worker did not establish its trusted boundary")
        if timed_out:
            return None
        stdout.seek(0)
        raw = stdout.read(MAX_OUTPUT_BYTES + 1)
        if process.returncode or len(raw) > MAX_OUTPUT_BYTES:
            return None
        try:
            return json.loads(raw)
        except (ValueError, UnicodeError, RecursionError):
            return None


def _prepare(package, np):
    manifest = package.manifest
    oracle, measurement = manifest["oracle"], manifest["measurement"]
    prepared, base, sequence = [], [], []
    for case in manifest["workloads"]:
        x = numpy_task.inputs(case, np)
        record = numpy_task.input_record(case, x)
        base.append(record)
        prepared.append((case, x, numpy_task.reference(x, oracle, np),
                         {**record, "phase": "precheck"}, case["id"]))
    seen = {record["input_sha256"] for record in base}
    for case in manifest["workloads"]:
        if case["id"] not in measurement["case_ids"]:
            continue
        for index in range(measurement["warmups"] + measurement["samples"]):
            x = numpy_task.inputs(case, np, sequence=index + 1)
            record = numpy_task.input_record(case, x)
            if record["input_sha256"] in seen:
                raise ValueError("Input sequence repeats earlier bytes")
            seen.add(record["input_sha256"])
            record.update(call_index=index,
                          phase="warmup" if index < measurement["warmups"] else "measurement")
            sequence.append(record)
            prepared.append((case, x, numpy_task.reference(x, oracle, np), record,
                             f"{case['id']}.call-{index}"))
    return prepared, base, sequence


def _array(value, original, np):
    if (not isinstance(value, dict) or set(value) != {"shape", "dtype", "data"}
            or value["shape"] != list(original.shape) or value["dtype"] != "float32"
            or not isinstance(value["data"], str)):
        return None
    try:
        raw = base64.b64decode(value["data"], validate=True)
    except (ValueError, binascii.Error):
        return None
    if len(raw) != original.nbytes:
        return None
    return np.frombuffer(raw, dtype=np.float32).reshape(original.shape)


def verify(task, output):
    validate_task(task)
    valid = (isinstance(output, dict)
             and set(output) == {"artifact", "summary", "artifact_source"}
             and output["artifact"] == ARTIFACT
             and isinstance(output["summary"], str)
             and isinstance(output["artifact_source"], str))
    if not valid:
        return {"passed": False, "assertions": {"artifact_schema": False}}
    try:
        source = output["artifact_source"].encode("utf-8")
    except UnicodeError:
        source = b""
    if not 0 < len(source) <= MAX_SOURCE_BYTES:
        return {"passed": False, "assertions": {"artifact_size": False}}
    np = _numpy()

    package = task_package(task["benchmark"]["task_id"])
    prepared, base, sequence = _prepare(package, np)
    request = {
        "eps": package.manifest["oracle"]["eps"],
        "inputs": [{"shape": list(x.shape), "layout": case["layout"],
                    "data": base64.b64encode(x.tobytes()).decode("ascii")}
                   for case, x, _, _, _ in prepared],
    }
    with tempfile.TemporaryDirectory(prefix="skill-benchmark-") as temporary:
        work = Path(temporary)
        (work / "runner.py").write_text(RUNNER, encoding="utf-8")
        (work / ARTIFACT).write_bytes(source)
        runtime = _invoke(work, probe=True)
        if (not isinstance(runtime, dict)
                or set(runtime) != {"ready", "numpy", "python", "machine"}
                or runtime["ready"] is not True or runtime["numpy"] != np.__version__
                or any(not isinstance(runtime[k], str) or not runtime[k]
                       for k in ("python", "machine"))):
            raise SandboxUnavailable("Benchmark sandbox preflight failed; no host fallback")
        actual = _invoke(work, request)
    package.assert_unchanged()
    receipt = {"identity": task["benchmark"], "workloads": base, "input_sequence": sequence,
               "artifact_sha256": hashlib.sha256(source).hexdigest(),
               "runtime": {k: runtime[k] for k in ("numpy", "python", "machine")},
               "returned_calls": [], "scope": "isolated-artifact-correctness-only",
               "timing": "not measured", "public_inputs": True,
               "coverage": (
                   "returned_calls indexes well-formed response rows, not independently "
                   "observed invocations; a crash may leave no rows. Isolation protects "
                   "the host and keeps the oracle outside, but does not prevent runtime "
                   "protocol spoofing by submitted source or public-suite overfitting."
               )}
    if (not isinstance(actual, dict) or set(actual) != {"outputs"}
            or not isinstance(actual["outputs"], list)
            or len(actual["outputs"]) != len(prepared)):
        return {"passed": False, "assertions": {"artifact_response": False}, "benchmark": receipt}
    checks = {}
    for (case, original, expected, record, prefix), result in zip(
        prepared, actual["outputs"], strict=True
    ):
        if not isinstance(result, dict) or set(result) != {"output", "input_after"}:
            checks[prefix + ".response"] = False
            continue
        received = _array(result["output"], original, np)
        after = _array({"shape": list(original.shape), "dtype": "float32",
                        "data": result["input_after"]}, original, np)
        assertions = numpy_task.check_output(
            received, original if after is None else after, original, expected,
            package.manifest["oracle"], np,
        )
        assertions["input_preserved"] = after is not None and assertions["input_preserved"]
        checks.update({prefix + "." + key: value for key, value in assertions.items()})
        receipt["returned_calls"].append(record)
    return {"passed": all(checks.values()), "assertions": checks, "benchmark": receipt}
