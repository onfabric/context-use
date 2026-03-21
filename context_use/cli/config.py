from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal, NamedTuple

from context_use.llm.litellm.models import OpenAIEmbeddingModel, OpenAIModel

if TYPE_CHECKING:
    from context_use.core import ContextUse

_DEFAULT_MODEL = OpenAIModel.GPT_5_2
_DEFAULT_EMBEDDING_MODEL = OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE
_DEFAULT_DATA_DIR = Path("./context-use-data")

ConfigSource = Literal["env", "file", "default"]


def config_path() -> Path:
    env = os.environ.get("CONTEXT_USE_CONFIG")
    if env:
        return Path(env).expanduser()
    return Path("~/.config/context-use").expanduser() / "config.toml"


class _FieldSpec(NamedTuple):
    attr: str
    toml_section: str
    toml_key: str
    env_var: str | None
    cast: type = str


_FIELDS: list[_FieldSpec] = [
    _FieldSpec("openai_api_key", "openai", "api_key", "OPENAI_API_KEY"),
    _FieldSpec("openai_model", "openai", "model", "OPENAI_MODEL"),
    _FieldSpec(
        "openai_embedding_model", "openai", "embedding_model", "OPENAI_EMBEDDING_MODEL"
    ),
    _FieldSpec("database_path", "store", "path", "CONTEXT_USE_DB_PATH"),
    _FieldSpec("data_dir", "data", "dir", "CONTEXT_USE_DATA_DIR", Path),
]


@dataclass
class Config:
    openai_api_key: str = ""
    openai_model: str = _DEFAULT_MODEL
    openai_embedding_model: str = _DEFAULT_EMBEDDING_MODEL

    database_path: str = "context_use.db"
    """
    SQLite database path.
    Relative to the `data_dir`/`store` directory.
    Default: `./context-use-data/store/context_use.db`
    """

    data_dir: Path = field(default_factory=lambda: _DEFAULT_DATA_DIR)

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
    def storage_path(self) -> Path:
        return self.data_dir / "storage"

    @property
    def store_path(self) -> Path:
        return self.data_dir / "store"

    @property
    def db_path(self) -> str:
        return str(self.store_path / self.database_path)

    def ensure_dirs(self) -> None:
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.store_path.mkdir(parents=True, exist_ok=True)


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

    if cfg.database_path:
        lines.extend(
            [
                "[store]",
                f'path = "{cfg.database_path}"',
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

    from context_use.core import ContextUse
    from context_use.llm.litellm.clients import (
        LiteLLMBatchClient,
        LiteLLMSyncClient,
    )
    from context_use.llm.litellm.config import OpenAIConfig
    from context_use.storage.disk import DiskStorage
    from context_use.store.sqlite import SqliteStore

    storage = DiskStorage(str(cfg.storage_path))
    store = SqliteStore(path=cfg.db_path)

    provider_config = OpenAIConfig(
        model=OpenAIModel(cfg.openai_model),
        embedding_model=OpenAIEmbeddingModel(cfg.openai_embedding_model),
        api_key=cfg.openai_api_key,
    )

    if llm_mode == "sync":
        llm_client = LiteLLMSyncClient(provider_config)
    else:
        llm_client = LiteLLMBatchClient(provider_config)

    return ContextUse(storage=storage, store=store, llm_client=llm_client)
