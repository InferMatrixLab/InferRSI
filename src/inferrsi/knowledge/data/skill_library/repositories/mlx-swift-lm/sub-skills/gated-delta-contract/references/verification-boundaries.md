# Native discriminators and evidence limits

The retained tests are source definitions, **not local successes**. They require
compatible Apple Swift/Xcode, the matched MLX Swift dependency and actual backend
execution. Source guidance uses Xcode testing rather than `swift test`. Nothing
here installs tooling or invokes original source examples; the bundled helper
provides only offline declaration support.

| Inspected source case | Falsifying signal and preserved boundary |
| --- | --- |
| [Multi-chunk versus single-chunk](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Tests/MLXLMTests/GatedDeltaTests.swift#L35-L82) | T=16 split at eight; carry FP32 state, evaluate outputs and compare maximum drift. A low-precision state roundtrip cannot be excused as the same state |
| [Nonmultiple Dk tail perturbation](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Tests/MLXLMTests/GatedDeltaTests.swift#L84-L124) | Dk=48; perturb only trailing dimensions 32–47 and require output to change; a shape flag alone cannot show all dimensions were used |
| [Compensated recurrent dot](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Tests/MLXLMTests/GatedDeltaTests.swift#L126-L161) | Dk=192 adversarial large-plus-unit terms; compare one carried-state element's actual bit pattern to a rounded reference; generic FP32 algebra is insufficient |
| [Differentiable ops](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Tests/MLXLMTests/GatedDeltaTests.swift#L163-L203) | T=40 crosses more than one recompute chunk; Q/K/V gradients must be finite and nonzero; one short forward says nothing about VJP propagation |
| [Ops versus requested kernel](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Tests/MLXLMTests/GatedDeltaTests.swift#L205-L258) | Compare Y and carried state by relative drift at T=40, not a universal absolute tolerance. `useKernel:true` can fall back; this body does not independently assert selected fused dispatch |
| [Q/K normalization near epsilon](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Tests/MLXLMTests/GatedDeltaQKNormTests.swift#L50-L143) | Tiny Qwen35 LLM/VLM and Qwen3Next layers compared per token to sum-based L2 reference across small magnitudes; not full-model quality |
| [Prefix checkpoint restore](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Tests/MLXLMTests/Qwen35MTPTests.swift#L324-L382) | Two-token layer, checkpoint after one, compare restored conv/recurrent pair with independent prefix run; preserve source precision-dependent tolerance, not an exact bitwise assertion |
| [Decode convolution](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Tests/MLXLMTests/Qwen35GDNDecodeBitwiseTests.swift) | Tiny FP16/BF16 conv output and conv-state comparison; conv-only bitwise evidence cannot qualify complete GDN, model or service |

Source test tolerances are tied to their definitions; they are not portable
acceptance thresholds or new local results. Requested kernel paths need actual
execution evidence, not an availability declaration or function argument.
The inspected core parity tests do not establish masked-output equivalence,
arbitrary strides or every dtype/head shape. A matched dependency's packing
behavior and real device execution remain separate open requirements.

Selected unit fixtures use tiny locally initialized tensors without downloaded
weights. That makes them good later native candidates, not CPU substitutes in
this environment. Full model integration tests can download checkpoints and
run for a long time; those require separate authorization and frozen controls.
Source CI configuration is also not evidence that this candidate ran those tests.

Missing compiler/backend/model evidence remains **BLOCKED_REQUIRED_BACKEND** and
the relevant conclusion unverified/INCONCLUSIVE. No helper/static assertion can
upgrade numerical, gradient, checkpoint, quality, fit or service scope to PASS.
