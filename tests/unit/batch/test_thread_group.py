from __future__ import annotations

from datetime import UTC, datetime

import pytest

from context_use.batch.grouper import ThreadGroup
from context_use.models.thread import Thread


def _thread(unique_key: str = "k") -> Thread:
    return Thread(
        unique_key=unique_key,
        provider="p",
        interaction_type="t",
        preview="",
        payload={"fibre_kind": "TextMessage", "content": "x"},
        version="1",
        asat=datetime.now(UTC),
    )


def test_thread_group_accepts_iterable_of_threads() -> None:
    t = _thread()
    g = ThreadGroup(threads=[t])
    assert g.threads == (t,)
    assert g.group_id


def test_thread_group_rejects_empty_iterable() -> None:
    with pytest.raises(ValueError, match="ThreadGroup requires at least one thread"):
        ThreadGroup(threads=[])


def test_thread_group_custom_group_id() -> None:
    t = _thread()
    g = ThreadGroup(threads=[t], group_id="fixed-id")
    assert g.group_id == "fixed-id"
