# TileLang Ascend FlashAttention stage reuse

Use this case when reviewing a change to a manually synchronized Ascend attention kernel. It traces one score tile from its first write to the last read that makes its global memory (GM) slot reusable.

**Source and evidence.** The source inspected is TileLang Ascend revision `3a93b960d22359de40db86250d335693b4b1a5f4`, which declares version `0.1.4`. The example is under the repository's MIT license (Tile-AI). The third-party notice lists separate Apache-2.0 terms for TVM, Marlin and FlashInfer. This note describes the example in original prose. Source inspection and the Python generation check below were completed. **empirical_validation: not_run** for compilation, Ascend accuracy and performance. [Version][version] · [License][license] · [Third-party notices][notices]

## Trace one packet through the ring

The kernel handles dense non-causal attention with FP16 Q, K, V and output. It supports grouped query heads when the query head count is a multiple of the KV head count. The builder takes query lengths divisible by 256, key lengths divisible by 512 and head dimension 128. A packet represents a 256-row query tile paired with a 512-row key/value block. Each of 24 logical core groups has three GM slots. Automatic synchronization passes are disabled in this example. [Builder and buffers][builder] · [Compile settings][settings]

| Step | Where data lives | When the next writer may proceed |
| --- | --- | --- |
| Cube forms QKᵀ | The query is held in L1 across its key blocks. Cube exports scores to FP16 `SP[core,stage]`. | Cube acquires `SP_REUSE(stage)` before the write. After export, `S_READY` allows Vector to read the scores. |
| Vector prepares weights | Vector reads score strips into UB, updates the row maximum and sum in FP32, and writes exponentiated weights back to the **same** FP16 `SP` slot. | `P_READY` is posted from MTE3 after the strip stores. The preceding contribution for the reused slot has already been merged in the Vector loop. |
| Cube forms PV | Cube can prefetch the first V panel before waiting for `P_READY`. After the wait it reads the weights and writes the partial output to a distinct FP16 slot in `OP`. | The last GM weight read returns `SP_REUSE(stage)` from MTE2. The score slot can then receive the next generation. `O_READY` signals that the partial output can be read. |
| Vector merges the contribution | Two FP32 output tiles remain in UB. The saved rescaling coefficient and tile sum belong to the same stage as the returning contribution. | Vector merges both tiles before reusing the stage statistics. On the final KV block it divides by the running sum, converts to FP16 and writes the output. |

For packet index `p`, Cube writes scores at step `p` and consumes weights at step `p + 3`. Both loops run for `packets + 3` steps. New scores are produced only while `step < packets`. The trailing iterations therefore consume outstanding contributions, even for a core with a single packet. Cube waits for the final `VECTOR_DONE`. A change that stops at `packets` can leave the final output unwritten. Moving the reuse signal ahead of the final weight read can overwrite weights while PV is still consuming them. [Cube ownership][cube] · [Vector math][vector] · [Production and drain loops][loops]

## Check a proposed change

1. From the pinned upstream checkout, use the [upstream preprocessor][preprocess] to regenerate the Python entry point and compare its syntax tree with the published file. This checks lock expansion without importing the kernel or requiring a device.

   ```sh
   cd examples/flash_attention/fa_opt/expert_v3
   python - <<'PY'
   import ast
   from pathlib import Path
   import subprocess
   import sys

   expanded = subprocess.check_output(
       [sys.executable, "tools/preprocess.py", "kernel.tl"], encoding="utf-8"
   )
   published = Path("kernel.py").read_text(encoding="utf-8")
   assert ast.dump(ast.parse(expanded)) == ast.dump(ast.parse(published))
   PY
   ```

2. At each modified signal, identify the writer, final reader and slot generation for both `SP` and `OP`. Trace one packet to exercise drain, then four packets on one core to exercise wraparound. For a separate device validation, direct-entry examples with `B=1, Q_heads=1, KV_heads=1, D=128` and `S=512` or `S=2048` give active cores one or four KV packets per query tile. Retain the input seed and the output for each. The direct script checks FP32 non-causal PyTorch SDPA cast to FP16, with KV head repetition for GQA. Masked, causal, ragged-tail and other head-dimension workloads require their own implementation and oracle. [Generated entry point][entry] · [Oracle and CLI][oracle]

3. For a future timing comparison from `fa_opt/`, select `run.py --tl expert_v3/kernel.py` explicitly. The default selects v2. The runner launches two applications under `msprof`, skips the AscendC reference check, and picks the matching op type's **Total Time(us)** from the newest statistics CSV. Run the AscendC script separately with checking enabled on matched inputs. Record actual device, CANN, TileLang/compiler revision, flags, dtype and layout, shape/head mapping, op names, invocation counts, warmup, repeats and timing boundaries. Decline a comparison when either oracle fails, the op row is absent, invocation counts differ or the samples mix simulation and device runs. The v3 README's timings refer to a separate historical A3/CANN 9.1 run at another revision. This intake establishes no operator or service speedup. [Harness parser][parser] · [Applications and defaults][harness] · [AscendC check][ascendc] · [Upstream report][report]

[version]: https://github.com/tile-ai/tilelang-ascend/blob/3a93b960d22359de40db86250d335693b4b1a5f4/VERSION
[license]: https://github.com/tile-ai/tilelang-ascend/blob/3a93b960d22359de40db86250d335693b4b1a5f4/LICENSE
[notices]: https://github.com/tile-ai/tilelang-ascend/blob/3a93b960d22359de40db86250d335693b4b1a5f4/THIRDPARTYNOTICES.txt
[builder]: https://github.com/tile-ai/tilelang-ascend/blob/3a93b960d22359de40db86250d335693b4b1a5f4/examples/flash_attention/fa_opt/expert_v3/kernel.tl#L330-L364
[settings]: https://github.com/tile-ai/tilelang-ascend/blob/3a93b960d22359de40db86250d335693b4b1a5f4/examples/flash_attention/fa_opt/expert_v3/kernel.tl#L13-L46
[cube]: https://github.com/tile-ai/tilelang-ascend/blob/3a93b960d22359de40db86250d335693b4b1a5f4/examples/flash_attention/fa_opt/expert_v3/kernel.tl#L50-L167
[vector]: https://github.com/tile-ai/tilelang-ascend/blob/3a93b960d22359de40db86250d335693b4b1a5f4/examples/flash_attention/fa_opt/expert_v3/kernel.tl#L202-L326
[loops]: https://github.com/tile-ai/tilelang-ascend/blob/3a93b960d22359de40db86250d335693b4b1a5f4/examples/flash_attention/fa_opt/expert_v3/kernel.tl#L410-L494
[entry]: https://github.com/tile-ai/tilelang-ascend/blob/3a93b960d22359de40db86250d335693b4b1a5f4/examples/flash_attention/fa_opt/expert_v3/kernel.py
[oracle]: https://github.com/tile-ai/tilelang-ascend/blob/3a93b960d22359de40db86250d335693b4b1a5f4/examples/flash_attention/fa_opt/expert_v3/kernel.tl#L498-L565
[parser]: https://github.com/tile-ai/tilelang-ascend/blob/3a93b960d22359de40db86250d335693b4b1a5f4/examples/flash_attention/fa_opt/run.py#L16-L45
[harness]: https://github.com/tile-ai/tilelang-ascend/blob/3a93b960d22359de40db86250d335693b4b1a5f4/examples/flash_attention/fa_opt/run.py#L178-L308
[ascendc]: https://github.com/tile-ai/tilelang-ascend/blob/3a93b960d22359de40db86250d335693b4b1a5f4/examples/flash_attention/fa_opt/reference/ascendc.py
[report]: https://github.com/tile-ai/tilelang-ascend/blob/3a93b960d22359de40db86250d335693b4b1a5f4/examples/flash_attention/fa_opt/expert_v3/README.md

[preprocess]: https://github.com/tile-ai/tilelang-ascend/blob/3a93b960d22359de40db86250d335693b4b1a5f4/examples/flash_attention/fa_opt/expert_v3/tools/preprocess.py
