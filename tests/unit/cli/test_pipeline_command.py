from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime, timedelta

from context_use.cli.commands.pipeline import PipelineCommand


def test_resolve_since_uses_latest_thread_as_anchor() -> None:
    command = PipelineCommand()
    latest_thread_asat = datetime(2025, 2, 15, 16, 30, tzinfo=UTC)
    args = Namespace(last_days=7, quick=False)

    since = command._resolve_since(args, latest_thread_asat)

    assert since == latest_thread_asat - timedelta(days=7)


def test_resolve_since_uses_quick_default_window_from_latest_thread() -> None:
    command = PipelineCommand()
    latest_thread_asat = datetime(2025, 2, 15, 16, 30, tzinfo=UTC)
    args = Namespace(last_days=None, quick=True)

    since = command._resolve_since(args, latest_thread_asat)

    assert since == latest_thread_asat - timedelta(days=30)


def test_resolve_since_returns_none_without_window() -> None:
    command = PipelineCommand()
    latest_thread_asat = datetime(2025, 2, 15, 16, 30, tzinfo=UTC)
    args = Namespace(last_days=None, quick=False)

    since = command._resolve_since(args, latest_thread_asat)

    assert since is None


def test_resolve_since_returns_none_when_latest_thread_missing() -> None:
    command = PipelineCommand()
    args = Namespace(last_days=14, quick=False)

    since = command._resolve_since(args, None)

    assert since is None
