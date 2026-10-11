# Recipes

RunSpec-oriented scenario recipes live here. Each recipe should reference:

- A **scenario** name aligned with `RunSpec.scenario`
- Inputs under `plan/` and outputs under `results/` for the campaign
- Validator freeze location under `validator/`

## Layout (minimal)

```
recipes/
  README.md
  _template/
    recipe.yaml      # copy and rename per scenario
```

No upstream revision pins belong in shared recipe defaults—pin baseline/candidate SHAs in the acceptance issue for that campaign.
