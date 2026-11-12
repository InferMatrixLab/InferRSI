# SPDX-License-Identifier: Apache-2.0
# Adapted from Qwen3-TTS, Copyright 2026 The Qwen team, Alibaba Group,
# and the HuggingFace Inc. team, and the attributed standalone reference.
"""Real CustomVoice text preparation, Talker/predictor execution and codec decode."""

import hashlib
import importlib.metadata
import inspect
import sys
from pathlib import Path


class SynthesisModel:
    def __init__(self, model_path):
        import numpy as np
        import torch
        import torch_npu  # noqa: F401 - registers the NPU backend before model loading
        from qwen_tts import Qwen3TTSModel

        self.torch = torch
        self.numpy = np
        torch.npu.set_device(0)
        torch.set_num_threads(4)
        self.wrapper = Qwen3TTSModel.from_pretrained(
            str(model_path),
            device_map="npu:0",
            dtype=torch.bfloat16,
            attn_implementation="sdpa",
            local_files_only=True,
        )
        self.wrapper.model.eval()
        if (
            self.wrapper.model.tts_model_type != "custom_voice"
            or self.wrapper.model.tts_model_size != "1b7"
        ):
            raise ValueError("The task requires the real 1.7B CustomVoice checkpoint")
        if next(self.wrapper.model.parameters()).dtype != torch.bfloat16:
            raise ValueError("BF16 model weights are required")
        self.speakers = {name.casefold() for name in self.wrapper.get_supported_speakers()}
        self.languages = {name.casefold() for name in self.wrapper.get_supported_languages()}
        runtime_sources = {}
        for component in (
            Qwen3TTSModel,
            type(self.wrapper.model),
            type(self.wrapper.model.speech_tokenizer),
        ):
            path = Path(inspect.getfile(component))
            runtime_sources[component.__module__] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.identity = {
            "runtime": {
                name: importlib.metadata.version(name)
                for name in ("qwen-tts", "transformers", "torch", "torch-npu")
            },
            "device": torch.npu.get_device_name(0),
            "dtype": "bfloat16",
            "attention": "sdpa",
            "runtime_source_sha256": runtime_sources,
            "engine_import_guard": "active",
            "sampling": self.wrapper._merge_generate_kwargs(),
        }
        self._assert_independent()

    def _assert_independent(self):
        blocked = {"vllm", "vllm_omni", "sglang", "sglang_omni", "qwen3_tts_engine"}
        found = [name for name in sys.modules if name.split(".", 1)[0] in blocked]
        if found:
            raise RuntimeError(f"Unexpected engine modules {found}")
        self.identity["engine_modules_loaded"] = found

    def generate(self, payload):
        """All request work stays on the single model-owner thread."""
        torch, wrapper = self.torch, self.wrapper
        torch.npu.set_device(0)
        torch.manual_seed(payload["seed"])
        torch.npu.manual_seed_all(payload["seed"])
        with torch.inference_mode():
            languages, speakers = [payload["language"]], [payload["voice"]]
            wrapper._validate_languages(languages)
            wrapper._validate_speakers(speakers)
            input_ids = wrapper._tokenize_texts([wrapper._build_assistant_text(payload["input"])])
            instruction = payload["instructions"]
            instruction_ids = (
                [wrapper._tokenize_texts([wrapper._build_instruct_text(instruction)])[0]]
                if instruction
                else [None]
            )
            options = wrapper._merge_generate_kwargs(max_new_tokens=payload["max_new_tokens"])
            codes, _ = wrapper.model.generate(
                input_ids=input_ids,
                instruct_ids=instruction_ids,
                languages=languages,
                speakers=speakers,
                non_streaming_mode=True,
                **options,
            )
            if len(codes) != 1 or codes[0].ndim != 2 or codes[0].shape[0] == 0:
                raise ValueError("Talker/code predictor emitted no complete codec frames")
            waveforms, sample_rate = wrapper.model.speech_tokenizer.decode(
                [{"audio_codes": codes[0]}]
            )
            torch.npu.synchronize()
        waveform = self.numpy.asarray(waveforms[0])
        if sample_rate != 24000 or waveform.ndim != 1 or not waveform.size:
            raise ValueError("Expected a nonempty 24 kHz mono waveform")
        if not self.numpy.isfinite(waveform).all():
            raise ValueError("Codec emitted nonfinite waveform samples")
        frames = int(codes[0].shape[0])
        pcm = (self.numpy.clip(waveform, -1, 1) * 32767).astype("<i2").tobytes()
        self._assert_independent()
        return {
            "pcm": pcm,
            "sample_rate": sample_rate,
            "codec_frames": frames,
            "finish_reason": "length" if frames >= payload["max_new_tokens"] - 1 else "stop",
        }

    def close(self):
        self.torch.npu.synchronize()
        del self.wrapper
        self.torch.npu.empty_cache()
