# Locate a registration failure

1. In the failing engine's Python environment, enumerate the installed package and its entry points. This probe reads distribution metadata without importing the plugin.

   ```bash
   python - <<'PY'
   from importlib.metadata import distribution

   plugin = distribution("vllm-ascend")
   print(plugin.version)
   for ep in plugin.entry_points:
       if ep.group in {"vllm.platform_plugins", "vllm.general_plugins"}:
           print(ep.group, ep.name, ep.value)
   PY
   ```

2. Match the failure to a hook. In the tagged setup, the platform hook `ascend` calls `register`, which returns the dotted class name `vllm_ascend.platform.NPUPlatform`. Connector, model loader, service profiling and model registration have separate general hooks. If the package or expected entry is absent, compare the engine interpreter and installed distribution with the release environment before debugging kernels.
3. If the platform resolves but a connector or loader is missing, trace the corresponding general hook inside the engine-core process. Connector, loader and profiling hooks call `_ensure_global_patch` before their own setup. The guard records success after `adapt_patch(is_global_patch=True)` returns and is process-local. Check the first import exception and process identity. A parent-process probe or a pytest conftest hook alone cannot establish subprocess initialization.
4. For an unknown model architecture, inspect `ascend_model` separately. Compare the checkpoint architecture string to the registered model target. The text and conditional-generation MiniMax entries are distinct. DeepSeek uses separate target (`DeepseekV4ForCausalLM`) and draft (`DSparkDraftModel`) entries. Record which lookup or subsequent class import failed before changing the checkpoint.

**Output:** package version, installed hook, process, checkpoint architecture, first failing lookup or import, then a fresh-process generation result if available. Source anchors: setup, registration and model registry in the [readset](sources.md).
