# Local retrieval experiment environment

Hardware/OS inventory was read locally by the accountable orchestrator:

| Field | Observed inventory |
| --- | --- |
| CPU | Intel Core i7-8565U @ 1.80 GHz |
| Cores | 4 physical, 8 logical |
| RAM | 15.8 GiB |
| OS | Windows 10 Pro, 10.0.19045 |

The processor string's frequency is inventory metadata, not proof of a fixed
operating clock. Clock/power state and unrelated background load are not held
constant by this evaluator. Twenty sequential paired groups alternate AB/BA;
there are no concurrent baseline/candidate workers. The formal benchmark starts
after software tests, quality comparison and diagram rendering finish. Their
durations are excluded from the latency observations.

Each result's identity section is authoritative for the actual Python version,
implementation, executable-binary digest, source revision, imported modules,
optimization flags and full source/corpus inventories. Both variants must use
the same interpreter and complete corpus. No personal path, hostname or network
address is needed in these shared records.

The completed formal runs used CPython 3.12.6 with site initializers disabled
and optimization flag zero on both sides. Their snapshots cover 53 Python
source files and 458 corpus files / 2,883,003 bytes, including 108 knowledge
records and the 342-file / 2,294,958-byte shared library.

Fresh-reader API measurements construct a new KnowledgeReader; reused-reader
measurements follow the frozen warmup. Every CLI measurement starts a fresh
Python process. The OS filesystem cache is uncontrolled and is not claimed
cold. API wall time, full CLI startup/capture and output decoding are distinct
measurements. This CPU-only experiment runs no model or inference service and
establishes no GPU, service, task-quality or production-distribution benefit.
