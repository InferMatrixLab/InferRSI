# Qwen3.8-Flash-Next on four H200 SXM GPUs

This worked example prices one text request at published H200 SXM rates. It
checks the stored tensors used by the text decoder and follows the NVIDIA
implementation in vLLM 0.32.0. The report keeps the whole-model qualified bound
and measured latency unavailable. [Model config](https://huggingface.co/Qwen/Qwen3.8-Flash-Next/blob/812d96e10a0dd82b69d749e68693698cf6c36daa/config.json) · [vLLM decoder](https://github.com/vllm-project/vllm/blob/5df63a7203cdb9328d824a27b682e77c7b9928be/vllm/models/qwen4_exp/nvidia/model.py#L178-L361)

## Reproduce

From the repository root, run the standard-library driver. The second command
also verifies the pinned config and index and reads the headers of all 131
safetensors shards with HTTP byte-range requests. The offline replay uses the
recorded digest of the observed names, shapes and dtypes. [Inputs and source digests](qwen38-h200-tp4.json)

```bash
skill=src/inferrsi/knowledge/data/skill_library/playbooks/measurement/model-sol-analysis
python3 "$skill/scripts/qwen38_h200_tp4.py" --prompt-tokens 8192 --output-tokens 256
python3 "$skill/scripts/qwen38_h200_tp4.py" --prompt-tokens 8192 --output-tokens 256 --verify-hub-headers
```

## Workload and layout

- One 8,192-token prompt, one prefill chunk, 256 output tokens, batch one, no prefix reuse, language-model-only mode and MTP disabled. Prefill emits the first token. The 255 following forwards have visible lengths 8,193 through 8,447, including the token being processed.
- One four-GPU node, TP4 and embedding TP4, with PP, context, data and expert parallel degrees of one. HC and MoE sequence parallelism are disabled. Each TP rank processes shards of the same ten selected experts per token. For prefill the driver evaluates both extrema for the number of distinct experts touched per layer. Routing skew and padding still affect kernel efficiency. [MoE layout](https://github.com/vllm-project/vllm/blob/5df63a7203cdb9328d824a27b682e77c7b9928be/vllm/model_executor/models/qwen3_next.py#L125-L259)
- Weights, activations, main KV, index KV and convolution state use BF16. The GDN temporal matrix uses FP32. The n-gram embedding is GPU-resident and vocabulary-sharded. The four residual streams have replicated projection weights on this path. [N-gram placement](https://github.com/vllm-project/vllm/blob/5df63a7203cdb9328d824a27b682e77c7b9928be/vllm/models/qwen4_exp/nvidia/ngram_embedding.py#L178-L240) · [Residual projections](https://github.com/vllm-project/vllm/blob/5df63a7203cdb9328d824a27b682e77c7b9928be/vllm/models/qwen4_exp/nvidia/hyperconnection.py#L90-L134)
- Per GPU, use about 989.5 TFLOP/s dense BF16 (half the advertised 1,979 with structured sparsity), 4.8 TB/s HBM and 450 GB/s outgoing NVLink (half the advertised bidirectional bandwidth). The capacity screen uses the nominal 141 GB in decimal units. These device specifications supply ideal rates. Actual clocks and effective rates require target evidence. [H200 SXM specifications and sparsity footnote](https://www.nvidia.com/en-us/data-center/h200/) · [Hopper NVLink direction convention](https://www.nvidia.com/en-us/data-center/technologies/hopper-architecture/)

## Counts

The 1,658 checkpoint entries contain 359,999,963,128 stored bytes. The driver
derives names, dtypes and shapes for the 1,294 text tensors, including the
output projection and 128 n-gram shards. The optional audit compares them
against the published headers in both directions. The other 364 entries belong
to vision and MTP. The header audit verifies metadata only. [Checkpoint index](https://huggingface.co/Qwen/Qwen3.8-Flash-Next/blob/812d96e10a0dd82b69d749e68693698cf6c36daa/model.safetensors.index.json) · [Language-model-only loading](https://github.com/vllm-project/vllm/blob/5df63a7203cdb9328d824a27b682e77c7b9928be/vllm/models/qwen4_exp/nvidia/model.py#L987-L1013)

The resident ledger divides stored axes according to their placement, including
partial KV-head replication and n-gram vocabulary ownership. `rank_logical_weight_bytes`
counts checkpoint-format logical payload before kernel repacking, internal
padding and dtype conversion. Real fit also depends on the KV pool, scratch
buffers, CUDA graphs and allocator reserves. [Tensor ledger](../scripts/qwen38_h200_tp4.py)

For the 12 QSA layers, one main KV head resides on each TP rank. The index stores
one compressed key per completed four-token group and a separate four-row raw
key ring. Language-model-only mode strips MRoPE. The 36 GDN layers retain fixed
temporal and convolution states. The PLE convolution retains its dilated
history. The cache report gives logical state payload for one live sequence.
[QSA head placement](https://github.com/vllm-project/vllm/blob/5df63a7203cdb9328d824a27b682e77c7b9928be/vllm/models/qwen4_exp/nvidia/qsa.py#L389-L429) · [Indexer caches](https://github.com/vllm-project/vllm/blob/5df63a7203cdb9328d824a27b682e77c7b9928be/vllm/models/qwen4_exp/common/qsa_cache.py#L815-L877) · [Text-only RoPE and GDN dtype configuration](https://github.com/vllm-project/vllm/blob/5df63a7203cdb9328d824a27b682e77c7b9928be/vllm/model_executor/models/config.py#L851-L949) · [GDN state shapes](https://github.com/vllm-project/vllm/blob/5df63a7203cdb9328d824a27b682e77c7b9928be/vllm/model_executor/layers/mamba/mamba_utils.py#L280-L302) · [PLE state](https://github.com/vllm-project/vllm/blob/5df63a7203cdb9328d824a27b682e77c7b9928be/vllm/models/qwen4_exp/nvidia/ple_layer.py#L91-L96)

## Interpret the phase output

| Resource | Counted demand per rank |
| --- | --- |
| Compute | Two FLOPs per useful dense multiply-add across the text projections, ten routed experts and one shared expert per token, and one logits row per forward. QSA QK/AV covers the selected rows and the causal tail. The index score counts dots against complete four-token groups. Arithmetic is priced in dense BF16 equivalents. |
| HBM | One stream of each distinct matrix per forward. Prefill counts two scenarios with 10 or 512 distinct routed experts per layer at the given length. Each QSA query writes its new main KV row. Decode streams selected main KV rows and reads compressed index keys once. GDN writes the final recurrent matrix after prefill and reads and writes it once per decode step. |
| NVLink transmit | 96 decoder hidden-state reductions per forward in the assumed ring schedule. Each of the four ranks sends 1.5 times the BF16 payload per reduction. The model allows zero startup time. |

The QSA token selection counts complete blocks up to the 2,048-token budget
plus the open group's tail. The retained main KV grows with the full context.
[Sparse index expansion](https://github.com/vllm-project/vllm/blob/5df63a7203cdb9328d824a27b682e77c7b9928be/vllm/models/qwen4_exp/nvidia/ops/qsa_indexer.py#L232-L276) · [Index projection and precision](https://github.com/vllm-project/vllm/blob/5df63a7203cdb9328d824a27b682e77c7b9928be/vllm/models/qwen4_exp/nvidia/indexer_qsa.py#L115-L164)

`resource_max_s` is the largest of the three resource times for the counted
work. `serial_group_s` sums the largest resource time of each modeled family.
Families aggregate layers and can contain several kernels. The mean decode
rate divides the 255 emitted tokens by the summed decode reference times.
`request_resource_s` adds the prefill reference for each routing scenario.

The timing omits GDN recurrence arithmetic, QSA top-k selection and
intermediate traffic, repeated prefill KV reads, embedding/PLE lookup traffic
and reductions, logits gathering, activation and normalization traffic,
allocator behavior, launch overhead and scheduling. The grouped time also
depends on fusion, cache reuse and overlap. A complete fused graph and
device evidence are needed to turn these scenario calculations into a
qualified bound or a calibrated latency or throughput estimate.
