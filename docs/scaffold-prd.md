# PRD — portable repo scaffold

## Problem

New ThinkFlowLab RSI repos need the same **evidence layout**, **claim contract**, **SIAS seams**, and **four-lane CI** without re-deriving the OmniRSI playbook or embedding one campaign’s revision pins into shared automation.

## Users

- RSI Team engineers starting a repo or campaign  
- Downstream integrators citing acceptance issues and artifact paths  
- Agents following portable skills for evidence and verdict discipline  

## Goals

1. **Copyable tree** — documented layout (`docs/`, `recipes/`, `benchmarks/`, `src/`, `tests/`, `skills/`, `evidence/`, CI workflows).  
2. **Playbook alignment** — extend [repo-template.md](repo-template.md) with a concrete skeleton section; keep chapter content intact.  
3. **Green minimal CI** — smoke tests pass on CPU-only GitHub Actions.  
4. **Portable defaults** — no campaign baseline/candidate SHAs in skills, benchmarks, or workflow env defaults.  

## Non-goals

- Full workbench / CLI ([#2](https://github.com/ThinkFlowLab/OmniRSI/pull/2))  
- vLLM-Omni integration or heavy inference stacks  
- Running acceptance campaigns on every `main` push  

## Success

A new repo can copy the scaffold, rename the package, open an acceptance issue with its own SHAs, and run draft → ready → merge → nightly CI with passing smoke.
