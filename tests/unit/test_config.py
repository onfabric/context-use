from __future__ import annotations

from pathlib import Path

import pytest

from context_use.config import load_config


class TestDataDirEnvVar:
    def test_data_dir_from_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("CONTEXT_USE_DATA_DIR", str(tmp_path / "custom"))
        monkeypatch.setenv("CONTEXT_USE_CONFIG", str(tmp_path / "nonexistent.toml"))
        cfg = load_config()
        assert cfg.data_dir == tmp_path / "custom"

    def test_data_dir_default_without_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("CONTEXT_USE_DATA_DIR", raising=False)
        monkeypatch.setenv("CONTEXT_USE_CONFIG", str(tmp_path / "nonexistent.toml"))
        cfg = load_config()
        assert cfg.data_dir == Path("./context-use-data")
