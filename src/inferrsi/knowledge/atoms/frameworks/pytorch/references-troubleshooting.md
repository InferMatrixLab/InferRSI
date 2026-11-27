# Cross-cutting diagnosis

| Symptom | Discriminating observation | Recovery and owning route |
| --- | --- | --- |
| Import fails or wrong version appears | Run the environment inspector from outside the source checkout; compare distribution and `torch.version.git_version` | Select the intended interpreter, remove import shadowing, then installation/build; do not upgrade another environment automatically |
| CUDA unavailable although a toolkit exists | Compare compiled CUDA tag, runtime availability and driver/device visibility | Installation/build; a toolkit installation does not turn a CPU wheel into a CUDA wheel |
| Missing optional module | Identify the selected API (ONNX, NumPy interop, compiler, extension or profiler) | Install only its needed dependency in the selected environment; preserve a failed capability rather than relabeling CPU success |
| Tensor operation works eagerly but fails after compilation | Same inputs/state in eager, Dynamo eager backend, AOT eager, then Inductor | Compiler/export; record the first failing stage and logs |
| Outputs or gradients change with streams or replay | Compare single-stream eager, then stream waits and graph input addresses | Memory/streams; do not tune the allocator to hide a race |
| Loader hangs, repeats data, or uses excessive RAM | Retry `num_workers=0`; inspect iterable worker sharding and prefetched batches | Training/data; avoid lambdas under spawn and stop increasing workers blindly |
| Distributed job hangs | Earliest rank exception and collective index/signature across every rank | Distributed/checkpoint; increasing timeout is not a collective-order fix |
| Checkpoint fails to load | Distinguish torch.save state_dict, DCP, export archive, TorchScript and ONNX formats | Distributed/checkpoint plus compiler/export; these formats are not interchangeable |
| Legacy helper absent | Compare actual installed namespace with pinned readset | Never substitute historical commands from memory; choose the current public route |

Return the exact failed operation, minimal shape/dtype/layout/backend contract,
actual observed error, checks not run and next safe check. Record runtime support,
numerical correctness, measured performance and security assumptions separately.
