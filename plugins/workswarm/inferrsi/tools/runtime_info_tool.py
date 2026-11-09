"""Expose the installed launcher through WorkSwarm's model-facing tool result."""

import json
from pathlib import Path

from openjiuwen.core.foundation.tool import Tool, ToolCard


class InferRSIRuntimeInfoTool(Tool):
    def __init__(self) -> None:
        super().__init__(ToolCard(
            id="inferrsi_runtime_info",
            name="inferrsi_runtime_info",
            description=(
                "Resolve the installed InferRSI launcher before following the inferrsi skill. "
                "Read-only: returns its absolute path without executing commands."
            ),
            input_params={"type": "object", "properties": {}, "additionalProperties": False},
            idempotent=True,
            parallel_safe=True,
        ))

    async def invoke(self, inputs, **kwargs):
        if inputs != {}:
            return {"success": False, "error": "This read-only tool accepts no arguments."}
        try:
            root = Path(__file__).resolve().parent.parent
            launcher = root / "skills/inferrsi/scripts/inferrsi.py"
            if (not launcher.is_file()
                    or not (root / "runtime/payload.zip").is_file()
                    or not (root / "runtime/launcher.py").is_file()
                    or not (root / "runtime/manifest.json").is_file()):
                return {
                    "success": False,
                    "error": "InferRSI bundle is incomplete; reinstall the built WorkSwarm ZIP.",
                }
            return {"success": True, "launcher": str(launcher)}
        except OSError:
            return {"success": False, "error": "Cannot read the installed InferRSI bundle."}

    def render_for_llm(self, output) -> str:
        # The host uses this renderer for the ToolMessage sent to the model.
        return json.dumps(output, ensure_ascii=False)

    async def stream(self, inputs, **kwargs):
        yield await self.invoke(inputs, **kwargs)
