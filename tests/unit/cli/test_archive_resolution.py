from __future__ import annotations

import argparse

import pytest

from context_use.cli.base import resolve_archive
from context_use.config import Config


def _namespace(
    provider: str | None,
    zip_path: str | None,
    zip_path_option: str | None = None,
    quick: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        provider=provider,
        zip_path=zip_path,
        zip_path_option=zip_path_option,
        quick=quick,
    )


def test_resolve_archive_quick_requires_zip_path(tmp_path) -> None:
    cfg = Config(data_dir=tmp_path / "data")
    args = _namespace(provider=None, zip_path=None, quick=True)

    with pytest.raises(SystemExit) as exc:
        resolve_archive(args, cfg, command="pipeline")
    assert exc.value.code == 1


def test_resolve_archive_quick_prompts_provider_with_zip_path(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    zip_file = tmp_path / "quick.zip"
    zip_file.write_bytes(b"dummy")
    cfg = Config(data_dir=tmp_path / "data")

    monkeypatch.setattr("context_use.cli.base.providers", lambda: ["chatgpt", "google"])
    monkeypatch.setattr("builtins.input", lambda _prompt: "2")

    args = _namespace(
        provider=None,
        zip_path=None,
        zip_path_option=str(zip_file),
        quick=True,
    )
    result = resolve_archive(args, cfg, command="pipeline")

    assert result is not None
    provider, path = result
    assert provider == "google"
    assert path == str(zip_file)


def test_resolve_archive_no_args_uses_interactive_archive_picker(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = Config(data_dir=tmp_path / "data")
    args = _namespace(provider=None, zip_path=None)

    monkeypatch.setattr(
        "context_use.cli.base.pick_archive_interactive",
        lambda _cfg: ("instagram", "/tmp/mock.zip"),
    )

    result = resolve_archive(args, cfg, command="pipeline")
    assert result == ("instagram", "/tmp/mock.zip")


def test_resolve_archive_known_provider_without_zip_path_exits(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = Config(data_dir=tmp_path / "data")

    monkeypatch.setattr("context_use.cli.base.providers", lambda: ["chatgpt", "google"])
    args = _namespace(provider="chatgpt", zip_path=None)

    with pytest.raises(SystemExit) as exc:
        resolve_archive(args, cfg, command="pipeline")
    assert exc.value.code == 1


def test_resolve_archive_standard_mode_uses_provider_and_zip_path(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    zip_file = tmp_path / "standard.zip"
    zip_file.write_bytes(b"dummy")
    cfg = Config(data_dir=tmp_path / "data")

    monkeypatch.setattr("context_use.cli.base.providers", lambda: ["chatgpt", "google"])

    args = _namespace(provider="chatgpt", zip_path=str(zip_file))
    result = resolve_archive(args, cfg, command="pipeline")

    assert result == ("chatgpt", str(zip_file))
