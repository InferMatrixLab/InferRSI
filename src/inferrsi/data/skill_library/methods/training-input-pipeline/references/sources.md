# Input pipeline reference evidence

Inspected 2026-10-15; direct pinned source reading, no runtime execution.
Dot B entry IDs preserved. All three downloaded root LICENSE files identify
Apache-2.0; this candidate paraphrases mechanisms and contains no copied code.

| Entry | Immutable source and inspected sections | Evidence / unresolved boundary |
|---|---|---|
| B1 NVIDIA/DALI | [pipeline.py](https://github.com/NVIDIA/DALI/blob/6fe47c48d3b0ca335f5e1afd3c77c750b2c7e041/dali/python/nvidia/dali/pipeline.py#L97-L174), constructor docs; [executor_statistics, 621–644](https://github.com/NVIDIA/DALI/blob/6fe47c48d3b0ca335f5e1afd3c77c750b2c7e041/dali/python/nvidia/dali/pipeline.py#L621-L644); deserialize queue handling 1748–1760 | Python API and backend binding only. Queue gates and statistics source-supported; C++ executor and current hardware performance untested. Dot B's 1700–1780 hint points to serialization in this pin; exact statistic symbol was located in the same approved file. |
| B2 mosaicml/streaming | [dataset.py configuration, 263–273](https://github.com/mosaicml/streaming/blob/d99bf9c7cdf2dd4ed62a4960ed35270b93337a5f/streaming/base/dataset.py#L263-L273); cache checks 502–520; [admission/eviction, 1129–1188](https://github.com/mosaicml/streaming/blob/d99bf9c7cdf2dd4ed62a4960ed35270b93337a5f/streaming/base/dataset.py#L1129-L1188); prepare/ready/yield 1330–1473 | Sample-count target and separate readiness verified. `get_max_size()` reserves compressed/raw footprint; four-largest-shard minimum is an implementation gate. Network, decompression and cache churn were not measured. Dataset state format shown in docs is not a recovery validation result. |
| B3 libffcv/ffcv | [loader.py, 48–162](https://github.com/libffcv/ffcv/blob/3a12966b3afe3a81733a732e633317d747bfaac7/ffcv/loader/loader.py#L48-L162); [os_cache.py](https://github.com/libffcv/ffcv/blob/3a12966b3afe3a81733a732e633317d747bfaac7/ffcv/memory_managers/os_cache.py) | Manager selection, documented traversal restriction and mmap context verified. Quasi-random read reduction is a source claim, not a measured gain. Process-cache internals and current toolchain compatibility were not audited; historical upstream pin dated 2024-05-06 in Dot B. |

DALI and FFCV current compatibility, Mosaic dataset conversion and multi-worker
memory use remain qualification gaps. Papers and live performance guides in
Dot B are background context only; no performance numbers were imported.

Source-supported mechanisms map to candidate coverage. Proposed verification
procedures are separately labeled in the skill and are not passed tests.
