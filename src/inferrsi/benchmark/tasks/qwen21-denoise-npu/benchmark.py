# SPDX-License-Identifier: Apache-2.0
"""Check and pair-time a self-contained Qwen 2.1 denoising candidate."""

import argparse
import copy
import dis
import hashlib
import importlib.util
import inspect
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
import traceback
from importlib import import_module
from pathlib import Path


class OutputValidationError(ValueError):
    """An explicit task output/input contract check rejected this implementation."""


class CandidateContractError(ValueError):
    """The candidate could not satisfy the Python entry contract before execution."""


class CandidateRecheckedError(RuntimeError):
    """A recognized candidate-call failure; it is rejected only after baseline recheck."""

    failure_kind = None
    record_key = None

    def details(self):
        return {"error": str(self.__cause__)}


class CandidateDependencyError(CandidateRecheckedError):
    """A known missing optional dependency; baseline recheck is still required."""

    failure_kind = "unsupported_candidate_dependency"
    record_key = "dependency_failure"

    def __init__(self, module):
        super().__init__(f"Candidate requires unavailable optional dependency: {module}")
        self.module = module

    def details(self):
        return {"module": self.module, **super().details()}


class CandidateComputeContractError(CandidateRecheckedError):
    """A host-side shape/contract diagnostic from the candidate call; recheck is required."""

    failure_kind = "rejected_candidate_contract"
    record_key = "contract_failure"

    def __init__(self, diagnostic, operator):
        super().__init__(f"Candidate compute violated a tensor shape contract: {diagnostic}")
        self.diagnostic = diagnostic
        self.operator = operator

    def details(self):
        return {"diagnostic": self.diagnostic, "operator": self.operator, **super().details()}


def view_size_conflict(match):
    dims = [int(size) for size in match[1].split(", ")] if match[1] else []
    if any(size < -1 for size in dims) or dims.count(-1) > 1:
        return False
    known, elements = math.prod(size for size in dims if size != -1), int(match[2])
    # The same acceptance condition as PyTorch's view/reshape size inference.
    return not (known == elements or (-1 in dims and known > 0 and elements % known == 0))


# Complete messages of PyTorch's host-side shape checks, which run during operator
# dispatch before device work is queued, each with a host recheck of its reported
# sizes. Containing such text is no evidence: any other wording, prefix or suffix,
# or sizes that do not actually conflict, leave the error unattributed.
HOST_SHAPE_DIAGNOSTICS = {
    "shapes cannot be multiplied": (
        re.compile(r"(?:mm: |addmm: )?mat1 and mat2 shapes cannot be multiplied "
                   r"\((\d+)x(\d+) and (\d+)x(\d+)\)"),
        lambda match: int(match[2]) != int(match[3])),
    "must match the size of tensor": (
        re.compile(r"The size of tensor a \((\d+)\) must match the size of tensor b "
                   r"\((\d+)\) at non-singleton dimension \d+"),
        lambda match: len({int(match[1]), int(match[2])} - {1}) == 2),
    "is invalid for input of size": (
        re.compile(r"shape '\[(-?\d+(?:, -?\d+)*)?\]' is invalid for input of size (\d+)"),
        view_size_conflict),
    "Sizes of tensors must match": (
        re.compile(r"Sizes of tensors must match except in dimension \d+\. Expected size "
                   r"(\d+) but got size (\d+) for tensor number \d+ in the list\."),
        lambda match: int(match[1]) != int(match[2])),
}


def shape_check_diagnostic(message):
    """Name the host shape check whose complete message, with conflicting sizes, this is."""
    for diagnostic, (pattern, conflict) in HOST_SHAPE_DIAGNOSTICS.items():
        match = pattern.fullmatch(message)
        if match:
            return diagnostic if conflict(match) else None
    return None


# Instructions that run a called object or an operator slot. A Python callee adds
# its own traceback entry, so an error whose innermost entry stops at one of these
# was raised in native code. A raise statement stops at a raise instruction.
NATIVE_CALL_INSTRUCTIONS = frozenset({
    "CALL", "CALL_KW", "CALL_FUNCTION", "CALL_FUNCTION_KW", "CALL_FUNCTION_EX", "CALL_METHOD",
    "COMPARE_OP", "STORE_SUBSCR",
})


def raised_by_native_call(trace):
    for instruction in dis.get_instructions(trace.tb_frame.f_code):
        if instruction.offset == trace.tb_lasti:
            name = instruction.opname
            return name in NATIVE_CALL_INSTRUCTIONS or name.startswith(("BINARY_", "INPLACE_"))
    return False


def native_call_site(error, function, skip=None):
    # Interpreter evidence, not message text or file names alone. The innermost
    # traceback entry must stop at a call or operator instruction, either in the
    # file that defines `function` (a C++ operator such as `a @ b` leaves no Torch
    # Python frame) or in core PyTorch Python code called from it. Return that
    # file's last instruction as (code, offset). A raise statement anywhere,
    # including torch._check, and any device runtime wrapper, other library or
    # evaluator frame in between are no evidence; only the `skip` code is ignored.
    # This shows that native code raised the error, not which native code did.
    # Without PyTorch loaded, no PyTorch operator raised it.
    try:
        source = os.path.realpath(inspect.unwrap(function).__code__.co_filename)
    except (AttributeError, ValueError):
        return None
    torch_file = getattr(sys.modules.get("torch"), "__file__", None)
    if not torch_file:
        return None
    library = os.path.join(os.path.dirname(os.path.realpath(torch_file)), "")
    trace, innermost, site = error.__traceback__, None, None
    while trace is not None:
        code = trace.tb_frame.f_code
        filename = os.path.realpath(code.co_filename)
        if code is not skip and not filename.startswith(library):
            site = (code, trace.tb_lasti) if filename == source else None
        innermost, trace = trace, trace.tb_next
    return site if site and raised_by_native_call(innermost) else None


def plain_runtime_error(error):
    # No subclass such as a device or memory error, and no earlier failure.
    return type(error) is RuntimeError and error.__cause__ is None and error.__context__ is None


def host_shape_diagnostic(error, function):
    """Name the host shape check this error may be, before any replay evidence."""
    # A plain, unchained RuntimeError; one complete host-check message whose sizes
    # conflict; native code under a call in the submitted file raised it.
    if not plain_runtime_error(error):
        return None
    diagnostic = shape_check_diagnostic(str(error))
    if diagnostic and native_call_site(error, function):
        return diagnostic
    return None


class AttributionReplayComplete(Exception):
    """The isolated attribution replay ran its one candidate call; evaluation stops."""


def call_site_identity(site):
    # Comparable across processes: the frozen candidate file is the same by SHA256,
    # so a code object is identified by its name, first line and bytecode.
    if site is None:
        return None
    code, offset = site
    return {"name": getattr(code, "co_qualname", code.co_name), "line": code.co_firstlineno,
            "bytecode": hashlib.sha256(code.co_code).hexdigest(), "offset": offset}


def bitwise_equal(left, right):
    """Equal dtype, shape and bit pattern; -0.0 differs from 0.0, unlike torch.equal."""
    import torch

    def raw(value):
        return value.detach().cpu().contiguous().reshape(-1).view(torch.uint8)

    return (left.dtype == right.dtype and left.shape == right.shape
            and torch.equal(raw(left), raw(right)))


def json_ready(value):
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_ready(item) for item in value]
    return value.tolist() if hasattr(value, "tolist") else value


def numpy_random():
    # Load the optional singleton before candidate import, even if the candidate
    # itself would have been the first to import NumPy.
    try:
        return import_module("numpy.random")
    except ModuleNotFoundError as error:
        if error.name != "numpy":
            raise
        return None


def random_states(device):
    """Serialize supported global RNG states, or return None if capture fails."""
    # Python's and NumPy's generators are seeded from OS entropy in each new
    # process, so a replay can only start from them by restoring these states.
    import random

    import torch

    try:
        generator = numpy_random()
        states = {"python": random.getstate(),
                  "numpy": generator.get_state(legacy=False) if generator is not None else None,
                  "torch_cpu": torch.get_rng_state().tolist()}
        if device == "npu":
            states["npu"] = torch.npu.get_rng_state().tolist()
        return json.dumps(json_ready(states), sort_keys=True)
    except Exception:
        # Attribution is optional evidence. A failed snapshot cannot reject or
        # prevent execution of a candidate.
        return None


def restore_random_states(states, device):
    import random

    import torch

    version, internal, gauss = states["python"]
    random.setstate((version, tuple(internal), gauss))
    if (state := states["numpy"]) is not None:
        generator = numpy_random()
        kind = state["bit_generator"]
        if generator.get_state(legacy=False)["bit_generator"] != kind:
            bit_generator = getattr(generator, kind)
            if not isinstance(bit_generator, type) or not issubclass(
                    bit_generator, generator.BitGenerator):
                raise ValueError(f"Unsupported NumPy bit generator: {kind}")
            generator.set_bit_generator(bit_generator())
        generator.set_state(state)
    torch.set_rng_state(torch.tensor(states["torch_cpu"], dtype=torch.uint8))
    if device == "npu":
        torch.npu.set_rng_state(torch.tensor(states["npu"], dtype=torch.uint8))


def process_state(device):
    """The compared pre-call process state of the replay contract (see isolated_replay)."""
    import torch

    random = random_states(device)
    if random is None:
        return None
    state = {
        "random": hashlib.sha256(random.encode()).hexdigest(),
        "default_dtype": str(torch.get_default_dtype()),
        "threads": torch.get_num_threads(),
        "grad_enabled": torch.is_grad_enabled(),
        "inference_mode": torch.is_inference_mode_enabled(),
        "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
        "float32_matmul_precision": torch.get_float32_matmul_precision(),
    }
    if device == "npu":
        state["npu_hf32"] = bool(torch.npu.matmul.allow_hf32)
    return state


def reproduces(func, args, kwargs, replayed):
    try:
        func(*args, **kwargs)
    except Exception as reproduced:
        return (plain_runtime_error(reproduced) and str(reproduced) == str(replayed)
                and native_call_site(reproduced, reproduces) is not None)
    return False


def recorded_operator_error(function, inputs, params, config):
    """Run one submitted call under an operator error recorder and report its failure."""
    # Only the isolated replay process calls this, never a timed or scored call.
    # A dispatch mode keeps each error object that escapes an operator together
    # with that operator and its arguments. Returns None when the call succeeds.
    from torch.utils._python_dispatch import TorchDispatchMode

    escaped = {}

    def record(self, func, types, args=(), kwargs=None):
        kwargs = kwargs or {}
        try:
            return func(*args, **kwargs)
        except RuntimeError as raised:
            escaped.setdefault(id(raised), (raised, func, args, kwargs))
            raise

    class OperatorErrors(TorchDispatchMode):
        __torch_dispatch__ = record

    try:
        with OperatorErrors():
            function(*inputs, params, config=config)
    except Exception as again:
        replayed = again
    else:
        return None
    raised, func, args, kwargs = escaped.get(id(replayed), (None,) * 4)
    operator = None
    # The same plain error object left an ATen operator that got no message
    # argument (unlike `_assert_async`). The evaluator then calls that operator on
    # the recorded arguments without the submission on the stack; only core
    # PyTorch may raise the identical message.
    # The same must hold for host copies of those arguments: then the message
    # follows from the arguments alone, not from any device state.
    if (raised is replayed and plain_runtime_error(replayed)
            and getattr(func, "namespace", None) == "aten"
            and not any(isinstance(leaf, str) for leaf in tensors((args, kwargs)))):
        import torch

        def host(value):
            if isinstance(value, torch.Tensor):
                return value.detach().cpu().clone()
            if isinstance(value, dict):
                return {key: host(item) for key, item in value.items()}
            if isinstance(value, (tuple, list)):
                return type(value)(host(item) for item in value)
            return value

        if all(reproduces(func, call_args, call_kwargs, replayed)
               for call_args, call_kwargs in ((args, kwargs), (host(args), host(kwargs)))):
            operator = str(func)
    return {"message": str(replayed), "operator": operator,
            "site": call_site_identity(native_call_site(replayed, function, skip=record.__code__))}


def attributed_operator(error, function, replayed):
    """Name the operator only if an equivalent replay raised this error from it."""
    # The replay report must name a reproduced ATen operator, with the original
    # message and the original submitted instruction. Whether the replay is
    # equivalent and isolated is the caller's proof; without it there is no report.
    site = call_site_identity(native_call_site(error, function))
    if (not isinstance(replayed, dict) or not replayed.get("operator") or site is None
            or replayed.get("message") != str(error) or replayed.get("site") != site):
        return None
    return replayed["operator"]


def invoke_compute(function, inputs, params, config, *, candidate, baseline_verified,
                   replay=None):
    # Catch only the submitted function call, never setup, synchronization or
    # reference checks. TBE is optional for this task's trusted baseline; older
    # native candidate kernels can require it. Other missing modules stay unknown.
    try:
        return function(*inputs, params, config=config)
    except ModuleNotFoundError as error:
        if (candidate and baseline_verified and isinstance(error.name, str)
                and error.name.split(".", 1)[0] == "tbe"):
            raise CandidateDependencyError(error.name) from error
        raise
    except RuntimeError as error:
        # CANN wraps the Python import failure in an ACL RuntimeError. Require
        # its specific compiler/import diagnostic, not an ACL code or "tbe" alone.
        message = str(error)
        if candidate and baseline_verified and all(part in message for part in (
            "AclSetCompileopt(aclCompileOpt::ACL_PRECISION_MODE",
            "Environment_Error_Import_Python_Module_Failed(EC0010)",
            "Failed to import Python module ModuleNotFoundError: No module named 'tbe'.",
        )):
            raise CandidateDependencyError("tbe") from error
        # A shape message from a native call in the submission, after this case's
        # baseline passed, is only a lead. Unproven source, including any device
        # or backend wording, stays an infrastructure failure.
        diagnostic = (candidate and baseline_verified and replay is not None
                      and host_shape_diagnostic(error, function))
        if not diagnostic:
            raise
        failure = error
    # Outside the handler, so a replay error has no implicit context. `replay`
    # reports an equivalent, isolated replay of this call, or None. An attributed
    # error is still only a recheck request.
    operator = attributed_operator(failure, function, replay())
    if operator:
        raise CandidateComputeContractError(diagnostic, operator) from failure
    raise failure


def candidate_function(path):
    # Compile independently so only syntax errors in the submitted file are
    # attributed to the candidate, not failures importing its runtime dependencies.
    try:
        compile(path.read_bytes(), str(path), "exec")
    except SyntaxError as exc:
        raise CandidateContractError(str(exc)) from exc
    function = getattr(load(path, "submitted_candidate"), "compute", None)
    if not callable(function):
        raise CandidateContractError("Candidate must define callable compute")
    try:
        inspect.signature(function).bind(*(None,) * 6, config={})
    except ValueError as exc:
        raise CandidateContractError("Candidate compute signature cannot be inspected") from exc
    except TypeError as exc:
        raise CandidateContractError("compute does not accept the task arguments") from exc
    return function


class EngineImportGuard:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".", 1)[0] in {"vllm", "vllm_omni", "diffusers", "transformers"}:
            raise ModuleNotFoundError(f"The standalone task blocks engine import {fullname}")
        return None


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tensors(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from tensors(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from tensors(item)
    else:
        yield value


def run(args, output, record, identity):
    # The process environment before any candidate code runs, for an isolated replay.
    startup = {"env": dict(os.environ), "cwd": os.getcwd()}
    # This guard is also active while importing PyTorch and torch_npu.
    sys.meta_path.insert(0, EngineImportGuard())
    import torch

    if args.device == "npu":
        visible = os.environ.get("ASCEND_RT_VISIBLE_DEVICES", "").split(",")
        if len(visible) != 1 or not visible[0].strip().isdigit():
            raise ValueError("Run inside one caller-owned NPU allocation, e.g. npu run --gpus 1")
        import torch_npu

        torch.npu.set_device(0)
        torch.npu.matmul.allow_hf32 = False
        synchronize = torch.npu.synchronize
        device = "npu:0"
        record["runtime"] = {
            "torch": torch.__version__,
            "torch_npu": torch_npu.__version__,
            "device": torch.npu.get_device_name(0),
            "hf32": False,
        }
    else:
        if not args.check_only:
            raise ValueError("CPU is supported for --check-only mathematical checks")

        def synchronize():
            pass

        device = "cpu"
        record["runtime"] = {"torch": torch.__version__, "device": "cpu"}
    torch.set_num_threads(args.cpu_threads)
    source = output / "snapshot"
    workload = load(source / "workload.py", "task_workload")
    reference = load(source / "reference.py", "independent_reference").compute
    baseline = load(source / "baseline.py", "trusted_baseline").compute
    functions = {"baseline": baseline}
    dtype = torch.bfloat16 if args.device == "npu" else torch.float32
    task = json.loads((source / "task.json").read_text(encoding="utf-8"))
    tolerance = task["tolerance"]
    selected = [case for case in task["cases"] if not args.case or case["id"] in args.case]
    if not selected or args.case and set(args.case) - {c["id"] for c in selected}:
        raise ValueError("Unknown or empty case selection")
    record["selected_cases"] = [c["id"] for c in selected]
    record["score_scope"] = "selected_cases" if args.case else "complete_task"
    record["phase"] = "candidate_import"
    record["round_consumed"] = True
    if args.attribution_replay:
        # Start from the original worker's generator states, before candidate import.
        restore_random_states(json.loads(args.attribution_replay.read_text(encoding="utf-8")),
                              args.device)
    else:
        startup["random"] = random_states(args.device)
    functions["candidate"] = candidate_function(source / "candidate.py")
    verified_baselines = set()
    candidate_calls = 0

    def pristine_inputs():
        # The current request's inputs, never a candidate's possibly modified copy.
        return workload.map_tensors(inputs, lambda t: t.clone())

    def argument_layout(original):
        return [[str(previous.dtype), list(previous.shape), list(stride), device_before.type]
                for _, previous, stride, device_before in original]

    def isolated_replay(case, phase, config, original, before):
        # A new worker process evaluates the same frozen snapshot up to its own
        # first candidate call, which is this call: the same trusted baseline
        # call first, then the candidate on arguments it rebuilds from the frozen
        # case and seeds. No object of this process, and no state the failed call
        # left in it, reaches the replay. Replay contract, each item aligned at
        # the replay's start and compared at its candidate call:
        # - aligned: interpreter flags, environment and working directory from
        #   this worker's start; captured Python, NumPy (when available) and
        #   PyTorch global generator states from before candidate import;
        # - compared: frozen source hashes against this worker's in-memory
        #   identity, case, phase, configuration, argument dtype, shape, stride,
        #   device and bits, and the pre-call `process_state`.
        # Outside the contract: files outside the snapshot, other processes,
        # device memory and Python's per-process string hash secret. The
        # attributed operator must therefore also reproduce the message on host
        # copies of its recorded arguments (`recorded_operator_error`).
        directory = output / "attribution-replay"
        start = output / "attribution-start.json"
        start.write_text(startup["random"], encoding="utf-8")
        command = [sys.executable, *subprocess._args_from_interpreter_flags(),
                   str(source / "benchmark.py"),
                   "--candidate", str(source / "candidate.py"), "--output-dir", str(directory),
                   "--device", args.device, "--pairs", str(args.pairs),
                   "--samples", str(args.samples), "--warmups", str(args.warmups),
                   "--cpu-threads", str(args.cpu_threads), f"--attribution-replay={start}",
                   *(f"--case={selection}" for selection in args.case or ()),
                   *(["--check-only"] if args.check_only else [])]
        with open(output / "attribution-replay.log", "wb") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False,
                           env=startup["env"], cwd=startup["cwd"])
        result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
        replayed = result.get("attribution_replay") or {}
        expected = {"status": "attribution_replayed", "identity": identity, "case": case,
                    "phase": phase, "config": config, "arguments": argument_layout(original),
                    "process_state": before}
        actual = {"status": result.get("status"),
                  "identity": json.loads((directory / "identity.json").read_text(
                      encoding="utf-8")),
                  **{key: replayed.get(key) for key in list(expected)[2:]}}
        mismatches = [key for key in expected if actual[key] != expected[key]]
        if not mismatches:
            arguments = torch.load(directory / "arguments.pt", weights_only=True)
            if len(arguments) != len(original) or not all(
                    bitwise_equal(argument, previous)
                    for argument, (_, previous, *_) in zip(arguments, original)):
                mismatches.append("argument_bits")
        return replayed.get("error"), mismatches

    def invoke(label, call_inputs, params, config, expected, phase, pair=None, sample=None):
        nonlocal candidate_calls
        record["phase"] = label + "_" + phase
        # `config` is the evaluator's frozen case. Each call gets its own copy, so
        # recorded case IDs, the reference and any recheck never read an object
        # that a submission could change.
        case, call_config = config["id"], copy.deepcopy(config)
        leaves = list(tensors((call_inputs, params)))
        original = [
            (value, value.detach().cpu().clone(), value.stride(), value.device)
            for value in leaves
        ]
        replay = None
        if label == "candidate":
            candidate_calls += 1
            first_call = candidate_calls == 1
            # The state this call starts from, before any of its own code ran.
            before = process_state(args.device) if first_call else None
            if args.attribution_replay:
                # Replay process: keep this first candidate call's arguments and
                # process state as they were before it ran, record its failure and stop.
                torch.save([previous for _, previous, *_ in original], output / "arguments.pt")
                replayed = record["attribution_replay"] = {
                    "case": case, "phase": phase, "config": copy.deepcopy(call_config),
                    "arguments": argument_layout(original), "process_state": before}
                replayed["error"] = recorded_operator_error(functions[label], call_inputs,
                                                            params, call_config)
                raise AttributionReplayComplete()

            def preserved():
                # Nothing the failed call received may differ from before it ran:
                # configuration, container entries, or tensor values and layout.
                try:
                    return (call_config == config
                            and [id(value) for value in tensors((call_inputs, params))]
                            == [id(value) for value in leaves]
                            and all(value.dtype == previous.dtype
                                    and value.device == device_before
                                    and value.stride() == stride
                                    and bitwise_equal(value, previous)
                                    for value, previous, stride, device_before in original))
                except Exception:
                    return False

            def replay():
                # Only an equivalent, isolated replay may attribute the error. The
                # replay starts from the state this call started from only if no
                # candidate code ran before it in this worker, and gets equal
                # arguments only if this call did not change its own.
                attempt = record["attribution"] = {"case": case, "phase": record["phase"]}
                if not first_call:
                    attempt["result"] = "not_first_candidate_call"
                    return None
                if startup["random"] is None or before is None:
                    attempt["result"] = "replay_state_unavailable"
                    return None
                if not preserved():
                    attempt["result"] = "arguments_changed"
                    return None
                try:
                    replayed, mismatches = isolated_replay(case, phase, config, original,
                                                           before)
                except Exception as error:
                    attempt.update(result="replay_unavailable", error=str(error))
                    return None
                if mismatches:
                    attempt.update(result="replay_not_equivalent", mismatches=mismatches)
                    return None
                attempt.update(result="replayed", replay=replayed)
                return replayed

        synchronize()
        started = time.perf_counter_ns()
        try:
            result = invoke_compute(functions[label], call_inputs, params, call_config,
                                    candidate=label == "candidate",
                                    baseline_verified=case in verified_baselines,
                                    replay=replay)
        except CandidateRecheckedError as error:
            failed_phase = record["phase"]
            record[error.record_key] = {"case": case, "phase": failed_phase,
                                        **error.details()}
            # Recheck only the trusted baseline on pristine request inputs and its
            # own parameter storage, after any attribution replay of the candidate.
            # Any sync, execution or quality failure here keeps the baseline phase
            # and blocks the campaign. The failed candidate is never scored again,
            # and the baseline never reuses the candidate's possibly modified tensors.
            invoke("baseline", pristine_inputs(), separate_params["baseline"], config,
                   expected, "recovery_check")
            record["baseline_recheck"] = {"case": case, "correctness": "PASS"}
            record["phase"] = failed_phase
            raise
        synchronize()
        elapsed = (time.perf_counter_ns() - started) / 1e6
        shape = (call_inputs[3].numel() - 1, *call_inputs[0].shape)
        if (
            not isinstance(result, torch.Tensor)
            or tuple(result.shape) != shape
            or result.dtype != call_inputs[0].dtype
            or result.device != call_inputs[0].device
        ):
            raise OutputValidationError("Wrong trajectory shape, dtype or device")
        for value, previous, stride, device_before in original:
            if (
                value.dtype != previous.dtype
                or value.device != device_before
                or value.stride() != stride
                or not torch.equal(value.cpu(), previous)
            ):
                raise OutputValidationError("Inputs or parameters were mutated")
        if result.untyped_storage().data_ptr() in {
            value.untyped_storage().data_ptr() for value, *_ in original
        }:
            raise OutputValidationError(
                "Output must own storage independent of the read-only inputs")
        actual = result.detach().float().cpu()
        errors = actual - expected
        rms = errors.flatten(1).square().mean(1).sqrt()
        scale = expected.flatten(1).square().mean(1).sqrt().clamp_min(1e-12)
        nrmse = (rms / scale).tolist()
        valid = (
            bool(torch.isfinite(actual).all())
            and torch.allclose(actual, expected, rtol=tolerance["rtol"], atol=tolerance["atol"])
            and max(nrmse) <= tolerance["max_nrmse"]
        )
        record["calls"].append(
            {
                "case": case,
                "label": label,
                "phase": phase,
                "pair": pair,
                "sample": sample,
                "elapsed_ms": elapsed,
                "step_nrmse": nrmse,
                "max_abs_error": errors.abs().max().item(),
                "correctness": "PASS" if valid else "FAIL",
            }
        )
        result.zero_()
        if not valid:
            raise OutputValidationError(
                f"Trajectory failed numerical checks, per-step NRMSE={nrmse}")
        if label == "baseline":
            verified_baselines.add(case)
        return elapsed

    preparation = 0.0
    with torch.inference_mode():
        for index, entry in enumerate(selected):
            config = {**task["defaults"], **entry}
            params = workload.parameters(config, 1701 + index, device, dtype)
            separate_params = {
                label: workload.map_tensors(params, lambda t: t.clone()) for label in functions
            }
            cpu_params = workload.map_tensors(
                params, lambda t: t.cpu().float() if t.is_floating_point() else t.cpu()
            )
            samples = {label: [] for label in functions}
            count = (
                1
                + args.warmups
                + (args.pairs * args.samples if entry["measured"] and not args.check_only else 0)
            )
            for request in range(count):
                record["phase"] = "input_reference_preparation"
                started = time.perf_counter()
                inputs = workload.inputs(config, 9001 + index * 1000 + request, device, dtype)
                cpu_inputs = workload.map_tensors(inputs, lambda t: t.cpu())
                expected = reference(*cpu_inputs, cpu_params, config=config)
                preparation += time.perf_counter() - started
                measured = request > args.warmups
                phase = "measurement" if measured else "correctness" if request == 0 else "warmup"
                sample_index = request - args.warmups - 1
                pair = sample_index // args.samples if measured else None
                order = (
                    ("candidate", "baseline")
                    if measured and pair % 2
                    else ("baseline", "candidate")
                )
                for label in order:
                    owned_inputs = workload.map_tensors(inputs, lambda t: t.clone())
                    elapsed = invoke(
                        label,
                        owned_inputs,
                        separate_params[label],
                        config,
                        expected,
                        phase,
                        pair,
                        sample_index if measured else None,
                    )
                    if measured:
                        samples[label].append(elapsed)
            # Keep the exact same parameter dictionary and storage addresses.
            # An immediately repeated call must observe an in-place weight update.
            for label in functions:
                separate_params[label]["image_out"].neg_()
            cpu_params["image_out"].neg_()
            expected = reference(*cpu_inputs, cpu_params, config=config)
            for label in functions:
                invoke(
                    label,
                    workload.map_tensors(inputs, lambda t: t.clone()),
                    separate_params[label],
                    config,
                    expected,
                    "weight_update",
                )
            if samples["baseline"]:
                medians = {label: statistics.median(values) for label, values in samples.items()}
                record["cases"].append(
                    {
                        "id": config["id"],
                        "samples_ms": samples,
                        "baseline_median_ms": medians["baseline"],
                        "candidate_median_ms": medians["candidate"],
                        "speedup": medians["baseline"] / medians["candidate"],
                    }
                )
    record["preparation_seconds"] = preparation
    record["engine_import_guard"] = "active throughout evaluation"
    record["forbidden_modules_loaded"] = [
        name
        for name in sys.modules
        if name.split(".", 1)[0] in {"vllm", "vllm_omni", "diffusers", "transformers"}
    ]
    if record["forbidden_modules_loaded"]:
        raise ValueError("An engine module was already loaded")
    record.update(status="completed", correctness="PASS", phase="completed")
    if record["cases"]:
        record["speedup"] = math.exp(
            statistics.mean(math.log(c["speedup"]) for c in record["cases"])
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", choices=("npu", "cpu"), default="npu")
    parser.add_argument("--pairs", type=int, required=True)
    parser.add_argument("--samples", type=int, required=True, help="Samples per paired block")
    parser.add_argument("--warmups", type=int, required=True)
    parser.add_argument("--cpu-threads", type=int, default=8)
    parser.add_argument("--case", action="append")
    parser.add_argument("--check-only", action="store_true")
    # Internal: the isolated replay of a failed first candidate call; never scored.
    # Its value is the original worker's random generator states at candidate import.
    parser.add_argument("--attribution-replay", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.pairs < 1 or args.samples < 1 or args.warmups < 0 or args.cpu_threads < 1:
        parser.error("pairs, samples and threads must be positive; warmups must be nonnegative")
    if not args.candidate.is_file():
        parser.error("candidate must be a self-contained Python file")
    if args.output_dir.exists():
        parser.error("output-dir must be new")
    output = args.output_dir.resolve()
    source = output / "snapshot"
    source.mkdir(parents=True)
    root = Path(__file__).resolve().parent
    for name in (
        "baseline.py",
        "reference.py",
        "workload.py",
        "task.json",
        "TASK.md",
        "benchmark.py",
        "LICENSE",
        "NOTICE.md",
    ):
        shutil.copyfile(root / name, source / name)
    shutil.copyfile(args.candidate, source / "candidate.py")
    identity = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    (output / "identity.json").write_text(json.dumps(identity, indent=2), encoding="utf-8")
    record = {
        "status": "infrastructure_failure",
        "correctness": "INCONCLUSIVE",
        "round_consumed": False,
        "phase": "setup",
        "calls": [],
        "cases": [],
        "speedup": None,
        "protocol": {
            "pairs": args.pairs,
            "samples": args.samples,
            "warmups": args.warmups,
            "check_only": args.check_only,
        },
    }
    started = time.perf_counter()
    try:
        try:
            run(args, output, record, identity)
        except AttributionReplayComplete:
            record["status"] = "attribution_replayed"
        if any(
            hashlib.sha256((source / name).read_bytes()).hexdigest() != digest
            for name, digest in identity.items()
        ):
            raise ValueError("Frozen source changed during evaluation")
    except Exception as error:
        explicit_rejection = isinstance(error, (OutputValidationError, CandidateContractError))
        checked_rejection = (isinstance(error, CandidateRecheckedError)
                             and record.get("baseline_recheck", {}).get("correctness") == "PASS")
        candidate_failure = ((explicit_rejection or checked_rejection)
                             and record["phase"].startswith("candidate_"))
        record.update(
            status="candidate_failure" if candidate_failure else "infrastructure_failure",
            correctness="FAIL" if candidate_failure else "INCONCLUSIVE",
            error=str(error),
            speedup=None,
        )
        if isinstance(error, CandidateRecheckedError):
            record["failure_kind"] = error.failure_kind
        if isinstance(error, CandidateDependencyError):
            record["missing_module"] = error.module
        (output / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
    record["elapsed_seconds"] = time.perf_counter() - started
    (output / "result.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(
        json.dumps({key: record.get(key) for key in ("status", "correctness", "speedup", "error")})
    )
    return (
        0
        if record["status"] == "completed"
        else 2
        if record["status"] == "candidate_failure"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
