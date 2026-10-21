"""Explicit checkpoint and execution precision profiles for the two supported models."""

BF16_MODEL_ID = "Qwen/Qwen3.8-27B"
FP8_MODEL_ID = "Qwen/Qwen3.8-27B-FP8"
MODEL_IDS = (BF16_MODEL_ID, FP8_MODEL_ID)
FP8_QUANTIZATION = {"quant_method": "fp8", "activation_scheme": "dynamic", "fmt": "e4m3",
                    "weight_block_size": [128, 128]}


def precision(model_id):
    if model_id not in MODEL_IDS:
        raise ValueError("Unsupported model identity")
    if model_id == FP8_MODEL_ID:
        return {"weight_dtype": "float8_e4m3fn", "activation_dtype": "bfloat16",
                "quantization": dict(FP8_QUANTIZATION), "dequantized": False}
    return {"weight_dtype": "bfloat16", "activation_dtype": "bfloat16", "quantization": None}


def validate_config(config, model_id):
    precision(model_id)
    if not isinstance(config, dict) or not isinstance(config.get("text_config"), dict):
        raise ValueError("Invalid checkpoint configuration")
    text = config["text_config"]
    if (config.get("model_type") != "qwen3_5"
            or config.get("architectures") != ["Qwen3_5ForConditionalGeneration"]
            or text.get("model_type") != "qwen3_5_text"
            or text.get("dtype", text.get("torch_dtype")) != "bfloat16"
            or text.get("quantization_config")):
        raise ValueError("Expected BF16 activation Qwen3.5-architecture checkpoint")
    quant = config.get("quantization_config")
    if model_id == BF16_MODEL_ID:
        if quant:
            raise ValueError("Expected unquantized BF16 checkpoint")
    elif (not isinstance(quant, dict)
          or any(quant.get(key) != value for key, value in FP8_QUANTIZATION.items())
          or quant.get("dequantize", False) is not False
          or quant.get("scale_fmt", "float") != "float"):
        raise ValueError("Expected dynamic e4m3 FP8 checkpoint with 128 by 128 blocks")


def check_precision(record, model_id):
    expected = precision(model_id)
    # Historical BF16 manifests/traces had no separate precision object.
    if record.get("precision", expected if model_id == BF16_MODEL_ID else None) != expected:
        raise ValueError("Missing or mismatched execution precision identity")


def validate_native_loading(loading, model_id):
    if not isinstance(loading, dict):
        raise ValueError("Missing native loading report")
    dtype = "fp8" if model_id == FP8_MODEL_ID else "bfloat16"
    if (loading.get("scope") != "text_only" or loading.get("dtype") != dtype
            or type(loading.get("loaded_parameters")) is not int
            or loading["loaded_parameters"] <= 0):
        raise ValueError("Native parameter loading coverage missing")
    if model_id == FP8_MODEL_ID:
        if (any(loading.get(key) != value for key, value in precision(model_id).items())
                or loading.get("execution") != "native_fp8"
                or loading.get("backend") != "triton_block_fp8"
                or type(loading.get("fp8_linear_modules")) is not int
                or loading["fp8_linear_modules"] <= 0):
            raise ValueError("Native FP8 execution coverage missing or dequantized")
