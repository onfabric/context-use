from __future__ import annotations

import argparse

from context_use.cli import output as out
from context_use.cli.base import BaseCommand, CommandGroup
from context_use.config import (
    Config,
    config_path,
    load_config,
    load_config_with_sources,
    save_config,
)


class ConfigShowCommand(BaseCommand):
    name = "show"
    help = "Show current settings and where each value comes from"

    async def execute(self, args: argparse.Namespace) -> None:
        cfg, sources = load_config_with_sources()

        def badge(attr: str) -> str:
            src = sources.get(attr, "default")
            if src == "env":
                return out.cyan("[env]")
            if src == "file":
                return out.dim("[file]")
            return out.dim("[default]")

        out.header(f"Configuration ({config_path()})")
        print()

        if cfg.openai_api_key:
            masked = cfg.openai_api_key[:7] + "..." + cfg.openai_api_key[-4:]
            out.kv("OpenAI API key", f"{masked} {badge('openai_api_key')}")
        else:
            out.kv("OpenAI API key", f"{out.dim('not set')} {badge('openai_api_key')}")

        out.kv("Model", f"{cfg.openai_model} {badge('openai_model')}")
        out.kv(
            "Embedding model",
            f"{cfg.openai_embedding_model} {badge('openai_embedding_model')}",
        )

        out.kv("Store", f"sqlite ({cfg.db_path}) {badge('database_path')}")

        if cfg.agent_backend:
            out.kv("Agent backend", f"{cfg.agent_backend} {badge('agent_backend')}")
        else:
            out.kv(
                "Agent backend", f"{out.dim('not configured')} {badge('agent_backend')}"
            )

        out.kv("Data directory", f"{cfg.data_dir} {badge('data_dir')}")

        print()
        out.info(
            f"{out.cyan('[env]')} = set by environment variable  "
            f"{out.dim('[file]')} = from config file  "
            f"{out.dim('[default]')} = built-in default"
        )
        print()
        out.info("To change settings:")
        out.next_step("context-use config set-key", "change OpenAI API key")
        out.next_step("context-use config set-store <path>", "set database path")
        out.next_step("context-use config set-agent adk", "configure agent backend")
        print()


class ConfigSetKeyCommand(BaseCommand):
    name = "set-key"
    help = "Change OpenAI API key"

    async def execute(self, args: argparse.Namespace) -> None:
        cfg = load_config() if config_path().exists() else Config()

        out.info("Get an API key at https://platform.openai.com/api-keys")
        print()

        if cfg.openai_api_key:
            masked = cfg.openai_api_key[:7] + "..." + cfg.openai_api_key[-4:]
            out.kv("Current key", masked)

        key = input("  New OpenAI API key: ").strip()
        if not key:
            out.warn("No key entered — keeping current value.")
            return

        cfg.openai_api_key = key
        path = save_config(cfg)
        out.success(f"API key saved to {path}")


class ConfigSetStoreCommand(BaseCommand):
    name = "set-store"
    help = "Set the database filename (relative to data directory)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "filename",
            nargs="?",
            default=None,
            help="Database filename (resolved relative to data directory)",
        )
        parser.add_argument(
            "--default",
            action="store_true",
            help="Reset to default (context_use.db)",
        )

    async def execute(self, args: argparse.Namespace) -> None:
        cfg = load_config() if config_path().exists() else Config()

        if args.default:
            cfg.database_path = ""
            save_config(cfg)
            out.success(f"Database reset to default: {cfg.db_path}")
            return

        if args.filename is None:
            out.kv("Database", cfg.db_path)
            return

        cfg.database_path = args.filename
        save_config(cfg)
        out.success(f"Database set to: {cfg.db_path}")


class ConfigSetAgentCommand(BaseCommand):
    name = "set-agent"
    help = "Configure the agent backend"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "backend",
            choices=["adk"],
            help="Agent backend to use (adk = single-turn LlmAgent)",
        )

    async def execute(self, args: argparse.Namespace) -> None:
        cfg = load_config() if config_path().exists() else Config()
        backend = args.backend

        cfg.agent_backend = backend
        path = save_config(cfg)
        out.success(f"Agent backend set to '{backend}'. Config written to {path}")

        if backend == "adk":
            out.info("Requires the adk extra: uv sync --extra adk")

        print()
        out.header("Next steps:")
        out.next_step(
            "context-use pipeline", "ingest archives and generate memories first"
        )
        out.next_step("context-use agent --help", "see available agent skills")
        print()


class ConfigPathCommand(BaseCommand):
    name = "path"
    help = "Print config file location"

    async def execute(self, args: argparse.Namespace) -> None:
        print(config_path())


class ConfigGroup(CommandGroup):
    name = "config"
    help = "View and change settings"
    subcommands = [
        ConfigShowCommand,
        ConfigSetKeyCommand,
        ConfigSetStoreCommand,
        ConfigSetAgentCommand,
        ConfigPathCommand,
    ]
