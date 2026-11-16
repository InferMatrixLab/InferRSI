---
name: ascend-operator-profiling
description: 'Benchmark a single Ascend NPU operator using msprof op: build, collect with warmup, read the 8 CSV metrics files, derive a bottleneck verdict, and iterate. Use when validating operator performance in isolation before system-level profiling.

  '
---

# Ascend Operator-Level Profiling

Use this skill to benchmark a **single operator** in isolation on real NPU hardware. Complements
`ascend-performance-analysis`, which focuses on system-level traces and multi-kernel workflows.
This skill is for validation, iteration, and root-cause analysis of a specific operator's
performance.

---

## When to use this skill vs ascend-performance-analysis

| Need | Use this skill | Use ascend-performance-analysis |
|------|----------------|--------------------------------|
| Single-operator isolated benchmark | ✓ | — |
| Per-operator CSV metrics (8 files) | ✓ | — |
| Bottleneck is AI Core vs memory vs fallback | ✓ | — |
| Full model trace, multi-kernel, step breakdown | — | ✓ |
| System communication analysis (HCCL) | — | ✓ |
| Top-N kernels by duration | — | ✓ |

---

## Workflow: Build → Collect → Archive → Analyze → Iterate

```
Step 1: Build operator
    ↓
Step 2: msprof op collect data (with warmup)
    ↓
Step 3: Archive CSV files + generate summary
    ↓
Step 4: Read summary → verdict (AI Core / memory / scalar bound?)
    ↓
Step 5: Locate bottleneck in optimization table
    ↓
Step 6: Modify operator code → return to Step 2
```

---

## Step 1: Build operator

### Direct operator (cmake + make):

```bash
cd operators/{operator_name}
mkdir -p build && cd build
cmake ..
make -j
```

### aclnn operator (install to CANN):

```bash
bash build.sh --pkg --soc=ascend910b --ops={operator_name} --vendor_name=custom -j16
./build_out/*.run --install-path=$CANN
bash build.sh --run_example {operator_name} eager cust --vendor_name=custom
```

Verify the executable or test harness exists before proceeding.

---

## Step 2: msprof op data collection

### Command template:

```bash
# Basic
msprof op ./demo

# Recommended (warmup + multiple runs + explicit output)
msprof op --warm-up=10 --launch-count=5 --output=./msprof_output ./demo
```

### Key parameters (observed from source):

| Parameter | Value | Why |
|-----------|-------|-----|
| `--warm-up=N` | 10 (recommended) | Avoid DVFS (dynamic voltage/frequency scaling) skewing first run. Always use this. |
| `--launch-count=N` | 5 (for stability) | Run N times, average the results. Use 1 for quick feedback, 5+ for production data. |
| `--output=<dir>` | `./msprof_output` or similar | Collect results in a named directory; avoids scattered files. |
| `--soc-version` | (omit on-board) | Hardware is auto-detected on the device. |

### Output directory:

msprof creates `OPPROF_{timestamp}_XXX/` containing the 8 CSV files (see Step 3).

---

## Step 3: Archive data and generate summary

### Manual steps:

1. **Locate the latest OPPROF directory:**
   ```bash
   OPPROF_DIR=$(ls -td ./msprof_output/OPPROF_* | head -1)
   ```

2. **Create archive round in operator docs:**
   ```bash
   ROUND_DIR=operators/{operator_name}/docs/perf/round_NNN
   mkdir -p $ROUND_DIR
   cp $OPPROF_DIR/*.csv $ROUND_DIR/
   ```

3. **Generate summary (use perf_summary.py if available):**
   ```bash
   python3 {skill_path}/scripts/perf_summary.py $OPPROF_DIR operators/{operator_name}
   ```

   This automatically:
   - Creates `docs/perf/round_NNN/` (NNN auto-increments)
   - Copies all 8 CSV files
   - Generates `summary.txt` with min/avg/max statistics (no judgment)

### Archive directory structure:

```
operators/{op_name}/docs/perf/
├── round_001/            # Baseline
│   ├── OpBasicInfo.csv
│   ├── PipeUtilization.csv
│   ├── ArithmeticUtilization.csv
│   ├── Memory.csv
│   ├── MemoryL0.csv
│   ├── MemoryUB.csv
│   ├── L2Cache.csv
│   ├── ResourceConflictRatio.csv
│   └── summary.txt       # min/avg/max; no judgment
├── round_002/            # After 1st optimization
│   ├── *.csv
│   └── summary.txt
└── ...                   # Auto-increment
```

---

## Step 4: Read summary → verdict

### The 8 CSV files and what they measure (observed):

1. **OpBasicInfo.csv** — Op name, type, total duration (us), block dimension, frequency
2. **PipeUtilization.csv** — Time on each pipeline (Vector/Scalar/MTE2/MTE3/Cube/FixPipe) per core; occupancy ratios
3. **ArithmeticUtilization.csv** — Instruction mix (fp32/fp16/int32 ratio for Vector; fp16/int8 for Cube); fops counts
4. **Memory.csv** — Data transferred GM↔UB, GM↔L1, main-memory I/O; bandwidth used
5. **MemoryUB.csv** — UB read/write bandwidth for Vector and Scalar instructions
6. **MemoryL0.csv** — L0A/L0B/L0C read/write bandwidth (Cube use)
7. **L2Cache.csv** — L2 cache hit rates (total, read, write)
8. **ResourceConflictRatio.csv** — Bank conflicts, wait ratios (vec/mte2/mte3/cube), stall reasons

### Read the summary first:

Open `summary.txt`. It reports min/avg/max across all cores for:
- Core time (us) per pipeline stage
- Occupancy ratios (vec_ratio%, mte2_ratio%, etc.) converted to %
- Bandwidth (GB/s)
- Cache hit rates
- Conflict ratios
- Head overhead (Task Duration - longest core time)

### Bottleneck verdict: which ratio is dominant?

| Indicator | Meaning | Next action |
|-----------|---------|-------------|
| `aiv_vec_ratio` > 80% or `aic_cube_ratio` > 70% | **Compute bound** — cannot improve by data movement alone | Reduce compute instructions, fuse operations, check for cast bloat |
| `aiv_mte2_ratio` > 60% or `aiv_mte3_ratio` > 50% | **Memory bound** — transfer time dominates | Increase transfer size ≥16KB, 512B-align addresses, enable L2 CacheMode |
| `aiv_scalar_ratio` > 30% | **Scalar bound** — control overhead high | Reduce tiling granularity or core count; check for serialization |
| `vec_bank_cflt_ratio` or `bankgroup_cflt_ratio` > 5% | **Bank conflict** — UB address collision | Adjust UB layout, add padding |
| `icache_miss_rate` > 15% | **Code cache miss** — instruction fetch bottleneck | Code too large; split kernel or reduce inlining |
| Head overhead > 30% of Task Duration | **Launch/sync overhead** high | Reduce core count, increase work per core |
| `(aiv_mte2_ratio + aiv_mte3_ratio) << max(aiv_vec_ratio, aiv_cube_ratio)` | **Pipeline imbalance** — one unit idle | Check DoubleBuffer (bufNum=2?), check stitch config, increase asyncio |

### Example: compare round_001 to round_002

```bash
diff operators/{op_name}/docs/perf/round_001/summary.txt \
     operators/{op_name}/docs/perf/round_002/summary.txt
```

Look for:
- **Task Duration** improvement (primary metric)
- **Dominant ratio** change (e.g., mte2_ratio down, vec_ratio up = less blocked on memory)
- **Core balance** (min/max spread shrinking = better load balance)

---

## Step 5: Bottleneck optimization reference

When the verdict is clear, consult this table (observed from source):

| Bottleneck | Optimization candidates |
|-----------|------------------------|
| **VEC Bound** (aiv_vec_ratio > 80%) | Fuse instructions in UB; reduce cast/type conversion; use SIMD-friendly tile shapes |
| **MTE2 Bound** (mte2_ratio > 60%) | Increase transfer granularity to ≥16KB chunks; align to 512B; enable L2 CacheMode; consider L2 reuse strategy |
| **CUBE Bound** (aic_cube_ratio > 70%) | Increase L0C buffer depth; ensure L1 data reuse; L0 data prefetch tuning |
| **SCALAR > 30%** | Reduce per-core tiling work; scale down core count; eliminate per-iteration conditionals |
| **Bank Conflict > 5%** | Pad UB arrays; offset read/write addresses; check unroll factors |
| **icache_miss > 15%** | Split kernel into smaller functions; reduce inlining; remove template bloat |
| **Head Overhead > 30%** | Use fewer cores; increase BLOCK_SIZE; move initialization outside loop |
| **No pipeline overlap** (MTE2/VEC both active but sequential) | Enable DoubleBuffer (set bufNum=2); increase stitch_function_max_num; use async data prefetch |

---

## Step 6: Iterate — modify operator, re-collect

**Iteration discipline (inferred from source workflow):**

1. Modify **one** optimization point at a time
2. Rebuild (cmake/make or edit + run)
3. Re-run msprof op (Step 2)
4. Re-archive + re-generate summary (Step 3)
5. Compare new round to previous round (Step 4)
6. If Task Duration improved → keep change; if regressed → revert
7. Repeat until target is met or no further improvement

**Example:**

```bash
# Round 1: baseline
msprof op --warm-up=10 --launch-count=5 --output=./msprof_output ./demo
# → round_001/summary.txt: Task Duration = 100 us, mte2_ratio = 70%

# Optimize: increase transfer size
# (edit operator code: GM_to_UB transfer now 32KB instead of 8KB)
cmake ..; make -j

# Round 2: measure improvement
msprof op --warm-up=10 --launch-count=5 --output=./msprof_output ./demo
# → round_002/summary.txt: Task Duration = 85 us, mte2_ratio = 55%
# ✓ Improvement! Task Duration down 15%, mte2_ratio down. Keep this change.

# Round 3: next optimization...
```

---

## Data-driven decisions

### Thresholds for "performance achieved" (inferred):

| Metric | Acceptable | Warning | Critical |
|--------|-----------|---------|----------|
| Core load imbalance (aiv_time min/max spread) | < 10% | 10–30% | > 30% |
| MTE2/MTE3 ratio (for transfer op) | < 50% | 50–70% | > 70% |
| VEC ratio (for elementwise) | 50–80% | 20–50% or > 80% | < 20% |
| Bank conflict | < 5% | 5–15% | > 15% |
| Icache miss | < 5% | 5–15% | > 15% |
| L2 cache hit rate | > 80% | 50–80% | < 50% |
| Head overhead | < 10% | 10–30% | > 30% |

### Theoretical performance bounds (for reference):

**Memory (Atlas A2, observed):**
- GM peak bandwidth: ~1.8 TB/s
- Example: 4 MB transfer theoretical minimum = 4×1024×1024 B / (1.8e12 B/s) ≈ 2.4 µs

**Compute (Atlas A2 float32 Vector, inferred):**
- Peak throughput: ~11.06 TOPS
- Example: 32K float ops theoretical minimum = 32000 / (11.06e12 ops/s) ≈ 0.003 µs

If actual time >> theoretical, check memory layout (alignment), instruction efficiency (cast bloat),
or core distribution (load balance).

---

## Known limitations and caveats

1. **License**: awesome-ascend-skills (source repo) is UNKNOWN license as of sync 2026-05-26.
   Verify licensing before integrating into production.

2. **DVFS impact**: First run without `--warm-up` will be 20–50% slower due to frequency scaling.
   Always collect warmup data.

3. **Frequency not always at rated**: Check `OpBasicInfo.csv` column `Current Freq` vs `Rated Freq`.
   If Current < Rated, the chip was not at full frequency during measurement (thermal throttling,
   power budget, or neighbor interference on shared device). Repeat when thermal conditions permit.

4. **MTE2/MTE3 contention**: When both read and write use GM simultaneously, bandwidth is shared.
   Theoretical time should be `(MTE2_bytes + MTE3_bytes) / GM_peak_bw`, not calculated separately.

5. **Small data regime**: If operator transfers < 1 KB total, head overhead may be 50%+ of total time.
   This is not necessarily an optimization failure — it reflects the data size constraint, not kernel
   inefficiency.

6. **Multi-core address aliasing**: Multiple cores reading the same 512 B address range will serialize
   over the MTE2 port. If many cores access identical data, consider broadcast or L0 routing.

7. **No instruction-level profile in msprof op output**: CSV files report aggregate ratios, not cycle-by-cycle
   instruction timeline. For detailed pipeline inspection, use `msprof op simulator` instead (trades
   hardware fidelity for detailed trace).

---

## Reference

### perf_summary.py usage:

Script location: `{skill_path}/scripts/perf_summary.py`

```bash
python3 perf_summary.py <OPPROF_dir> <ops_dir> [--round-name <name>]
```

- `<OPPROF_dir>`: Path to `OPPROF_{timestamp}_XXX/` directory (msprof output)
- `<ops_dir>`: Path to operator directory (e.g., `ops/Softmax`)
- `--round-name`: Optional; override auto-increment round name

Outputs:
- Auto-created `{ops_dir}/docs/perf/round_NNN/` with all CSV files
- `summary.txt` with min/avg/max statistics (observation, no judgment)

---

## Verification checklist

Before committing optimization:

- [ ] Warmup enabled (`--warm-up=10`)
- [ ] Multiple runs collected (`--launch-count≥3`)
- [ ] Task Duration decreased or hit target
- [ ] No new ratio spike (e.g., icache_miss suddenly > 15%)
- [ ] Core load balance acceptable (< 30% spread)
- [ ] No instruction fallback to AI_CPU (if applicable)

---

## Summary

Use operator profiling to validate and iterate a single operator on real hardware. The workflow is:
**Build → measure with warmup → archive → read ratios → identify bottleneck → optimize one point → repeat.**
Each round's CSV files are preserved in `docs/perf/round_NNN/` for reproducibility and comparison.
