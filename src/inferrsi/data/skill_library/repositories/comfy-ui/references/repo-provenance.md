# Source and scope

- Repository: [Comfy-Org/ComfyUI](https://github.com/Comfy-Org/ComfyUI).
- Source revision: `b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c`.
- Package metadata version: `0.42.0`.
- Source access date: 2026-10-21.
- Input: immutable source-reading archive, not a working Git checkout; no local
  branch, dirty-state or installed-package equivalence is inferred.
- License: upstream [GNU GPL version 3](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/LICENSE#L1-L6).
  The original license is retained as `../LICENSE`. This owner distills the
  mechanisms in new prose; it does not vendor ComfyUI implementation code.
- Metadata evidence:
  [pyproject.toml](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/pyproject.toml#L1-L6).

## Inspected responsibility layers

| Layer | Readset | Coverage |
|---|---|---|
| Submission and caller defaults | `server.py:1161–1227`, `main.py:330–377` | Validation/queue/executor connection; worker cache selection |
| Cache identity | `execution.py:65–154`, `comfy_execution/caching.py:17–218` | Output signatures, node-object IDs, fingerprints and classic cleanup |
| Scheduling and completion | `execution.py:439–647,733–846`, `comfy_execution/graph.py:23–73,145–183,217–319` | Cache hits, lazy pending, expanded subgraphs, local consumer references and prompt cleanup |
| Retention and external-cache boundary | `comfy_execution/caching.py:223–345,440–568`, `comfy_execution/cache_provider.py:56–114` | Policy versus key; external NaN/unknown-key guard; not provider storage implementations |
| Model loading | `nodes.py:1581–1632`, `comfy/sample.py:79–84`, `comfy/samplers.py:1240–1274,1443–1463`, `comfy/sampler_helpers.py:165–214` | Sampler entry, memory estimate, managed load and cleanup boundary |
| Weight residency | `comfy/model_management.py:771–858,893–1038`, `comfy/model_patcher.py:51–92,1150–1189,1276–1302,1771–1840,2064–2185` | LoadedModel, partial/full unload and static/dynamic differences |
| Native candidate evidence | `tests/execution/test_execution.py:481–566,600–651,810–831,915–935`, `tests-unit/execution_test/test_execution_list.py`, selected `test_cache_provider.py`, `tests-unit/comfy_test/model_management_test.py`, CI and requirements | Assertions inspected; complete executor/device suites not executed |

The archive omits 12 assets, including tokenizer data, documentation pictures
and `input/example.png`. None is a selected mechanism implementation file;
their absence still prevents treating the archive as a complete model-runtime
installation. Frontend/Desktop, third-party custom nodes, all model families,
database/assets internals and hosted API providers are outside this readset.

## Reference reuse

AREX-Skill's existing `comfy-ui` skill was consulted as a structural reference.
Its provenance cites `0d8b7510bdc5409f4a76c3191e122ddea50f4aa2` / `0.25.0`.
It is not evidence for this pin. No server/custom-node/model-setup tutorial or
validator implementation was copied. In particular, its link classifier accepts
numeric node IDs while the pinned `graph_utils.is_link` requires a string ID;
its integer-only socket rule also differs from that low-level predicate. Neither
predicate alone proves that a link passes runtime node-schema validation.

This candidate is source grounded and locally unvalidated as an executor or
device-residency procedure. Seven self-authored contract cases executed the
unchanged pure `graph_utils.py` module; they cover only syntactic link/build/
prefix/blocker helpers, not cache correctness, model quality or performance.
