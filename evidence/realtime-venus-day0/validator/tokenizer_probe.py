import json
import sys
from pathlib import Path

import transformers
from transformers import AutoTokenizer

if int(transformers.__version__.split(".")[0]) >= 5:
    from vllm_omni.engine.arg_utils import _register_omni_hf_configs

    _register_omni_hf_configs()

tokenizer = AutoTokenizer.from_pretrained(sys.argv[2], trust_remote_code=True)
texts = [
    "What is the capital of France? Answer briefly.",
    "Count from one to twenty using English words, separated by commas.",
    "请用中文介绍一下北京。",
    "你好，世界！这是一个实时语音测试。",
    "I'm ready. Don't stop—let's go!",
    "one\n\ntwo\tthree  12345",
    "你好🙂 café e\u0301 中文English混合",
    "<delegate>查一下天气</delegate><|turn_eos|>",
    "<|audio_start|><|audio_end|><image></image><|tts_bos|>",
]
result = {
    "transformers": transformers.__version__,
    "class": type(tokenizer).__name__,
    "ids": {text: tokenizer.encode(text, add_special_tokens=False) for text in texts},
}
Path(sys.argv[1]).write_text(json.dumps(result, ensure_ascii=False, indent=2))
