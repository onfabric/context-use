from __future__ import annotations

import argparse
import subprocess
import sys

from context_use.cli import output as out
from context_use.cli.base import (
    BaseCommand,
    CommandGroup,
    build_ctx,
)
from context_use.config import (
    Config,
    config_path,
    load_config,
    load_config_with_sources,
    save_config,
)

# ── show ─────────────────────────────────────────────────────────────────────


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
        out.kv("Embedding model", f"{cfg.openai_embedding_model} {badge('openai_embedding_model')}")

        if cfg.store_provider == "postgres":
            store_val = f"postgres ({cfg.db_host}:{cfg.db_port}/{cfg.db_name})"
        else:
            store_val = "memory (in-memory, no persistence)"
        out.kv("Store", f"{store_val} {badge('store_provider')}")

        if cfg.agent_backend:
            out.kv("Agent backend", f"{cfg.agent_backend} {badge('agent_backend')}")
        else:
            out.kv("Agent backend", f"{out.dim('not configured')} {badge('agent_backend')}")

        out.kv("Data directory", f"{cfg.data_dir} {badge('data_dir')}")

        print()
        out.info(f"{out.cyan('[env]')} = set by environment variable  "
                 f"{out.dim('[file]')} = from config file  "
                 f"{out.dim('[default]')} = built-in default")
        print()
        out.info("To change settings:")
        out.next_step("context-use config set-key", "change OpenAI API key")
        out.next_step("context-use config set-store postgres", "set up PostgreSQL")
        out.next_step("context-use config set-store memory", "switch to in-memory")
        out.next_step("context-use config set-agent adk", "configure agent backend")
        print()


# ── set-key ──────────────────────────────────────────────────────────────────


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


# ── set-store ────────────────────────────────────────────────────────────────


def _start_docker_postgres(cfg: Config) -> None:
    """Start a pgvector/pgvector Postgres container via ``docker run``."""
    probe = subprocess.run(["docker", "info"], capture_output=True, text=True)
    if probe.returncode != 0:
        out.error("Docker daemon is not running.")
        out.info("Start Docker Desktop (or the docker service) and try again:")
        out.next_step("context-use config set-store postgres")
        sys.exit(1)

    container_name = "context-use-postgres"

    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and "true" in result.stdout:
        out.success("Postgres container already running")
        return

    subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)

    out.info("Starting Postgres container...")
    result = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "-p",
            f"{cfg.db_port}:5432",
            "-e",
            f"POSTGRES_USER={cfg.db_user}",
            "-e",
            f"POSTGRES_PASSWORD={cfg.db_password}",
            "-e",
            f"POSTGRES_DB={cfg.db_name}",
            "-v",
            "context-use-pgdata:/var/lib/postgresql/data",
            "pgvector/pgvector:pg17",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        import time

        out.success(f"Postgres running on localhost:{cfg.db_port}")
        out.info("Waiting for Postgres to be ready...")
        time.sleep(3)
    else:
        out.error(f"Failed to start Postgres: {result.stderr.strip()}")
        sys.exit(1)


class ConfigSetStoreCommand(BaseCommand):
    name = "set-store"
    help = "Configure the store backend"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "backend",
            choices=["postgres", "memory"],
            help="Store backend to use",
        )

    async def execute(self, args: argparse.Namespace) -> None:
        import shutil

        cfg = load_config() if config_path().exists() else Config()
        backend = args.backend

        if backend == "memory":
            cfg.store_provider = "memory"
            path = save_config(cfg)
            out.success(f"Store set to in-memory. Config written to {path}")
            out.info("Data will only persist for the duration of a single command.")
            out.info(
                "Use 'context-use quickstart' to ingest + generate in one session."
            )
            return

        # postgres
        cfg.store_provider = "postgres"
        out.info("Setting up PostgreSQL for persistent storage across sessions.")
        out.info("For trying it out without PostgreSQL, run 'context-use quickstart'\n")

        if shutil.which("docker") is not None:
            prompt_text = "  Start a local Postgres container with Docker? [Y/n] "
            start_db = input(prompt_text).strip().lower()
            if start_db in ("", "y", "yes"):
                _start_docker_postgres(cfg)

        host = input(f"  Database host [{cfg.db_host}]: ").strip() or cfg.db_host
        port = input(f"  Database port [{cfg.db_port}]: ").strip() or str(cfg.db_port)
        name = input(f"  Database name [{cfg.db_name}]: ").strip() or cfg.db_name
        user = input(f"  Database user [{cfg.db_user}]: ").strip() or cfg.db_user
        pw_prompt = f"  Database password [{cfg.db_password}]: "
        password = input(pw_prompt).strip() or cfg.db_password
        cfg.db_host = host
        cfg.db_port = int(port)
        cfg.db_name = name
        cfg.db_user = user
        cfg.db_password = password

        path = save_config(cfg)
        out.success(f"PostgreSQL configured. Config written to {path}")

        try:
            ctx = build_ctx(cfg)
            await ctx.init()
            out.success("Database initialised")
        except Exception as exc:
            out.warn(f"Could not initialise database: {exc}")
            out.info("You can retry later with: context-use config set-store postgres")

        print()
        out.header("You're all set! Next steps:")
        print()
        out.info("Run the full pipeline:")
        out.next_step("context-use pipeline")
        out.info("Or step by step:")
        out.next_step("context-use ingest")
        out.next_step("context-use memories generate")
        out.info("Start the MCP server:")
        out.next_step("python -m context_use.ext.mcp_use.run")
        print()


# ── set-agent ────────────────────────────────────────────────────────────────


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

        if not cfg.uses_postgres:
            out.warn("The agent requires PostgreSQL for persistent storage.")
            out.info("Set it up first with:")
            out.next_step("context-use config set-store postgres")
            print()

        print()
        out.header("Next steps:")
        out.next_step(
            "context-use pipeline", "ingest archives and generate memories first"
        )
        out.next_step("context-use agent --help", "see available agent skills")
        print()


# ── path ─────────────────────────────────────────────────────────────────────


class ConfigPathCommand(BaseCommand):
    name = "path"
    help = "Print config file location"

    async def execute(self, args: argparse.Namespace) -> None:
        print(config_path())


# ── group ─────────────────────────────────────────────────────────────────────


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
