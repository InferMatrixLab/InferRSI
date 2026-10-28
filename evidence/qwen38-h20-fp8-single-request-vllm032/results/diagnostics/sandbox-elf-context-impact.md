# Explicit library lookup resolves the inventory blocker

Refs [Issue #67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**INCONCLUSIVE for isolated runtime, evaluator qualification and E2E.**

The first proposal was rejected before execution: its claimed overall deadline
was only cooperative, and subprocess exceptions discarded partial output. The
executed v1 saves attempted commands and available partial output, keeps dynamic
path tags private, and states the cooperative budget and outer Slurm limit.

CPU2004 then failed1:0 in1second on2CPUs/zeroGPUs. One readelf command completed;
aliasing the interpreter's unresolved lexical path raised ValueError. Resolving
that path before aliasing is the only helper change in v2. The original source,
partial readelf evidence, result, review rejection and synthetic alias control
remain retained. No ldd command ran in2004.

CPU2005 completed0:0 in43seconds on2CPUs/zeroGPUs and released the allocation.
The registered base Python has RPATH `$ORIGIN/../lib`; its Tk extension has no
RPATH/RUNPATH. Both previously unresolved Tcl/Tk libraries exist as actual ELF
files in the registered base's lib directory, with their bytes hashed. The clean
standalone extension ldd misses both; adding only that base lib directory to a
controlled LD_LIBRARY_PATH resolves both. All141ELF files across the registered
base and evaluator site-packages then return ldd0 with no not-found marker.
All147subprocess stdout/stderr hashes were checked against the private archive.

This establishes the effect of explicit lookup context on the inventory scan.
It does not demonstrate Python import behavior or isolation. No runtime/package
file changed, package was imported, namespace was created, evaluator/model/task
data was used, or generated code was run. Full dynamic tags and absolute lookup
results remain private; public paths use the established readonly-root aliases.

Next version the inventory policy separately: use a cleared scanner environment
with the registered base lib directory and the matching relocated sandbox
directory, retain all dependency checks, then run inventory and the trusted benign
probe. Keep the original frozen runtime intact. No measured E2E effect;
readiness remains2388/7200GPUseconds with initial147separate.

KnowledgeStore candidate `case.qwen38-eval-sandbox-preparation-cand` revision `sha256:8f867ff7110efc2730461a7963e7009c2fb87d10ab92b17d8cf0840aa0d09507`; readback verified.
