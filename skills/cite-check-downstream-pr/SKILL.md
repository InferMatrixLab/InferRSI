---
name: cite-check-downstream-pr
description: Review a downstream PR description for correct acceptance issue links, SHA pins, and artifact citations.
---

# Cite-check a downstream PR

Use when reviewing external PRs that claim performance or quality improvements tied to RSI acceptance work.

## Checklist

- [ ] Links an acceptance issue URL (not only a chat thread)  
- [ ] States **baseline SHA** and **candidate SHA** matching that issue  
- [ ] Points to `evidence/<campaign-id>/results/` (or equivalent published mirror)  
- [ ] Does **not** invent new thresholds or restate bars differently  
- [ ] Marks summaries **unverified** if artifacts are missing, stale, or off-SHA  
- [ ] Uses verdict vocabulary only: `PASS` / `FAIL` / `INCONCLUSIVE`  

## Red flags

- “X% faster” without artifact path  
- Branch names instead of full SHAs  
- Microbench-only support for e2e latency claims  

## Reference

[docs/downstream.md](../../docs/downstream.md)
