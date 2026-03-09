from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, ClassVar

from context_use.cli import output as out
from context_use.cli.base import ApiCommand, CommandGroup
from context_use.config import Config
from context_use.ext.adk.agent.runner import AdkAgentBackend

if TYPE_CHECKING:
    from context_use import ContextUse


def _build_agent_backend(cfg: Config) -> AdkAgentBackend:
    return AdkAgentBackend(
        api_key=cfg.openai_api_key or "",
        model=cfg.openai_model,
    )


class BaseAgentSkillCommand(ApiCommand):
    """Base for commands that run a named skill from the skill registry.

    Subclasses set ``skill_name``, a short ``header_text`` and
    ``info_text`` to display before running.
    """

    skill_name: ClassVar[str]
    header_text: ClassVar[str]
    info_text: ClassVar[str]

    async def run(
        self,
        cfg: Config,
        ctx: ContextUse,
        args: argparse.Namespace,
    ) -> None:
        from context_use.agent.skill import get_skill

        backend = _build_agent_backend(cfg)

        out.header(self.header_text)
        out.info(self.info_text + "\n")

        skill = get_skill(self.skill_name)
        result = await ctx.run_agent(backend, skill.prompt)

        out.success(f"{self.header_text} complete")
        print()
        if result.summary:
            print(result.summary)
        print()


class AgentSynthesiseCommand(BaseAgentSkillCommand):
    name = "synthesise"
    help = "Synthesise pattern memories from event memories"
    skill_name = "synthesise"
    header_text = "Synthesising memories"
    info_text = (
        "The agent will explore your memories topic by topic and synthesise "
        "higher-level pattern memories. Might take a few minutes."
    )

    async def run(
        self,
        cfg: Config,
        ctx: ContextUse,
        args: argparse.Namespace,
    ) -> None:
        await super().run(cfg, ctx, args)
        out.next_step("context-use memories list", "browse your memories")
        print()


class AgentUserProfileCommand(BaseAgentSkillCommand):
    name = "profile"
    help = "Compile a first-person user profile from memories (printed to stdout)"
    skill_name = "profile"
    header_text = "Generating user profile"
    info_text = (
        "The agent will explore your memories topic by topic and compile "
        "a first-person profile. Might take a few minutes."
    )


class AgentAskCommand(ApiCommand):
    name = "ask"
    help = "Send a free-form query to the personal agent"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("query", help="The task or question to send to the agent")

    async def run(
        self,
        cfg: Config,
        ctx: ContextUse,
        args: argparse.Namespace,
    ) -> None:
        from context_use.agent.skill import make_adhoc_skill

        query: str = args.query
        if not query:
            out.error(
                "Please provide a query. "
                'Example: context-use agent ask "Fix any dates that look wrong"'
            )
            return

        backend = _build_agent_backend(cfg)

        out.header("Running agent")
        out.info(f"Query: {query}\n")

        skill = make_adhoc_skill(query)
        result = await ctx.run_agent(backend, skill.prompt)

        print()
        if result.summary:
            print(result.summary)
        print()


class AgentGroup(CommandGroup):
    name = "agent"
    help = "Run the personal memory agent"
    description = (
        "Run the personal memory agent with a built-in skill or a free-form query."
    )
    subcommands = [
        AgentSynthesiseCommand,
        AgentUserProfileCommand,
        AgentAskCommand,
    ]
