from __future__ import annotations

from context_use.cli.base import BaseCommand, CommandGroup
from context_use.cli.commands.agent import AgentGroup
from context_use.cli.commands.config import ConfigGroup
from context_use.cli.commands.ingest import IngestCommand
from context_use.cli.commands.memories import MemoriesGroup
from context_use.cli.commands.pipeline import PipelineCommand, QuickstartCommand
from context_use.cli.commands.reset import ResetCommand

TOP_LEVEL_COMMANDS: list[type[BaseCommand]] = [
    QuickstartCommand,
    PipelineCommand,
    IngestCommand,
    ResetCommand,
]

COMMAND_GROUPS: list[type[CommandGroup]] = [
    MemoriesGroup,
    AgentGroup,
    ConfigGroup,
]
