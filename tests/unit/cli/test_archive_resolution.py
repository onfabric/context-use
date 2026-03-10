from __future__ import annotations

import argparse

import pytest

from context_use.cli.base import resolve_archive
from context_use.config import Config


def _namespace(provider: str | None, zip_path: str | None) -> argparse.Namespace:
    return argparse.Namespace(provider=provider, zip_path=zip_path)


def test_resolve_archive_quick_uses_single_zip_path_arg(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    zip_file = tmp_path / "quick.zip"
    zip_file.write_bytes(b"dummy")
    cfg = Config(data_dir=tmp_path / "data")

    monkeypatch.setattr("context_use.cli.base.providers", lambda: ["chatgpt", "google"])
    monkeypatch.setattr("builtins.input", lambda _prompt: "2")

    args = _namespace(provider=str(zip_file), zip_path=None)
    result = resolve_archive(args, cfg, command="pipeline", quick=True)

    assert result is not None
    provider, path = result
    assert provider == "google"
    assert path == str(zip_file)


def test_resolve_archive_quick_requires_zip_path(tmp_path) -> None:
    cfg = Config(data_dir=tmp_path / "data")
    args = _namespace(provider=None, zip_path=None)

    with pytest.raises(SystemExit) as exc:
        resolve_archive(args, cfg, command="pipeline", quick=True)

    assert exc.value.code == 1


def test_resolve_archive_quick_prompts_provider_even_with_explicit_provider(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    zip_file = tmp_path / "archive.zip"
    zip_file.write_bytes(b"dummy")
    cfg = Config(data_dir=tmp_path / "data")

    monkeypatch.setattr(
        "context_use.cli.base.providers", lambda: ["chatgpt", "claude", "instagram"]
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "3")

    args = _namespace(provider="chatgpt", zip_path=str(zip_file))
    result = resolve_archive(args, cfg, command="pipeline", quick=True)

    assert result is not None
    provider, path = result
    assert provider == "instagram"
    assert path == str(zip_file)


def test_resolve_archive_standard_mode_uses_provider_and_zip_path(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    zip_file = tmp_path / "standard.zip"
    zip_file.write_bytes(b"dummy")
    cfg = Config(data_dir=tmp_path / "data")

    monkeypatch.setattr("context_use.cli.base.providers", lambda: ["chatgpt", "google"])

    args = _namespace(provider="chatgpt", zip_path=str(zip_file))
    result = resolve_archive(args, cfg, command="pipeline", quick=False)

    assert result == ("chatgpt", str(zip_file))
