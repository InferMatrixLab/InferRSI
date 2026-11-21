# Inkling 2 Mini on Apple silicon: local adaptation and one RSI round

**RESULTS_HEADLINE**

[Inkling 2 Mini](https://huggingface.co/thinkingmachines/Inkling-2-Mini) is a
26B-total, MoE, looped transformer from Thinking Machines Lab (24 layers; the
first and last 6 run once, the middle 12 run three times; about 3.4B active
parameters, 5.4B effective with the loop). The release checkpoint is ModelOpt
NVFP4 experts with MXFP8 tail layers (about 20 GB) and does not load in Apple
runtimes directly. This page records how it was brought up on one Mac with
community conversions, which runtime was faster, and one InferRSI-style search
round on that runtime. Measurement rules follow the
[scheduling RSI lessons](scheduling-rsi-lessons.md) and the
[Apple silicon playbook](apple-silicon-playbook.md). Nothing here is an
InferRSI acceptance result.

## Machine and sources

- Apple M5 Max, 128 GB unified memory, macOS 27.0 (26A425).
- Labels: **measured** = run on this machine, raw logs in the maintainers'
  run directory (not published); **public** = model card or repository at the
  link given.

| Route | Weights | Runtime | Source |
| --- | --- | --- | --- |
| MLX | [mlx-community/Inkling-2-Mini-4bit](https://huggingface.co/mlx-community/Inkling-2-Mini-4bit) (17.3 GB) | mlx-lm from [ml-explore/mlx-lm#2086](https://github.com/ml-explore/mlx-lm/pull/2086) (`0c4c991`), mlx 0.32.4 | public |
| llama.cpp | [lmstudio-community/Inkling-2-Mini-GGUF](https://huggingface.co/lmstudio-community/Inkling-2-Mini-GGUF) Q4_K_M (17.5 GB) | llama.cpp main `418fe97`, Metal | public |

Not run: Ollama (not installed on the machine), vLLM/SGLang (no Apple
backend for this model), the variable-loop research model
`TML-d24-varloop-research` (released only in the ModelOpt format, no MLX or
GGUF conversion at the time).

## Bring-up

BRINGUP_ROWS

## Route comparison

ROUTE_TABLE

## RSI round

RSI_SECTION

## What we did not establish

LIMITS
