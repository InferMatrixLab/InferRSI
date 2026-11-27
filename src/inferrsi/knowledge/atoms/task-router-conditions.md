## Target conditions

Record model family as a list (LLM, Omni, TTS, Diffusion, RLT or another
specified family), model/checkpoint revision, hardware backend (CUDA, ROCm,
Ascend NPU, XPU or another specified target), device SKU, OS (Linux, Windows,
Android, iOS or another specified target), engine and revision, dtype, shape,
concurrency and constraints. An Omni pipeline may additionally include its TTS
or diffusion stages. Keep deployment form such as mobile/edge separate from OS.
An absent field is unknown. A routing label or a common-backend registration
does not establish device support. Check the selected owner's source and scope.

Failures that interrupt execution begin in debug. Correct execution with
unacceptable output begins in accuracy. A regression first observed after an
upgrade may use version-align as the primary route and either as a secondary
route. For engine work, decide who owns the execution core: an upstream fork
uses derived-engine; a new runtime owning its own execution and memory model
uses independent-engine, including on Windows or mobile. OS alone cannot
decide between them.

For a Windows vLLM fork with a TTS quality regression after an upgrade,
choose accuracy if the requested delivery is restored speech quality, or
version-align if the requested delivery is a validated upgrade matrix. Link
the other route and pin both revisions, the same audio input, and reference
output. Record fork lineage as context unless creating the fork is a deliverable.
If the delivery is unclear, state both routes and ask what must be accepted.

