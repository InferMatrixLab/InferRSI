Use two allocator-reserved Ascend 910B1s. Stage the checkpoint identified by `weights.json`, install InferRSI at the revision in `runspec.json` and check out the two vLLM-Omni revisions listed there. The launcher in `validator/` uses this site's Ascend Docker runtime conventions. Supply the matching runtime image on an appropriate Docker host with the drivers installed.

Set `GLM_RSI_WORKSPACE` to an absolute shared directory with room for fresh snapshots and outputs, `GLM_BASELINE` and `GLM_CANDIDATE` to the two checkouts, `GLM_IMAGE_WEIGHTS` to the staged checkpoint, and `GLM_OMNI_IMAGE` to the pinned runtime. From this directory, run:

```sh
npu run --gpus 2 -- bash replay.sh
```

The reservation spans the round and its independent final. The native model is imported from each declared candidate tree. Public reference hashes are specific to this runtime, checkpoint, workload and deployment. A different runtime can invalidate the pixel oracle.
