from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, NamedTuple

from context_use import ContextUse
from context_use.llm.litellm import LiteLLMBatchClient, LiteLLMSyncClient
from context_use.llm.models import OpenAIEmbeddingModel, OpenAIModel
from context_use.storage.disk import DiskStorage

_DEFAULT_MODEL = OpenAIModel.GPT_5_2
_DEFAULT_EMBEDDING_MODEL = OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE

ConfigSource = Literal["env", "file", "default"]


def config_path() -> Path:
    env = os.environ.get("CONTEXT_USE_CONFIG")
    if env:
        return Path(env).expanduser()
    return Path("~/.config/context-use").expanduser() / "config.toml"


class _FieldSpec(NamedTuple):
    attr: str  # Config dataclass field name
    toml_section: str  # TOML [section]
    toml_key: str  # key within that section
    env_var: str | None  # env var name, or None if no env override
    cast: type = str  # type to coerce raw values to


_FIELDS: list[_FieldSpec] = [
    _FieldSpec("openai_api_key", "openai", "api_key", "OPENAI_API_KEY"),
    _FieldSpec("openai_model", "openai", "model", "OPENAI_MODEL"),
    _FieldSpec(
        "openai_embedding_model", "openai", "embedding_model", "OPENAI_EMBEDDING_MODEL"
    ),
    _FieldSpec("store_provider", "store", "provider", "CONTEXT_USE_STORE"),
    _FieldSpec("db_host", "database", "host", "POSTGRES_HOST"),
    _FieldSpec("db_port", "database", "port", "POSTGRES_PORT", int),
    _FieldSpec("db_name", "database", "name", "POSTGRES_DB"),
    _FieldSpec("db_user", "database", "user", "POSTGRES_USER"),
    _FieldSpec("db_password", "database", "password", "POSTGRES_PASSWORD"),
    _FieldSpec("agent_backend", "agent", "backend", "CONTEXT_USE_AGENT_BACKEND"),
    _FieldSpec("data_dir", "data", "dir", None, Path),
]


@dataclass
class Config:
    openai_api_key: str = ""

    # LLM models — shared by the memories pipeline and the personal agent
    openai_model: str = _DEFAULT_MODEL
    openai_embedding_model: str = _DEFAULT_EMBEDDING_MODEL

    # Store backend: "sqlite" (default), "memory", or "postgres"
    store_provider: str = "sqlite"

    # Postgres settings (only used when store_provider == "postgres")
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "context_use"
    db_user: str = "postgres"
    db_password: str = "postgres"

    # Agent backend: "" (not configured), "adk", …
    agent_backend: str = ""

    data_dir: Path = field(default_factory=lambda: Path("./data"))

    @property
    def is_configured(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def input_dir(self) -> Path:
        return self.data_dir / "input"

    @property
    def output_dir(self) -> Path:
        return self.data_dir / "output"

    @property
    def storage_path(self) -> str:
        return str(self.data_dir / "storage")

    @property
    def db_path(self) -> str:
        return str(self.data_dir / "context_use.db")

    @property
    def uses_postgres(self) -> bool:
        return self.store_provider == "postgres"

    def ensure_dirs(self) -> None:
        """Create the data directory structure if it doesn't exist."""
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "storage").mkdir(parents=True, exist_ok=True)


def load_config_with_sources() -> tuple[Config, dict[str, ConfigSource]]:
    """Load config and return it alongside a per-field source map.

    Each key in the returned dict is a :class:`Config` field name; the value is
    one of ``"env"``, ``"file"``, or ``"default"`` indicating where the active
    value came from.  Env vars always take precedence over the file.
    """
    path = config_path()
    cfg = Config()
    sources: dict[str, ConfigSource] = {spec.attr: "default" for spec in _FIELDS}
    toml_data: dict = {}

    if path.exists():
        with open(path, "rb") as f:
            toml_data = tomllib.load(f)

    for spec in _FIELDS:
        section = toml_data.get(spec.toml_section, {})
        if spec.toml_key in section:
            setattr(cfg, spec.attr, spec.cast(section[spec.toml_key]))
            sources[spec.attr] = "file"
        if spec.env_var and (env_val := os.environ.get(spec.env_var)) is not None:
            setattr(cfg, spec.attr, spec.cast(env_val))
            sources[spec.attr] = "env"

    return cfg, sources


def load_config() -> Config:
    """Load config from disk, falling back to defaults + env overrides."""
    cfg, _ = load_config_with_sources()
    return cfg


def save_config(cfg: Config) -> Path:
    """Write config to the TOML file. Returns the path written."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "[openai]",
        f'api_key = "{cfg.openai_api_key}"',
    ]
    if cfg.openai_model != _DEFAULT_MODEL:
        lines.append(f'model = "{cfg.openai_model}"')
    if cfg.openai_embedding_model != _DEFAULT_EMBEDDING_MODEL:
        lines.append(f'embedding_model = "{cfg.openai_embedding_model}"')
    lines.append("")

    lines += [
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

    if cfg.agent_backend:
        lines.extend(
            [
                "[agent]",
                f'backend = "{cfg.agent_backend}"',
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


def build_ctx(cfg: Config, *, llm_mode: str = "batch") -> ContextUse:
    """Construct a :class:`ContextUse` from a :class:`Config`."""

    storage = DiskStorage(cfg.storage_path)

    if cfg.store_provider == "postgres":
        from context_use.store.postgres import PostgresStore

        store = PostgresStore(
            host=cfg.db_host,
            port=cfg.db_port,
            database=cfg.db_name,
            user=cfg.db_user,
            password=cfg.db_password,
        )
    elif cfg.store_provider == "sqlite":
        from context_use.store.sqlite import SqliteStore

        store = SqliteStore(path=cfg.db_path)
    else:
        raise ValueError(
            f"Unknown store provider {cfg.store_provider!r}. "
            "Supported: 'sqlite', 'postgres'."
        )

    api_key = cfg.openai_api_key or ""
    model = OpenAIModel(cfg.openai_model)
    embedding_model = OpenAIEmbeddingModel(cfg.openai_embedding_model)

    if llm_mode == "sync":
        llm_client = LiteLLMSyncClient(
            model=model,
            api_key=api_key,
            embedding_model=embedding_model,
        )
    else:
        llm_client = LiteLLMBatchClient(
            model=model,
            api_key=api_key,
            embedding_model=embedding_model,
        )

    return ContextUse(storage=storage, store=store, llm_client=llm_client)
