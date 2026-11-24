# Explicit full-context skill evaluation

`anthropic-messages-full-context-v1` is a separate frozen client condition,
not a retry or an implicit change to `anthropic-messages-agent-v1`.

It supplies every exposed file, including `task.json` and the complete selected
knowledge bundle, in path order with byte counts and SHA-256 digests. It does not
select excerpts, truncate files, invent model read calls, or include the private
validator. Knowledge remains fallible guidance; task observations are authoritative.

The condition permits exactly one Messages request per trial. The only offered
tool is `submit_answer`, with the existing frozen output schema. Tool choice stays
`auto`, preserving the existing thinking/sampling policy rather than forcing a
potentially incompatible tool choice. A plain-text answer, malformed submission,
wrong model, unknown usage, or provider failure is not completion. There are no
retries. A valid submission is still graded by the independent frozen validator;
client completion is not a quality verdict.

## Bounds and evidence

- Preserve the original read-agent settings/defaults for old plans.
- The new mode accepts a configured request ceiling no greater than 262,144 bytes.
  Build the exact canonical serialized payload offline for **both** arms before
  authorization. Include all paths, digests, content, tool schema, and prompt.
  Oversize input fails before provider transport; never silently trim to fit.
- Existing per-file UTF-8/read bounds and symlink confinement remain in force.
- Record an `agent.context` manifest and its digest, followed by the ordinary
  request/response/submission events. Do not report preloaded files as model tool
  reads. Raw file content and reasoning are not written into this trace.
- Keep the existing full-model-context cost ceiling, worst input/cache rate,
  output-token ceiling, credential filters, exact-payload authorization gate,
  single-send transport and response-size guard. A larger engineering byte cap
  does not increase spending authority or permit a new pricing assumption.
- Freeze a new plan and runtime identity. Keep failed earlier plans and artifacts;
  do not pool a read-agent arm with a full-context arm.

Offline payload fit proves exposure and serialization bounds, not provider
compatibility, model completion, diagnostic accuracy or service performance.

## Recovery deployment preflight

The deployment configuration selects the explicit full-context kind, one request
per arm and the 262,144-byte ceiling. It retains the same provider, model,
4,096-output-token limit, pricing expiry/rates, PR ledger anchors, daily ledger
and caps. The complete update-only diagnostic pilot payloads measured offline
are 67,018 bytes for the baseline and 224,933 bytes for the candidate, including
all task/knowledge files, paths, digests, prompt and tool schema. The larger
payload leaves 37,211 bytes of engineering headroom; no content is omitted.

At the existing conservative $10.17 per-request reservation, a pair reserves
$20.34. Keep the entire earlier $122.04 reservation; a $200 lifetime allowance
therefore leaves $77.96 before this pair and $57.62 after reserving it. Pricing
validity and both live ledger balances still require revalidation at admission.
The legacy six-request policy and its $122.04 paired bound remain explicit
regression fixtures, not current deployment settings. These are payload/cost
checks, not model-effect evidence or authorization to bypass runtime checks.
