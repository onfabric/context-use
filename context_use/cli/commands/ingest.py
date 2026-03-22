from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import TYPE_CHECKING

from context_use.cli import output as out
from context_use.cli.base import (
    ContextCommand,
    add_archive_args,
    print_ingest_result,
    resolve_archive,
)
from context_use.cli.config import Config

if TYPE_CHECKING:
    from context_use import ContextUse
    from context_use.etl.core.pipe import Pipe


class IngestCommand(ContextCommand):
    name = "ingest"
    help = "Parse a data export archive"
    description = (
        "Process a data export archive. Run without arguments to "
        "interactively pick from archives in context-use-data/input/."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        add_archive_args(parser)

    async def run(
        self,
        cfg: Config,
        ctx: ContextUse,
        args: argparse.Namespace,
    ) -> None:
        picked = resolve_archive(args, cfg, command="ingest")
        if picked is None:
            return
        provider_str, zip_path = picked

        pipe_factory: Callable[[type[Pipe]], Pipe] | None = None
        if provider_str == "bank":
            from context_use.cli.bank_setup import run_bank_setup
            from context_use.providers.bank.generic_pipe import GenericBankPipe

            mapping = run_bank_setup(zip_path)
            if mapping is None:
                return

            def _bank_factory(pipe_cls: type[Pipe]) -> Pipe:
                return GenericBankPipe(mapping=mapping)

            pipe_factory = _bank_factory

        print()
        out.header(f"Ingesting {provider_str} archive")
        out.kv("File", zip_path)
        out.kv("Provider", provider_str)
        print()

        result = await ctx.process_archive(
            provider_str, zip_path, pipe_factory=pipe_factory
        )

        out.success("Archive processed")
        out.kv("Archive ID", result.archive_id)
        print_ingest_result(result)

        if result.tasks_failed:
            out.kv("Tasks failed", result.tasks_failed)
        if result.errors:
            for e in result.errors:
                out.error(e)

        print()
        out.header("Next step:")
        out.next_step("context-use memories generate")
        print()
