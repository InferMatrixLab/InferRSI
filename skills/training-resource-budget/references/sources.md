# Cross-resource reference evidence

Inspected 2026-10-15. No hardware, dependency installation, benchmark or
checkpoint implementation investigation was performed.

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

Historical original GitCode `core_r0.8.0` documentation; short history ID
`53193db8`, full immutable revision unresolved. The case is linked directly
from SKILL.md. Implementation, current compatibility and historical document
license remain unresolved. Only an independently written mechanism/evidence
account is included; no implementation text or headline percentage is copied.

## Evidence distinctions

DeepSpeed configuration is source code plus matched field documentation.
Stas material is attributed expert methodology. MindSpeed is a historical
author-described case. None is a measured InferRSI gain, a runtime qualification
or an automatic authorization to execute the original runbooks.
