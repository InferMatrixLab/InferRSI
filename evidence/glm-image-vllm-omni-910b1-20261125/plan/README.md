Use two allocator-reserved Ascend 910B1s. Stage the checkpoint identified by `weights.json`, install InferRSI at the revision in `runspec.json` and check out the two vLLM-Omni revisions listed there. The launcher in `validator/` uses this site's Ascend Docker runtime conventions. Supply the matching runtime image on an appropriate Docker host with the drivers installed.

Set `GLM_RSI_WORKSPACE` to an absolute shared directory with room for fresh snapshots and outputs, `GLM_BASELINE` and `GLM_CANDIDATE` to the two checkouts, `GLM_IMAGE_WEIGHTS` to the staged checkpoint, and `GLM_OMNI_IMAGE` to the pinned runtime. Set `GLM_RSI_PYTHON` to the Python interpreter that contains the pinned InferRSI wheel, or activate that environment. From this directory run

```sh
npu run --gpus 2 -- bash replay.sh
```

The reservation spans the round and its independent final. The native model is imported from each declared candidate tree. Public reference hashes are specific to this runtime, checkpoint, workload and deployment. A different runtime can invalidate the pixel oracle.

Set `GLM_COHORT=packed` for the incremental comparison. Use the InferRSI revision and the two model revisions from `incremental/decision.json`. Use `GLM_COHORT=shared` with `plan/runspec.json` for the first comparison. Each invocation writes to its own campaign directory.

Before creating a campaign, the replay checks both Git revisions and the exact retained `vllm_omni` source bytes and modes. It verifies the installed InferRSI build and package files, the frozen evaluation protocol, the Docker image ID and every staged checkpoint file against its recorded size and SHA-256. The replay then passes the immutable image ID to the engine launcher. The weight directory should contain the 25 files listed in `weights.json`. The same interpreter runs the preflight and the campaign.

Run `python -B test_preflight.py` in the pinned InferRSI environment to exercise the identical-tree and dirty-source checks on CPU. To check real inputs alone, set the same environment variables and run `python -B preflight.py packed` or `python -B preflight.py shared`; a successful check prints the Docker image ID.

The replay writes a timestamped input verification record to `$GLM_RSI_WORKSPACE/preflight-$GLM_COHORT.json`. The bundle retains independent host checks in `results/input-pins-shared.json`, `results/input-pins-packed.json` and `results/input-pins-direct.json`. These records were collected against the pinned inputs after the original measurements had started. Each contains the two revisions and source digests, installed InferRSI build and package digest, protocol hashes, runtime image ID and checkpoint manifest hash. The cumulative direct run used the incremental protocol on stock and packed source revisions.
