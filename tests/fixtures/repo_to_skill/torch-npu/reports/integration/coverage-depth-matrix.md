# Coverage and depth

| Capability | Owning content | Source coverage | Native verification |
|---|---|---|---|
| installation-and-compatibility | `sub-skills/installation-and-compatibility/SKILL.md` + mechanisms/troubleshooting | Source-supported primary workflow | BLOCKED_REQUIRED_BACKEND |
| privateuse1-and-dispatch | `sub-skills/privateuse1-and-dispatch/SKILL.md` + mechanisms/troubleshooting | Source-supported primary workflow | BLOCKED_REQUIRED_BACKEND |
| operator-development | `sub-skills/operator-development/SKILL.md` + mechanisms/troubleshooting | Source-supported primary workflow | BLOCKED_REQUIRED_BACKEND |
| memory-streams-and-events | `sub-skills/memory-streams-and-events/SKILL.md` + mechanisms/troubleshooting | Source-supported primary workflow | BLOCKED_REQUIRED_BACKEND |
| graph-and-compile | `sub-skills/graph-and-compile/SKILL.md` + mechanisms/troubleshooting | Source-supported primary workflow | BLOCKED_REQUIRED_BACKEND |
| distributed-and-hccl | `sub-skills/distributed-and-hccl/SKILL.md` + mechanisms/troubleshooting | Source-supported primary workflow | BLOCKED_REQUIRED_BACKEND |
| training-and-precision | `sub-skills/training-and-precision/SKILL.md` + mechanisms/troubleshooting | Source-supported primary workflow | BLOCKED_REQUIRED_BACKEND |
| profiling-and-debugging | `sub-skills/profiling-and-debugging/SKILL.md` + mechanisms/troubleshooting | Source-supported primary workflow | BLOCKED_REQUIRED_BACKEND |

Full directory/file breadth is in `full-tree-inventory.json`; actual semantic
spans are in the runtime source manifest. Long-tail inventoried-only surfaces
are named in the gap register. CPU/static/helper checks do not upgrade native
device gates. Cross-route checks cover stream/graph replay, dispatch/operator
Meta/autograd, HCCL lifetime and training/profiling boundaries.
