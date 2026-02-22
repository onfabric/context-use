"""Configuration management for the context-use CLI.

Reads/writes a TOML config file and provides a typed Config dataclass.
Default location: ``~/.config/context-use/config.toml``.
Override with the ``CONTEXT_USE_CONFIG`` environment variable.

Data directory layout::

    data/
      input/       <- drop your .zip archives here
      output/      <- exported memories and profiles land here
      storage/     <- internal extracted archive data
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_CONFIG_DIR = Path("~/.config/context-use").expanduser()
_DEFAULT_DATA_DIR = Path("./data")


def _config_path() -> Path:
    env = os.environ.get("CONTEXT_USE_CONFIG")
    if env:
        return Path(env).expanduser()
    return _DEFAULT_CONFIG_DIR / "config.toml"


@dataclass
class Config:
    openai_api_key: str = ""

    # Store backend: "memory" (default, no external deps) or "postgres"
    store_provider: str = "memory"

    # Postgres settings (only used when store_provider == "postgres")
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "context_use"
    db_user: str = "postgres"
    db_password: str = "postgres"

    data_dir: str = str(_DEFAULT_DATA_DIR)

    @property
    def is_configured(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def input_dir(self) -> Path:
        return Path(self.data_dir) / "input"

    @property
    def output_dir(self) -> Path:
        return Path(self.data_dir) / "output"

    @property
    def storage_path(self) -> str:
        return str(Path(self.data_dir) / "storage")

    @property
    def uses_postgres(self) -> bool:
        return self.store_provider == "postgres"

    def ensure_dirs(self) -> None:
        """Create the data directory structure if it doesn't exist."""
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        Path(self.storage_path).mkdir(parents=True, exist_ok=True)


def load_config() -> Config:
    """Load config from disk, falling back to defaults + env overrides."""
    path = _config_path()
    cfg = Config()

    if path.exists():
        with open(path, "rb") as f:
            data = tomllib.load(f)
        openai_section = data.get("openai", {})
        store_section = data.get("store", {})
        db_section = data.get("database", {})
        data_section = data.get("data", {})

        cfg.openai_api_key = openai_section.get("api_key", cfg.openai_api_key)

        cfg.store_provider = store_section.get("provider", cfg.store_provider)

        # Legacy: if [database] section exists but no [store] section,
        # infer postgres provider from the presence of DB settings
        if db_section and "store" not in data:
            cfg.store_provider = "postgres"

        cfg.db_host = db_section.get("host", cfg.db_host)
        cfg.db_port = int(db_section.get("port", cfg.db_port))
        cfg.db_name = db_section.get("name", cfg.db_name)
        cfg.db_user = db_section.get("user", cfg.db_user)
        cfg.db_password = db_section.get("password", cfg.db_password)

        cfg.data_dir = data_section.get("dir", cfg.data_dir)

    # Environment variables always take precedence
    cfg.openai_api_key = os.environ.get("OPENAI_API_KEY", cfg.openai_api_key)
    cfg.store_provider = os.environ.get("CONTEXT_USE_STORE", cfg.store_provider)
    cfg.db_host = os.environ.get("POSTGRES_HOST", cfg.db_host)
    cfg.db_port = int(os.environ.get("POSTGRES_PORT", str(cfg.db_port)))
    cfg.db_name = os.environ.get("POSTGRES_DB", cfg.db_name)
    cfg.db_user = os.environ.get("POSTGRES_USER", cfg.db_user)
    cfg.db_password = os.environ.get("POSTGRES_PASSWORD", cfg.db_password)

    return cfg


def save_config(cfg: Config) -> Path:
    """Write config to the TOML file. Returns the path written."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "[openai]",
        f'api_key = "{cfg.openai_api_key}"',
        "",
        "[store]",
        f'provider = "{cfg.store_provider}"',
        "",
    ]

    if cfg.uses_postgres:
        lines.extend(
            [
                "[database]",
                f'host = "{cfg.db_host}"',
                f"port = {cfg.db_port}",
                f'name = "{cfg.db_name}"',
                f'user = "{cfg.db_user}"',
                f'password = "{cfg.db_password}"',
                "",
            ]
        )

    lines.extend(
        [
            "[data]",
            f'dir = "{cfg.data_dir}"',
            "",
        ]
    )

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def config_exists() -> bool:
    return _config_path().exists()


def config_path_display() -> str:
    return str(_config_path())
