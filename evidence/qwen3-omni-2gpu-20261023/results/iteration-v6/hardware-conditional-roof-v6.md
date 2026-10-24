# Conditional hardware envelopes (read-only follow-up)

These are conditional architecture-and-telemetry calculations, not a verified L20X SKU specification or attainable application throughput. No CUDA context or kernels were launched for this follow-up.

## Observations and discrepancy

Direct NVML queries on both assigned devices report CUDA capability 9.0, memory bus width 6144 bits, maximum memory clock 3201 MHz, and maximum SM clock 1980 MHz. Previously retained nvidia-smi compute_cap output reported 8.9. Thus the discrepancy is between that nvidia-smi field and direct NVML/CUDA-runtime observations, not between NVML as a whole and CUDA. Its cause is unknown. Earlier parent-owned CUDA runtime observations report 132 SMs and 60 MiB L2; successful sm90-compiled parity execution also supports capability compatibility. These do not identify a retail GPU SKU.

Installed <PATH_26> documents cudaDevAttrClockRate (line 1932, kHz), MultiProcessorCount (1935), MemoryClockRate (1955, kHz), and GlobalMemoryBusWidth (1956, bits). Inspecting declarations alone does not obtain or validate hardware values. No CUDA runtime queries were performed here.

## Conditional memory interface ceiling

NVIDIA CUDA Best Practices gives DDR theoretical bandwidth as clock Hz times bus width in bytes times two. If the reported memory clock has this interpretation and all reported bus bits are active:

3201e6 * 2 * 6144 / 8 = 4.916736e12 bytes/s = 4.916736 TB/s per GPU.

This excludes protocol/ECC overhead and is not sustained bandwidth. It should not be called a verified L20X theoretical limit without confirming telemetry semantics. The parent-measured read-plus-write copy envelope of about 4.265 TB/s is compatible with this conditional value but cannot validate it.

Source: https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html (Bandwidth / Theoretical Bandwidth Calculation).

## Conditional dense BF16 Tensor Core envelope

The official Ampere whitepaper documents four Tensor Cores per A100 SM and 256 FP16 FMA per Tensor Core per cycle: 2048 FLOP per SM per cycle, counting FMA as two operations. NVIDIA's Hopper architecture article states twice the previous tensor-type throughput per SM clock-for-clock and equal BF16/FP16 Tensor Core rates. Assuming the measured device implements that standard Hopper dense tensor datapath, its conditional rate is 4096 dense BF16 FLOP per SM per cycle:

132 * 1.98e9 * 4096 = 1.07053056e15 FLOP/s = 1070.53056 TFLOP/s per GPU.

This is dense BF16, not the doubled structured-sparsity rate or FP8 rate. Compute capability 9.0 establishes ISA compatibility; it does not alone certify enabled tensor throughput or simultaneous sustainable clock. Therefore the expression is defensible as an explicitly conditional architecture envelope, not an unconditional device-specific numerical upper bound. Parent empirical square-GEMM medians around 780–788 TFLOP/s remain operation-specific envelopes.

Sources:
- https://images.nvidia.com/aem-dam/en-zz/Solutions/data-center/nvidia-ampere-architecture-whitepaper.pdf (SM / third-generation Tensor Core discussion, pages 19 and 23).
- https://developer.nvidia.com/blog/nvidia-hopper-architecture-in-depth/ (Hopper Tensor Core throughput and BF16 support).

The same Hopper article distinguishes full GH100 geometry from H100 SXM product geometry. Matching selected attributes is insufficient to substitute an H100/H200 datasheet for L20X. No verified official L20X SKU datasheet was identified.

## Use in the Qwen3-Omni ceiling analysis

Use these values only as an additional optimistic sensitivity scenario, alongside the measured operation envelopes. They do not predict achieved model latency. Kernel shapes, small GEMMs, routing, memory reuse, clock behavior, synchronization, serial stages and codec work remain limiting factors. Do not add two GPU peaks for work confined to the speech GPU. The defensible conclusion is that a conditional numerical envelope is available; an unconditional SKU-specific theoretical peak remains unverified.
