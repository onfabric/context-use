from __future__ import annotations

from context_use.cli.base import BaseCommand, CommandGroup
from context_use.cli.commands.agent import AgentGroup
from context_use.cli.commands.config import ConfigGroup
from context_use.cli.commands.describe import DescribeCommand
from context_use.cli.commands.embed import EmbedCommand
from context_use.cli.commands.ingest import IngestCommand
from context_use.cli.commands.memories import MemoriesGroup
from context_use.cli.commands.pipeline import PipelineCommand
from context_use.cli.commands.proxy import ProxyCommand
from context_use.cli.commands.reset import ResetCommand

TOP_LEVEL_COMMANDS: list[type[BaseCommand]] = [
    ProxyCommand,
    PipelineCommand,
    IngestCommand,
    DescribeCommand,
    EmbedCommand,
    ResetCommand,
]

COMMAND_GROUPS: list[type[CommandGroup]] = [
    MemoriesGroup,
    AgentGroup,
    ConfigGroup,
]
