# FlashInfer all-M prefill candidate: analytically deferred

InferRSI Issue67; model-plane opt-in candidate; INCONCLUSIVE for GPU, quality and E2E performance. Preserve this attempt even though it is not selected for GPU execution.

The explicit flashinfer_all option sends both small-M decode and large-M prefill to the installed FlashInfer SM90 API while preserving original E4M3weights/FP32multipliers and the existingdefault/small-M-only modes. Exactstagedtree4983aa6ada4154df368b1471ce0af0df1c342526 is based on8859ef319486eb5ed4a444fc66c1018cbebbab33. Patchsha2565899d910e7cebc64a2ca2afa87927d3225062210eb81ab4915cdc6fb2adc9cb1 is retained privately. No commit/PR or GPU run has been made for this slice.

CPUjob2079 COMPLETED0:0 in14seconds,8CPUs/0GPU,released;114tests passed in10.71seconds. Independent review found no added dispatch/shape/scale/no-fallback/provenance defect. The installedPythonAPI acceptslargeM. The internalnormalGEMM/quantizer C++implementation has not been completely reviewed.

Counter-signal: pinnedvLLM0.32 source5df63a7203cdb9328d824a27b682e77c7b9928be, vllm/model_executor/kernels/linear/scaled_mm/flashinfer.py245-248, explicitly reports a DeepSeek-V3.1 GSM8K accuracy regression for FlashInferlargeM and uses separateDeepGEMM atM>=32. This is an upstream different-model observation, not a measured Qwen3.8failure; nevertheless it is a concrete reason to prioritize the originalDeepGEMM plan before spendingGPUtime here.

Do not extrapolate2076'ssmall-Mmicrobench: itsM32row actuallyusedTriton. No all-M GPUoutput or modelquality result exists. Parentdisposition: analyticallydefer; retainpatch/CPUevidence and sourcecounter-signal. Revisitonlywithprospectivelybounded numerical and taskquality controls. ThisdoesnotweakenIssue67qualitygates or claimFIlargeMisuniversallyinvalid.
