# Acceptance issue checklist (PM)

Use **before** large feature PRs. GitHub form: [.github/ISSUE_TEMPLATE/campaign-acceptance.yml](../.github/ISSUE_TEMPLATE/campaign-acceptance.yml).

## Open the issue first

1. **Campaign ID** — `{model-or-scenario} / {device}×{count}`  
2. **Pinned baseline SHA** and **pinned candidate SHA** (in the issue body only)  
3. **Owner** and target dates on the team Now board  
4. **RunSpec** — repo × revision × backend × device × model × scenario  
5. **Gates frozen** — validators, e2e scenarios, numeric bars documented before runs  
6. **Evidence paths** — `evidence/<campaign-id>/plan|results|patch|validator/`  
7. **Verdict** — start `INCONCLUSIVE`; move to `PASS` or `FAIL` only with complete artifacts  
8. **Downstream citation** — paragraph for external PRs (issue URL + SHAs + artifact paths)  

## Board ordering

Acceptance campaigns → blocking infra/CI → merge-ready slices → research spikes.

## Shared-component review

- [ ] Framework dispatch uses common configuration; model/backend policy and its
  tests stay with their owners. Avoid duplicated model/device selection knobs.
- [ ] List every direct and transitive consumer of changed shared components or
  scripts, including consumers outside the optimization's target model.
- [ ] Map affected contracts to tests and evidence: fast/fallback paths, dtype,
  layout, hooks, gradients and relevant encoder/decoder integration.
- [ ] Record untested consumers or hardware as `INCONCLUSIVE`; operator or
  component parity does not establish full-model quality or service performance.

## Anti-patterns

- Floating branch names instead of pinned SHAs in claims  
- Metrics only in comments (no `results/` tree)  
- Redefining gates in downstream repos  

## Related

- [claims.md](claims.md)  
- [repo-template.md](repo-template.md) § PM  
