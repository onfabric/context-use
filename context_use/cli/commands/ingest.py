import argparse
from typing import TYPE_CHECKING

from context_use.cli import output as out
from context_use.cli.base import (
    ContextCommand,
    add_archive_args,
    print_ingest_result,
    resolve_archive,
)
from context_use.config import Config

if TYPE_CHECKING:
    from context_use import ContextUse


class IngestCommand(ContextCommand):
    name = "ingest"
    help = "Step 1: Process a data export archive"
    description = (
        "Process a data export archive. Run without arguments to "
        "interactively pick from archives in data/input/."
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

        print()
        out.header(f"Ingesting {provider_str} archive")
        out.kv("File", zip_path)
        out.kv("Provider", provider_str)
        print()

        result = await ctx.process_archive(provider_str, zip_path)

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
