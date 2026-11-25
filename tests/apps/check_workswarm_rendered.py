"""Exercise the pinned host's model-facing bootstrap in a disposable process."""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path


async def rendered_launcher(plugin: Path, workspace: Path) -> str:
    """Resolve only from native model-visible ToolMessages, without an LLM call."""
    from openjiuwen.core.foundation.llm import ToolCall
    from openjiuwen.core.runner import Runner
    from openjiuwen.core.session.agent import create_agent_session
    from openjiuwen.core.single_agent.rail.base import AgentCallbackContext
    from openjiuwen.core.single_agent.schema.agent_card import AgentCard
    from openjiuwen.core.sys_operation import LocalWorkConfig, OperationMode, SysOperationCard
    from openjiuwen.harness.deep_agent import DeepAgent
    from openjiuwen.harness.rails.skills.skill_use_rail import SkillUseRail
    from openjiuwen.harness.schema.config import DeepAgentConfig
    from openjiuwen.harness.workspace.workspace import Workspace

    identity = "inferrsi-check-" + uuid.uuid4().hex
    Runner.resource_mgr.add_sys_operation(SysOperationCard(
        id=identity, mode=OperationMode.LOCAL,
        work_config=LocalWorkConfig(work_dir=str(workspace)),
    ))
    agent = DeepAgent(AgentCard(id=identity, name=identity))
    record = None
    session = None
    try:
        agent.configure(DeepAgentConfig(
            workspace=Workspace(root_path=str(workspace / "agent-workspace")),
            sys_operation=Runner.resource_mgr.get_sys_operation(identity),
            auto_create_workspace=True, enable_task_loop=False, enable_skill_discovery=True,
            rails=[SkillUseRail(skills_dir=[], skill_mode="all", include_tools=False)],
        ))
        await agent.ensure_initialized()
        record = await agent.load_plugin(str(plugin))
        assert sorted(ref.kind.value for ref in record.refs) == ["skill", "tool"]
        session = create_agent_session(
            session_id=identity, card=agent.card, close_stream_on_post_run=False,
        )
        await session.pre_run(inputs={"query": "Use InferRSI in this target workspace"})

        async def model_text(name: str, arguments: dict) -> str:
            call = ToolCall(
                id=uuid.uuid4().hex, type="function", name=name, arguments=json.dumps(arguments),
            )
            ctx = AgentCallbackContext(agent=agent, session=session)
            results = await agent.ability_manager.execute(ctx, call, session)
            assert len(results) == 1
            # Discard structured results, just as the model does.
            return results[0][1].content

        skill = await model_text("skill_tool", {"skill_name": "inferrsi"})
        assert "inferrsi_runtime_info" in skill
        assert str(plugin) not in skill
        visible_location = await model_text("inferrsi_runtime_info", {})
        location = json.loads(visible_location)
        assert location["success"] is True
        launcher = Path(location["launcher"])
        assert launcher.is_absolute() and launcher.is_file()
        assert launcher.resolve().is_relative_to(plugin.resolve())
        rejected = json.loads(await model_text("inferrsi_runtime_info", {"command": "unused"}))
        assert rejected["success"] is False
        assert len(await agent.unload_extension(record)) == len(record.refs)
        record = None
        assert agent.ability_manager.get("inferrsi_runtime_info") is None
        return visible_location
    finally:
        if session is not None:
            await session.post_run()
        if record is not None:
            await agent.unload_extension(record)
        shutdown = getattr(agent, "shutdown", None)
        if shutdown is not None:
            await shutdown()
        Runner.resource_mgr.remove_sys_operation(identity)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-source", type=Path, required=True)
    parser.add_argument("--plugin", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.host_source.resolve()))
    sys.dont_write_bytecode = True
    visible_result = asyncio.run(rendered_launcher(args.plugin, args.workspace))
    args.result.write_text(visible_result, encoding="utf-8")
