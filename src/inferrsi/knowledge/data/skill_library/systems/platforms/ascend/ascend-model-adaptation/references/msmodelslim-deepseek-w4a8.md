# Selecting a DeepSeek mixed-W4A8 checkpoint for an Ascend loader

Source review of Ascend/msmodelslim at `d4ee30cb6ed97448f79c80652db6ec0f911a47f9`. Scope is the DeepSeek-V3.1 example export path. `empirical_validation: not_run`. The observations below come from inspecting the upstream files. Loader compatibility, model quality and service performance remain unmeasured in InferRSI.

## Select the model, recipe and consumer together

The support table gives different recipes for DeepSeek-V3.1, V3.1-Terminus and V3.2-Exp. For **V3.1 W4A8**, the linked command uses `quant_deepseek_w4a8.py`, the V3.1 anti-outlier and calibration prompt files, and mixed multi-token prediction (MTP). V3.1-Terminus lists W8A8C8 and W4A4C8. V3.2-Exp has its own W4A8 command. Match all three identifiers (model revision, mode and exporter) before applying the mechanism below. The V3 preflight in this revision specifies Transformers 4.48.2 and model-specific preparation. [Support table][matrix] · [V3 preflight][preflight] · [V3.1 recipe][recipe]

| Inspection point | What the pinned path does | What to record or reject |
| --- | --- | --- |
| Input dtype | The loader requests `torch_dtype="auto"` and calls the FP8-to-BF16 helper before calibration. Forced FP8 requires matched scale entries. Forced BF16 skips conversion. Auto mode can skip on an empty scale list or warn on a shard/index mismatch. [Loader][load] · [Conversion helper][convert] | Record checkpoint and shard-index identity, original dtype and conversion mode. Stop on missing or mismatched weight/scale pairs for a declared FP8 input. A completed auto path alone cannot establish the input dtype. |
| Calibration | The two JSON prompt lists have different consumers. The anti-outlier pass uses `m4` on the first list. The calibrator receives the second list with the mixed configuration. Both lists are split into chunks of up to 512 **characters** before tokenization, then batched and padded. [Batch builder][batch] · [Consumers][mix] | Record both dataset digests, tokenizer revision, batch size and actual token lengths. Keep quality evaluation prompts independent of these two inputs. A 512-token truncation changes the input. |
| Layer precision | The module map selects dynamic W4A8 for routed main-model experts, dynamic W8A8 for shared experts and the first three dense MLPs, and W8A8 for attention. Per-layer `self_attn.kv_b_proj` is excluded. Mixed MTP has separate expert and exclusion rules. [Module map][mix] | Inspect one tensor description from each applicable class and the declared MTP mode. A single top-level dtype or a reduced-layer export cannot establish the full model layout. |
| Backend packaging | The default branch saves `ascendV1` with `quant_model_description.json` and the vLLM config hook. With `--mindie_format`, it selects `safe_tensor`, a differently named description and the MindIE config hook. The README describes this compatibility flag for MindIE 2.1.RC1 and earlier. Both branches set the summary `model_quant_type` to `W8A8_DYNAMIC` even with mixed W4A8 experts. [Flag scope][flags] · [Exporter][save] · [Config writers][hooks] | Record the serving engine and plugin versions, hardware, format switch, description filename and per-layer entries. Reject a loader/format mismatch or an inference about all weights from the summary field. |

## Checks and fallback

1. **Reproduce the source review without a device.** At the pinned revision, follow the V3.1 W4A8 row through the linked command to `main()`. Trace the two JSON inputs to their distinct consumers, then trace the module map, both save branches and both config hooks. Cross-check the V3.1-Terminus row as a negative example. This verifies what the exporter requests.
2. **Quality gate for a future authorized run.** Preserve the original checkpoint and loader configuration. Stage the export separately. With real weights and all layers, require a successful load by the intended consumer and compare held-out task outputs against the original under the same tokenizer, prompts, decoding parameters and MTP mode. Use the acceptance issue's predeclared quality bar.
3. **Performance gate for a future authorized run.** Only after the quality gate, compare both variants on the same device topology, serving stack, request mix, sequence lengths, concurrency and warm-up policy. Judge the requested service metrics against the issue's frozen gates. On a failed load or quality regression, restore the original checkpoint/configuration. Record a failed performance gate separately. Missing baseline or incompatible conditions leave the comparison inconclusive.

## Attribution

The exporter and conversion helper carry Huawei Technologies' 2026 MulanPSL-2.0 notices. The repository distinguishes product code from CC BY 4.0 documentation under `docs/`. The package also lists component-specific terms, including Apache-2.0, BSD-3-Clause, MIT and NOASSERTION entries. Check the separate terms for any model weights, tokenizer, data or third-party code before reuse. This reference contains original source analysis. [Product license][license] · [Documentation notice][docs-license] · [Third-party notice][third-party]

[matrix]: https://github.com/Ascend/msmodelslim/blob/d4ee30cb6ed97448f79c80652db6ec0f911a47f9/example/DeepSeek/README.md#L35-L50
[preflight]: https://github.com/Ascend/msmodelslim/blob/d4ee30cb6ed97448f79c80652db6ec0f911a47f9/example/DeepSeek/README.md#L190-L200
[recipe]: https://github.com/Ascend/msmodelslim/blob/d4ee30cb6ed97448f79c80652db6ec0f911a47f9/example/DeepSeek/README.md#L259-L265
[flags]: https://github.com/Ascend/msmodelslim/blob/d4ee30cb6ed97448f79c80652db6ec0f911a47f9/example/DeepSeek/README.md#L108-L121
[load]: https://github.com/Ascend/msmodelslim/blob/d4ee30cb6ed97448f79c80652db6ec0f911a47f9/example/DeepSeek/quant_deepseek_w4a8.py#L185-L238
[convert]: https://github.com/Ascend/msmodelslim/blob/d4ee30cb6ed97448f79c80652db6ec0f911a47f9/example/DeepSeek/convert_fp8_to_bf16.py#L117-L154
[batch]: https://github.com/Ascend/msmodelslim/blob/d4ee30cb6ed97448f79c80652db6ec0f911a47f9/example/DeepSeek/quant_deepseek_w4a8.py#L103-L128
[mix]: https://github.com/Ascend/msmodelslim/blob/d4ee30cb6ed97448f79c80652db6ec0f911a47f9/example/DeepSeek/quant_deepseek_w4a8.py#L242-L293
[save]: https://github.com/Ascend/msmodelslim/blob/d4ee30cb6ed97448f79c80652db6ec0f911a47f9/example/DeepSeek/quant_deepseek_w4a8.py#L296-L338
[hooks]: https://github.com/Ascend/msmodelslim/blob/d4ee30cb6ed97448f79c80652db6ec0f911a47f9/example/common/copy_config_files.py#L43-L95
[license]: https://github.com/Ascend/msmodelslim/blob/d4ee30cb6ed97448f79c80652db6ec0f911a47f9/LICENSE
[docs-license]: https://github.com/Ascend/msmodelslim/blob/d4ee30cb6ed97448f79c80652db6ec0f911a47f9/docs/en/legal/license_notice.md
[third-party]: https://github.com/Ascend/msmodelslim/blob/d4ee30cb6ed97448f79c80652db6ec0f911a47f9/msmodelslim/Third_Party_Open_Source_Software_Notice
