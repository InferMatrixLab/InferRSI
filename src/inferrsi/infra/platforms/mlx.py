import platform


def _parse_sysctl_info(stdout: str) -> tuple[bool, str]:
    # 解析固定 sysctl 文本；静态样例不代表真实硬件探测。
    rows = [line.partition(":") for line in stdout.splitlines() if line.strip()]
    values = {name.strip(): value.strip() for name, _, value in rows}
    if len(rows) != 2 or set(values) != {"hw.optional.arm64", "machdep.cpu.brand_string"}:
        raise ValueError("sysctl must report ARM64 capability and chip identity")
    flag = values["hw.optional.arm64"]
    chip = values["machdep.cpu.brand_string"]
    if flag not in ("0", "1") or not chip:
        raise ValueError("sysctl reported an invalid ARM64 flag or empty chip identity")
    return flag == "1", chip


def inspect_devices(*, device_ids, device_model, command):
    result = {"status": "unavailable", "tool": "sysctl", "selection_verified": False}
    if device_ids:
        result["reason"] = "MLX discovery does not support discrete device IDs (unified memory)"
        return result
    if platform.system() != "Darwin":
        result["reason"] = "MLX Apple Silicon discovery requires macOS"
        return result

    probe = command(["sysctl", "hw.optional.arm64", "machdep.cpu.brand_string"])
    result["probe"] = probe
    if probe["returncode"] != 0:
        result["reason"] = "sysctl could not report Apple Silicon hardware facts"
        return result
    try:
        arm64, chip = _parse_sysctl_info(probe["stdout"])
    except ValueError as exc:
        result["reason"] = str(exc)
        return result
    result["chip"] = chip
    if not arm64:
        result["reason"] = "Host is not Apple Silicon"
    elif device_model and device_model.casefold() not in chip.casefold():
        result["status"] = "device_model_mismatch"
        result["reason"] = "Discovered chip does not match the requested device model"
    else:
        result["status"] = "available"
        result["selection_verified"] = True
    return result
