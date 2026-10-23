# Source notices

This candidate distills `lithos-ai/lithos-metal` at
`6653b7df5f2c4392ec7b038960f2796b1499923f` (Apache-2.0). The owner-local
[LICENSE](../LICENSE) is preserved from that snapshot. The
[upstream third-party registry](upstream-notice.md) and [MLX license](mlx-license.md)
are preserved verbatim; retaining them does not claim that this skill copies
every listed implementation. No Metal kernel or model weights are bundled.

The task compiler/runtime implementation is standalone. Upstream acknowledges
MPK/Mirage design influence, attributed registry/module/model fragments,
MLX-derived format/kernel fragments, Transformers numerical conventions and
DeepSpec DSpark semantics. Those provenance relationships must not be erased
when adapting upstream code. This guide's small software diagnostic is new
glue around the pinned public Python contracts, not an upstream script rename.

The extraction/verification procedure was informed by VectorSpaceLab/AREX-Skill
at `ac3fe1afa80fb9a09775ecfb2b6cc3ba850a2db6`, specifically its
`create-repo-skill`, `prepare-repo-skill-env` and `verify-repo-skill` workflows.
The user's contribution destination is InferRSI, so this graph uses InferRSI's
registry and two matrices. It makes no live DisCo import, router deployment or
cross-agent export claim.
