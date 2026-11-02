# Independent review of the PyTorch and TorchNPU operating graphs

Reviewer: Codex `independent_review`, separately delegated from the material authors. The reviewer did not edit protected material, the Git index or commits, and performed no GitHub mutation. Review artifacts are separate from material authorship.

Assessed source commit: `8115da15b9ef34978de500b08aa9f14ea790c35b`.
Assessed base: `f5a21bf0bd684fab70bfae02562076eb478bd627`.
Scope: the two new framework graphs and fixtures, shared registry/matrices/package-data integration, local-skill-v1 sidecar adaptation, source grounding, bounded scripts, claims, privacy and retained licenses. The scope is broad repository capability discovery with selected deep mechanisms, not every-line implementation or all-device qualification. Generated catalog confirmation is recorded separately after its final projection is available.

## Findings

No actionable source-content, helper, license, privacy or shared-integration findings were identified in the assessed source commit. No change request is issued for cosmetic wording. This conclusion is a bounded review result, not a guarantee of untested backend behavior.

The rebase onto the assessed base changed the two shared matrix documents relative to the earlier working-tree review snapshot. Inspection confirmed that it retained the new framework sections alongside the base's AutoTuneBench additions; the already reviewed graph and case bytes were unchanged. `source-commit-reviewed-hashes.json` records the 278 changed paths as exact committed blob SHA-256 values, including the byte-preserved upstream license exception.

## Prompt-first usability

Before opening fixture assertions, implementation tests or upstream source, the reviewer read only the fixture user prompts and installed-style library skills/references. The reviewer wrote concrete answers for 22 cases: each root, one synthetic case for each of eight sub-skills per repository, and both integrated cases for each repository. Answers were fixed before grading.

- PyTorch: 11 of 11 selected responses satisfied the semantic assertions, with no specific misses.
- TorchNPU: 11 of 11 selected responses satisfied the manually assessed task semantics, with no specific misses. Its fixture assertions are file-content `contains` checks; these were assessed separately and are not represented as automatic response grading.
- Fifteen additional fixture cases were not independently replayed. The selection covers every child route and both integration cases for both graphs.

The fixed answers are in `usability-answers.md`; `usability-grades.json` retains each prompt/assertion/answer identity, case-level assessment and the distinction between semantic grading and structural checks. This is actual textual procedure execution by an independent reviewer. It is not accelerator execution, a baseline-versus-skill effectiveness experiment, or evidence of model-quality or service gains.

## Source, procedure and integration checks

The complete declared identity ledgers were checked against the pinned read-only source repositories: 68 PyTorch files/97 recorded spans and 54 TorchNPU/op-plugin files/75 recorded spans, totaling 122 files and 172 spans. Immutable Git blob OIDs and SHA-256 values, recorded checkout hashes and normalized line/span equivalence matched. Byte identity verifies provenance; it does not assert that every hashed file was independently read in full.

Independent semantic source spot-checks included the following high-consequence mechanisms:

| Source area | Confirmed operating distinction |
| --- | --- |
| PyTorch `pyproject.toml`, `setup.py`, `cmake/EnvVarForwarding.cmake` | Current scikit-build-core/PEP517 build, Windows generator and forwarding controls versus legacy commands |
| PyTorch `torch/distributed/checkpoint/format_utils.py` | DCP conversion/readers explicitly use unrestricted load; `weights_only` protection is not inherited |
| PyTorch FSDP2 documentation | Optimizer after sharding; `model(x)` hooks; target mesh/state and grouping contract |
| PyTorch nested documentation and `torch/_library/custom_ops.py` | Shared jagged offsets, fresh/alias contracts, FakeTensor metadata and incoming backward strides |
| TorchNPU `dynamo/__init__.py` and import-contract test | Missing TorchAir can return eager execution; basic import must not preload compiler modules |
| TorchNPU `ProcessGroupHCCL.cpp` | Host future completion, end-event recording, consumer-stream wait and optional host blocking differ |
| TorchNPU `NPUGraph.cpp` and allocator sources | Non-default capture stream, task-queue and expandable pinned allocator guards; lifetime and reclamation boundaries |
| TorchNPU autocast source and profiler implementation | BCE guard and required memory timeline options; collection and analysis are separate states |
| Pinned op-plugin Add adapter and full extension example | Real dtype/broadcast/compatibility wrapper behavior versus the narrow equal-shape example and incomplete broadcast gradient |

The broad inventories and support references explicitly distinguish substantive inspection from discovery-only long tails and unfetched dependencies. The eight primary procedures per graph contain actionable prerequisites, outputs, steps, failure discrimination and recovery. Runtime references resolve without the original inspection checkout. Existing allocator, DCP and host-memory owners retain separate source identities; a new latest-source graph is not an implicit compatibility pairing or update to their evidence.

All 12 bundled Python scripts were inspected and parsed, 23 graph JSON files parsed, and 159 local Markdown links resolved. Helpers use bounded inputs, explicit device execution where relevant, and do not silently replace missing accelerators with CPU success. The declared cases and reports distinguish source-native tests, adapted installed-wheel helper runs, static assertions, blocked backends and unperformed efficacy measurements. The source and installed CPU package revisions remain distinct.

The local-skill-v1 adapter keeps name/description in frontmatter and repository license, invocation visibility and operating role in sidecars for all 18 skill documents. The AREX license-validator reports clearly retain the expected direct-final-tree mismatch and a separate successful scratch projection bound to the final resource hashes. No managed DisCo import is claimed. Registry membership adds only two roots; child procedures stay owner resources. Package-data changes retain script and notice resources.

Seven retained license/notice files matched exact pinned Git blob bytes. The single `op-plugin-LICENSE.txt -text` attribute preserves its original CRLF bytes through Git clean filtering; the raw-first hash comparison with a fallback for ordinary LF-equivalent text does not weaken the dedicated exact-license checks. The bounded scan of changed deliverables found no private path or credential-like pattern flags; manual review preserved public source attribution and did not identify private identifiers. This is not a universal secret-scanner guarantee.

`independent-static-checks.json` records the performed identity/link/AST/JSON/license checks and their zero failures. The reviewer separately ran the source-only integration selection:

```text
python -m pytest -q -p no:cacheprovider tests/test_pytorch_torchnpu_integration.py -k 'not catalog'
```

Result: eight selected tests passed, exit code 0; two catalog-dependent tests were deselected. A private temporary directory was supplied for isolation and is omitted here. This selection covered root/child registration, read-only bundle/resource bytes, retained licenses and bound adapter reports. The parent/integrator owns full-suite, installed-wheel and generated-catalog results; those are not counted as reviewer-executed tests.

## Limits and next validation

No CUDA, ROCm, MPS, XPU, Ascend/CANN, HCCL or optional compiler backend was executed by this reviewer. No full pinned-source build, native C++/CUDA/SYCL extension, model convergence, performance, service, distributed durability or deployment-consumer result is established. The author's recorded Windows Gloo/libuv failure remains a failure; the independent review does not clear it. The source-only candidate state and `BLOCKED_REQUIRED_BACKEND`/not-run limits are appropriate to the user-authorized portable destination.

On actual target infrastructure, first verify exact framework/plugin/runtime compatibility, then run the selected tiny device and original native cases for the relevant operator, stream/capture, AMP, collective and profiler paths. Qualify ONNX/AOT/optional compiler consumers and larger workloads separately. Completion of repository packaging or this review does not promote any of these untested scopes to PASS.
