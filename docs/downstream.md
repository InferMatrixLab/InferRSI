# Downstream citation (fill-in template)

## Contract

Downstream repos (inference stacks, forks, product PRs) **cite** acceptance issues and pinned SHAs. They do **not** redefine gates or restate gain/quality bars.

## Checklist for a downstream PR

- [ ] Links OmniRSI (or sibling) acceptance issue URL  
- [ ] States baseline SHA and candidate SHA matching the issue  
- [ ] Points to `evidence/<campaign-id>/results/` (or published mirror) for numbers  
- [ ] Marks any summary **unverified** if artifacts are missing or stale  
- [ ] No threshold invented in the downstream repo  

## Compatibility matrix (starter)

Label each cell: `validated` / `unsupported` / `unverified`.

| Repo × revision | Backend | Device | Model | Scenario | Status |
| --- | --- | --- | --- | --- | --- |
| _your/target@sha_ | _…_ | _…_ | _…_ | _…_ | _unverified_ |

## Agents

Use skill `skills/cite-check-downstream-pr/SKILL.md` when reviewing external PR text.
