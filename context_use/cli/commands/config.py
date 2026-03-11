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

        if cfg.api_base:
            out.kv("API base URL", f"{cfg.api_base} {badge('api_base')}")
        else:
            out.kv("API base URL", f"{out.dim('default (OpenAI)')} {badge('api_base')}")

        out.kv("Store", f"sqlite ({cfg.db_path}) {badge('database_path')}")
        out.kv("Data directory", f"{cfg.data_dir} {badge('data_dir')}")

        print()
        out.info(
            f"{out.cyan('[env]')} = set by environment variable  "
            f"{out.dim('[file]')} = from config file  "
            f"{out.dim('[default]')} = built-in default"
        )
        print()
        out.info("To change settings:")
        out.next_step("context-use config set-key", "change API key")
        out.next_step(
            "context-use config set-url <url>",
            "set custom API base URL (e.g. LM Studio)",
        )
        print()


class ConfigSetKeyCommand(BaseCommand):
    name = "set-key"
    help = "Change OpenAI API key"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "key",
            nargs="?",
            default=None,
            help="OpenAI API key (omit to enter interactively)",
        )

    async def execute(self, args: argparse.Namespace) -> None:
        cfg = load_config() if config_path().exists() else Config()

        if args.key:
            key = args.key.strip()
        else:
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


class ConfigSetUrlCommand(BaseCommand):
    name = "set-url"
    help = "Set a custom API base URL (e.g. http://localhost:1234/v1 for LM Studio)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "url",
            nargs="?",
            default=None,
            help="Base URL for an OpenAI-compatible API (omit to enter interactively)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Remove the custom base URL and revert to the default (OpenAI)",
        )

    async def execute(self, args: argparse.Namespace) -> None:
        cfg = load_config() if config_path().exists() else Config()

        if args.clear:
            cfg.api_base = ""
            path = save_config(cfg)
            out.success(
                f"Custom base URL cleared — using default (OpenAI). Saved to {path}"
            )
            return

        if args.url:
            url = args.url.strip()
        else:
            out.info("Set a custom base URL for an OpenAI-compatible API.")
            out.info("Example: http://localhost:1234/v1 (LM Studio)")
            print()

            if cfg.api_base:
                out.kv("Current URL", cfg.api_base)

            url = input("  API base URL: ").strip()
            if not url:
                out.warn("No URL entered — keeping current value.")
                return

        cfg.api_base = url
        path = save_config(cfg)
        out.success(f"API base URL saved to {path}")
        out.info("Use --quick mode for local APIs (batch mode requires OpenAI).")


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
        ConfigSetUrlCommand,
        ConfigPathCommand,
    ]
