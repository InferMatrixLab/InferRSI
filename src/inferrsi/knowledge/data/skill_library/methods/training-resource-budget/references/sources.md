# Cross-resource reference evidence

Initial scoped inspection: 2026-10-15. CR5 historical-source follow-up:
2026-10-30. No hardware, dependency installation, benchmark or checkpoint
implementation investigation was performed.

## CR1 — DeepSpeed

- Implementation: [offload_config.py](https://github.com/deepspeedai/DeepSpeed/blob/5f266e26d216a705d9c64cac88fb813cefdbac4b/deepspeed/runtime/zero/offload_config.py),
  whole short configuration file (parameter config 20–51, optimizer config
  54–111). Revision `5f266e26d216a705d9c64cac88fb813cefdbac4b`.
- License: Apache-2.0, confirmed by file header and downloaded root LICENSE.
  Mechanisms are paraphrased; no source code copied.
- [Official ZeRO-3 docs](https://deepspeed.readthedocs.io/en/latest/zero3.html),
  offload overview and parameter/optimizer configuration fields only. Live
  `latest` HTML SHA-256:
  `56beb8cdf148ace7a279518e1abe8256fa767038b471b273aa8650e55b295f46`.
  Retrieved fields match the inspected config, including `pin_memory=True`;
  this is not a claim that the entire docs build matches the source SHA.
- `max_in_cpu` is explicitly parameter elements. `buffer_size` units are not
  defined in this approved config excerpt or its live field description;
  no runtime consumer was inspected, so no byte-budget formula or unsupported
  element-unit assertion is supplied for that field.
- `pipeline_read/write` descriptions establish intended tiled optimizer overlap,
  not dispatch or measured overlap. CPU Adam core share is gated by stage 3 and
  super-offload. No NVMe/pinned-memory support is inferred for NPU hardware.

## CR6 — Stas ML Engineering

Revision `ee7517e0f562ff0e7d56c3e88c619d0c0c496ba7`; approved skill and targeted
performance sections only. Exact citations, adaptation license and limitations
are in the sibling Stas decision note linked directly from SKILL.md.
The source skill declares CC BY-SA 4.0; root `LICENSE` URL returned 404, so
that declaration, not a guessed root file, supplies attribution evidence.
Compute/network scripts were identified but not fetched or executed.

## CR5 — MindSpeed

The 2026-10-15 inspection was historical GitCode documentation only, with short
history ID `53193db8` and unresolved full pin/license. The 2026-10-30 follow-up
resolved `53193db8bf5def407c4041a9beb3f4c9e9773daf` through the original commit
link and official Ascend/MindSpeed GitHub source. Its root LICENSE supplies
default BSD-3-Clause terms with identified third-party exceptions; no later
documentation license replaces that historical evidence.

The [historical case](mindspeed-historical.md) preserves the original date and
HTML hash. The [new bounded readset](mindspeed-source-readset.md) supports
selection versus validation, allocator/callback ownership, eligible shared-storage
rescue, explicit autograd-wrapper integration and conditional CPU-affinity
prerequisites. Complete search/cache behavior, current compatibility, numerical
correctness and measured benefit remain unqualified. Only independent mechanism
paraphrases are included; no upstream implementation or headline percentage is
copied.

## Evidence distinctions

DeepSpeed configuration is source code plus matched field documentation.
Stas material is attributed expert methodology. MindSpeed combines a historical
author-described case with bounded source observations at the recovered pin.
None is a measured InferRSI gain, a runtime qualification or an automatic
authorization to execute the original runbooks.
