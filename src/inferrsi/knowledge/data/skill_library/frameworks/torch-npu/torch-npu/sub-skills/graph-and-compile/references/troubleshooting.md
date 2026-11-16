# Graph and compiler troubleshooting

| Failure | Recovery |
|---|---|
| Capture demands a non-default stream | Use the graph context's managed side stream; join warmup work first. |
| `TASK_QUEUE_ENABLE=2` rejected | Select a supported queue mode in a fresh process; retain the changed execution contract. |
| `pin_memory_expandable_segments` rejected | Remove the incompatible startup option or avoid that capture workload; do not bypass the private-pool guard. |
| Replay returns old values | Update the original static storage in place; ensure the copy precedes replay and inspect retained output aliases. |
| `backend="npu"` succeeds without compiler activity | Check TorchAir presence and eager-fallback warning; do not report compiler acceleration. |
| Triton/MLIR/DVM/NPUGraph-EX import failure | Check the selected route's optional build/runtime packages; a successful eager import does not qualify it. |
| Unexpected recompilation | Compare shape/stride/dtype and state guards before changing cache settings. |
| FXRT output or view alias issue | Preserve input/output alias contract and compare a bounded view-disabled run; record IR and exact build. |

Restore a known-correct eager path while preserving the original failure.
Do not hide graph failures with a performance conclusion drawn from fallback.
