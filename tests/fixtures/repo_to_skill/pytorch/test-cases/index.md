# PyTorch usability cases

All cases grade operating guidance, not empirical agent efficacy. Synthetic integration cases combine evidence because no single short safe native test covers these exact multi-route failure combinations. Native-derived cases retain source patterns without copying entire harnesses.

| Case | Target | Origin |
| --- | --- | --- |
| [sub-skills/installation-and-build/wheel-versus-source-build](sub-skills/installation-and-build/wheel-versus-source-build/user_request.txt) | installation-and-build | synthetic |
| [sub-skills/tensor-dispatch-autograd/detached-alias-and-jagged-offsets](sub-skills/tensor-dispatch-autograd/detached-alias-and-jagged-offsets/user_request.txt) | tensor-dispatch-autograd | synthetic |
| [sub-skills/training-and-data/amp-loader-attention-interaction](sub-skills/training-and-data/amp-loader-attention-interaction/user_request.txt) | training-and-data | synthetic |
| [sub-skills/compiler-and-export/recompilation-and-export-range](sub-skills/compiler-and-export/recompilation-and-export-range/user_request.txt) | compiler-and-export | synthetic |
| [sub-skills/memory-streams-and-graphs/allocator-race-and-replay](sub-skills/memory-streams-and-graphs/allocator-race-and-replay/user_request.txt) | memory-streams-and-graphs | synthetic |
| [sub-skills/distributed-and-checkpoint/dcp-trust-and-sharded-resume](sub-skills/distributed-and-checkpoint/dcp-trust-and-sharded-resume/user_request.txt) | distributed-and-checkpoint | synthetic |
| [sub-skills/profiling-and-debugging/trace-overhead-and-enqueue-time](sub-skills/profiling-and-debugging/trace-overhead-and-enqueue-time/user_request.txt) | profiling-and-debugging | synthetic |
| [sub-skills/custom-operators-and-extension/fake-strides-versus-gradcheck](sub-skills/custom-operators-and-extension/fake-strides-versus-gradcheck/user_request.txt) | custom-operators-and-extension | synthetic |
| [root/backend-snapshot-routing](root/backend-snapshot-routing/user_request.txt) | pytorch | synthetic |
| [integration/sharded-compiled-amp-resume](integration/sharded-compiled-amp-resume/user_request.txt) | pytorch | synthetic-cross-route |
| [integration/custom-attention-capture-export](integration/custom-attention-capture-export/user_request.txt) | pytorch | synthetic-cross-route |
| [sub-skills/tensor-dispatch-autograd/native-gradcheck-pattern](sub-skills/tensor-dispatch-autograd/native-gradcheck-pattern/user_request.txt) | tensor-dispatch-autograd | native-derived |
| [sub-skills/training-and-data/native-dataset-size-mismatch](sub-skills/training-and-data/native-dataset-size-mismatch/user_request.txt) | training-and-data | native-derived |
| [sub-skills/compiler-and-export/native-invalid-export-bound](sub-skills/compiler-and-export/native-invalid-export-bound/user_request.txt) | compiler-and-export | native-derived |
| [sub-skills/memory-streams-and-graphs/native-record-stream-pattern](sub-skills/memory-streams-and-graphs/native-record-stream-pattern/user_request.txt) | memory-streams-and-graphs | native-derived |
| [sub-skills/distributed-and-checkpoint/native-safe-state-roundtrip](sub-skills/distributed-and-checkpoint/native-safe-state-roundtrip/user_request.txt) | distributed-and-checkpoint | native-derived |
| [sub-skills/profiling-and-debugging/native-finite-schedule](sub-skills/profiling-and-debugging/native-finite-schedule/user_request.txt) | profiling-and-debugging | native-derived |
| [sub-skills/custom-operators-and-extension/native-stride-error](sub-skills/custom-operators-and-extension/native-stride-error/user_request.txt) | custom-operators-and-extension | native-derived |
