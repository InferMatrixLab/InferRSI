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

## Reading depth and supporting paths

The source paths in metadata identify selected evidence, not complete-file
reviews. The mechanism ranges above were read together with these supporting
paths at the same source revision on 2026-10-21.

| Supporting path | Actual reading depth |
|---|---|
| comfy_execution/graph_utils.py | Complete 155-line module; seven helper contract checks executed on the unchanged module |
| main.py | Selected prompt_worker and cleanup path, L330-L415 |
| comfy_execution/cache_provider.py | L1-L130 selected registry/key handling; remaining symbols used for navigation |
| nodes.py | L1581-L1633 and LoadImage.IS_CHANGED L1805-L1819; other symbols navigational |
| comfy/samplers.py | Selected sample paths L1238-L1275 and L1443-L1468 |
| tests/execution/test_execution.py | L1-L150, L476-L568, L594-L655, L800-L837 and L904-L936 plus test-name inventory; not executed |
| tests-unit/execution_test/test_execution_list.py | Complete 106-line test source; not executed |
| tests-unit/execution_test/test_cache_provider.py | L1-L100 and test names; not a full provider implementation audit or an executed suite |
| tests-unit/comfy_test/model_management_test.py | Complete 81-line test source; its Mock/FakeStream boundary does not qualify native residency |
| tests/inference/test_inference.py | L1-L140 to identify model/service requirements; not the full inference suite |
| .github/workflows/test-execution.yml | Selected CPU CI setup/test entry; workflow not executed |
| AGENTS.md | First 110 lines read as source material; no instructions executed |
| pyproject.toml and LICENSE | Selected project version/license metadata and license text; no implementation claim |

Other selected ranges remain bounded by the responsibility table. Symbol and
test-name inventories are navigation evidence, not deep reads; unlisted
provider storage, native allocator and custom-node implementations are not
promoted by this source-path inventory.
