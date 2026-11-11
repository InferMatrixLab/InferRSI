"""Read and sanitize fields shared by campaign records and their views."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath, PureWindowsPath


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return float(value) if math.isfinite(value) else None
    except OverflowError:
        return None


def _text(value: object, default: str = "not_recorded", limit: int = 240) -> str:
    if not isinstance(value, str) or not value:
        return default
    value = re.sub(r"https?://\S+", "[redacted-url]", value, flags=re.I)
    value = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[redacted-email]", value)
    value = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[redacted-address]", value)
    value = re.sub(r"(?<!\w)[A-Za-z]:[\\/][^\s<>\"']+", "[redacted-path]", value)
    value = re.sub(r"(?<![\w:])/(?:[^\s/<>\"']+/)*[^\s/<>\"']+", "[redacted-path]", value)
    value = re.sub(
        r"(?i)\b(api[_-]?key|token|password|secret)\s*[:=]\s*\S+",
        r"\1=[redacted]", value,
    )
    return value[:limit]


_SENSITIVE_NAME = re.compile(
    r"(?i)(?:password|passwd|token|secret|api[_-]?key|access[_-]?key|auth|credential|cookie|header)"
)
_SENSITIVE_PATH = re.compile(
    r"(?i)(?:^|[/._-])(?:password|passwd|token|secret|api[_-]?key|credential|cookie)(?:$|[/._-])"
)


def _relative_location(value: object) -> str | None:
    """Accept a source location, never a host path or a credential-like filename."""
    if not isinstance(value, str) or not value or len(value) > 240:
        return None
    posix, windows = PurePosixPath(value), PureWindowsPath(value)
    if (posix.is_absolute() or windows.is_absolute() or windows.drive or ".." in posix.parts
            or ".." in windows.parts or "\\" in value or any(ord(c) < 32 for c in value)
            or "://" in value or _text(value, "", 240) != value
            or _SENSITIVE_PATH.search(value) or any(part.startswith(".") for part in posix.parts)):
        return None
    return posix.as_posix()


def _safe_argv(value: object, *, candidate_ids: set[str] | None = None) -> list[str] | None:
    """Keep useful argv structure without retaining arbitrary argument values."""
    if not isinstance(value, list) or not value or len(value) > 100:
        return None
    if not all(isinstance(arg, str) and len(arg) <= 4096 for arg in value):
        return None
    safe_words = {"baseline", "candidate", "mtp", "quality-baseline", "quality-mtp", "smoke",
                  "true", "false", "auto", "vllm", "float16", "bfloat16", "float32"}
    safe_options = {"--mode", "--dtype", "--candidate", "--gpu", "--max-tokens", "--max-model-len",
                    "--num-speculative-tokens", "--max-num-batched-tokens", "--input-len",
                    "--output-len", "--batch-size", "--num-prompts", "--port",
                    "--tensor-parallel-size", "--gpu-memory-utilization", "--max-num-seqs",
                    "--generation-config"}
    known_options = safe_options | {"-m", "--model", "--served-model-name", "--host", "--result",
                                   "--speculative-config", "--disable-prefix-caching",
                                   "--disable-log-requests", "--trust-remote-code",
                                   "--enforce-eager",
                                   "--dataset-name", "--dataset-path", "--backend", "--endpoint"}

    def safe_value(name: str, val: str) -> bool:
        if name == "--candidate":
            return bool(candidate_ids and val in candidate_ids
                        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", val)
                        and not _SENSITIVE_NAME.search(val) and _text(val, "", 128) == val)
        if name == "--gpu":
            return bool(re.fullmatch(r"[0-9]{1,3}", val))
        return val in safe_words or bool(re.fullmatch(r"[0-9.]+", val))

    result = []
    hide_next = False
    value_option = None
    for index, arg in enumerate(value):
        if hide_next:
            result.append("[redacted]")
            hide_next = False
            value_option = None
            continue
        if arg in ("-H", "-c", "--header", "--data", "--data-raw"):
            result.append(arg)
            hide_next = True
            continue
        if arg.startswith("-"):
            value_option = None
            name, equal, val = arg.partition("=")
            if not re.fullmatch(r"--?[A-Za-z0-9][A-Za-z0-9_-]*", name):
                result.append("[redacted]")
                continue
            if _SENSITIVE_NAME.search(name) and name not in safe_options:
                result.append("[sensitive-option]" + ("=[redacted]" if equal else ""))
                hide_next = not equal
                continue
            if name not in known_options:
                result.append("[redacted-option]")
                continue
            if equal:
                safe = name in safe_options and safe_value(name, val)
                shown = val if safe else "[redacted]"
                result.append(name + "=" + shown)
            else:
                result.append(name)
                hide_next = bool(_SENSITIVE_NAME.search(name)) and name not in safe_options
                accepts_value = name in safe_options or name == "--speculative-config"
                value_option = name if accepts_value else None
            continue
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", arg):
            result.append(arg.split("=", 1)[0] + "=[redacted]")
            continue
        base = PureWindowsPath(arg).name if "\\" in arg else PurePosixPath(arg).name
        if (index == 0 and re.fullmatch(r"(?:python(?:[0-9.]+)?|vllm|pytest|bash|sh)", base)):
            result.append(base)
        elif (index == 1 and base.endswith(".py")
              and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", base)
              and not _SENSITIVE_NAME.search(base)):
            result.append(base if base == arg else "[path]/" + base)
        elif index == 2 and value[1] == "-m" and arg == "vllm.entrypoints.openai.api_server":
            result.append(arg)
        elif value_option == "--speculative-config":
            try:
                config = json.loads(arg)
            except (ValueError, RecursionError):
                config = None
            if (isinstance(config, dict) and set(config) == {"method", "num_speculative_tokens"}
                    and config.get("method") == "mtp"
                    and type(config.get("num_speculative_tokens")) is int
                    and 0 < config["num_speculative_tokens"] <= 128):
                result.append(json.dumps(config, separators=(",", ":")))
            else:
                result.append("[redacted]")
        elif value_option and safe_value(value_option, arg):
            result.append(arg)
        else:
            result.append("[redacted]")
        value_option = None
    return result


def _inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _snapshot(root: Path, path: Path, kind: str) -> tuple[bytes | None, dict]:
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return None, {"kind": kind, "state": "missing", "missing_reason": "unsafe_path"}
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None, {"kind": kind, "path": relative, "state": "missing",
                      "missing_reason": "file_absent"}
    except OSError:
        return None, {"kind": kind, "path": relative, "state": "missing",
                      "missing_reason": "unreadable"}
    return data, {"kind": kind, "path": relative, "state": "present",
                  "sha256": hashlib.sha256(data).hexdigest()}


def _object_snapshot(path: Path, root: Path, kind: str) -> tuple[dict, str, dict]:
    raw, ref = _snapshot(root, path, kind)
    if raw is None:
        state = "unsafe" if ref["missing_reason"] == "unsafe_path" else "missing"
        return {}, state, ref
    try:
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("object required")
    except (UnicodeError, json.JSONDecodeError, ValueError):
        return {}, "corrupt", {**ref, "state": "missing", "missing_reason": "corrupt"}
    return data, "present", ref


def _object(path: Path, root: Path) -> tuple[dict, str]:
    data, state, _ = _object_snapshot(path, root, "record")
    return data, state


def _file_ref(root: Path, path: Path, kind: str) -> dict:
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return {"kind": kind, "state": "missing", "missing_reason": "unsafe_path"}
    try:
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(block)
        digest = hasher.hexdigest()
    except FileNotFoundError:
        return {"kind": kind, "path": relative, "state": "missing", "missing_reason": "file_absent"}
    except OSError:
        return {"kind": kind, "path": relative, "state": "missing", "missing_reason": "unreadable"}
    return {"kind": kind, "path": relative, "state": "present", "sha256": digest}
