# softmax-cpu

CPU adaptation of [KernelBench 23_Softmax.py](https://github.com/ScalingIntelligence/KernelBench/blob/423217d9fda91e0c2d67e4a43bf62f96f6d104f1/KernelBench/level1/23_Softmax.py).
Source license is retained in LICENSE. No upstream scoring result transfers here.

Implement `compute(x, *, eps)` in a self-contained `implementation.py`. Return a
float32 NumPy array of the same shape. Preserve input values. Compute stable softmax along axis 1.
Use only NumPy, math and locally defined helpers. Source is reviewed/trusted;
the evaluator is not a security sandbox for model-produced arbitrary code.

The task JSON owns all six public inputs, seeds, layouts, numerical tolerances
and timing policy. Baseline and example candidate are separate from the scalar
double-precision oracle. The oracle uses math.fsum and is not editable by a
candidate. The task package and grader are content-frozen per comparison.

Each measured call actually runs compute and checks its output and input
preservation outside the timed region. Input generation, reference computation,
warmups, validation, process startup and profiling are excluded. Output allocation
inside compute is included. Samples use perf_counter_ns and report milliseconds.
Sum of per-case medians is only this task's fixed-suite objective, not a universal
score. Retain every per-case sample to inspect regressions. Repeated calls describe
a warm-cache CPU workload. No device synchronization is claimed.

All tests are public. This small subset cannot demonstrate production inference
speedup, memory savings, or GPU/NPU support. A fresh task version and device
qualification are needed for changed shapes, dtype, backend or timing.
