# MUSA (Moore Threads) backend

`--backend musa` targets the Moore Threads MUSA plugin
([`MooreThreads/vllm-musa`](https://github.com/MooreThreads/vllm-musa)). It is a
discovery and measurement lane, not a validation claim: the adapter reports what
the host says, and every number still has to come from your own benchmark and
quality commands.

## What the adapter does

- Probes devices through `pymtml` (the pynvml-compatible MTML binding shipped by
  `mthreads-ml-py` and loaded by vLLM-MUSA itself), in the interpreter you pass
  with `--python`, in a bounded read-only subprocess. It does not require a
  preinstalled vendor CLI such as `mthreads-gmi`, and the probe initializes no
  MUSA context.
- Records `index`, `uuid`, `name`, driver version and total memory per device,
  plus `MUSA_VISIBLE_DEVICES` in the environment snapshot.
- Registers `torch_musa`, `vllm-musa`, `mthreads-ml-py`, `torchada` and `mate` in
  the dependency fingerprint, so a run records the compat layer it measured.
- Qualifies a campaign selection (`inferrsi.apps.host.platforms.musa.qualify_devices`)
  by device count, SKU substring and an already-running compute process. An empty
  process list only counts as idle when the device's used memory agrees
  (`IDLE_USED_MIB`), because a vendor binding can implement the query without
  implementing process accounting. A binding that reports neither fails.

## Device identity caveat

`pymtml` answers with **physical** device ids and is documented by the plugin as
unaffected by `MUSA_VISIBLE_DEVICES`, while `torch.musa` applies the logical
remapping. `--device-ids` therefore means physical ids.

```bash
# Devices as the plugin sees them, then pin the same physical ids.
inferrsi doctor --repo ~/ws/vllm-musa --repo-type vllm_musa --backend musa \
  --python /path/to/musa/python --device-ids 0,1 --device-model "S5000"
```

A declared id only names the card that produced the tokens when the inherited
mask pins logical index `L` to that id. An unset mask is the runtime's implicit
identity view, so it binds `--device-ids 0` but not `--device-ids 1`. Discovery
and the dashboard signature share `logical_binding()`
(`inferrsi.apps.host.platforms`): a selection whose mask does not bind is
reported unverified and gets no comparable device identity. `qualify_devices`
returns each record with the `logical_index` the trial will use, so evidence can
state "verified physical N == logical L" explicitly.

## First experiment

```bash
inferrsi plan \
  --repo ~/ws/vllm-musa --repo-type vllm_musa --backend musa \
  --python /path/to/musa/python --device-ids 0 --device-model "S5000" \
  --baseline-command "bash bench.sh baseline {result}" \
  --candidate-command "bash bench.sh candidate {result}" \
  --validation-command "bash check_outputs.sh" \
  --metric-key latency_ms --direction minimize --repetitions 3 \
  --min-improvement-pct 3 --output-dir ~/campaigns/musa-first
inferrsi run ...   # same flags, then read report.html
```

Commands are executed as `argv` (no shell). Wrap pipelines in a script and pass
`{result}` as the path your script must write the metric JSON to.

## Lanes

- **Text LLM**: `--repo-type vllm_musa`, scenarios `llm.decode` and
  `llm.serving`.
- **Omni (image/video/audio)**: same repo type; scenarios
  `diffusion.image_generation`, `diffusion.video_generation`, `audio.tts`. Build
  from the MUSA Omni image so the pinned dependency set is part of the record.

Knowledge: `skill_library/records/` for the three `vllm_musa.*` records and
`systems/engines/vllm-musa/` for the operating procedure
([`SKILL.md`](../src/inferrsi/knowledge/data/skill_library/systems/engines/vllm-musa/SKILL.md)).

## Bounds

What has been executed, and where it is recorded:

- **Executed on real hardware.** The probe, the qualification refusals and the
  Dashboard environment signature ran on an MTT S5000 host (8 cards, driver
  `5.2.0-server`, image `…/vllm:v0.32.0-ph1-5.2.0-torch2.13.0.post1-20261120`).
  The mask matrix, the controlled "held 4 GiB in my own process while the binding
  reported zero processes" refusal, and a live `vllm serve` holding 65 GiB that
  still reported zero processes are in the linked comments on the pull request
  that added this backend. Each case names the commit it ran at, the driver and
  the exact probe output; the refusal paths were tightened afterwards (a negative
  `used_mib` reading and a non-sequence process reply both refuse now) without
  weakening any case that was verified.
- **Not executed here.** A campaign that produces a PASS/FAIL verdict, and any
  claim about numerics or performance. Those stay unverified until someone runs
  them on their own hardware with their own quality command.
- A `musa` descriptor is deliberately `unverified` in `pack.json`; device
  discovery is not a compatibility or performance certification.
- Records under `skill_library/records/` are source-derived
  (`locally_verified: false`). CUDA and Ascend records remain scoped to their own
  hardware.
