"""Tests for ChatGPT transform strategy."""

import json
from pathlib import Path

import pandas as pd
import pytest

from context_use.etl.models.etl_task import EtlTask, EtlTaskStatus
from context_use.etl.providers.chatgpt.conversations import (
    ChatGPTConversationsExtractionStrategy,
    ChatGPTConversationsTransformStrategy,
)
from context_use.storage.disk import DiskStorage
from tests.conftest import CHATGPT_CONVERSATIONS


@pytest.fixture()
def chatgpt_raw_batches(tmp_path: Path):
    storage = DiskStorage(str(tmp_path / "store"))
    key = "archive/conversations.json"
    storage.write(key, json.dumps(CHATGPT_CONVERSATIONS).encode())

    extraction = ChatGPTConversationsExtractionStrategy()
    task = EtlTask(
        archive_id="a1",
        provider="chatgpt",
        interaction_type="chatgpt_conversations",
        source_uri=key,
        status=EtlTaskStatus.CREATED.value,
    )
    return extraction.extract(task, storage), task


class TestChatGPTTransform:
    def test_produces_thread_columns(self, chatgpt_raw_batches):
        raw, task = chatgpt_raw_batches
        transform = ChatGPTConversationsTransformStrategy()
        result = transform.transform(task, raw)

        assert len(result) >= 1
        df = result[0]
        required = {
            "unique_key",
            "provider",
            "interaction_type",
            "preview",
            "payload",
            "source",
            "version",
            "asat",
            "asset_uri",
        }
        assert required.issubset(set(df.columns))

    def test_payload_is_dict(self, chatgpt_raw_batches):
        raw, task = chatgpt_raw_batches
        transform = ChatGPTConversationsTransformStrategy()
        result = transform.transform(task, raw)
        df = result[0]

        for payload in df["payload"]:
            assert isinstance(payload, dict)
            assert "fibre_kind" in payload

    def test_send_and_receive(self, chatgpt_raw_batches):
        raw, task = chatgpt_raw_batches
        transform = ChatGPTConversationsTransformStrategy()
        result = transform.transform(task, raw)
        df = pd.concat(result)

        kinds = df["payload"].apply(lambda p: p["fibre_kind"]).tolist()
        assert "SendMessage" in kinds
        assert "ReceiveMessage" in kinds

    def test_previews_non_empty(self, chatgpt_raw_batches):
        raw, task = chatgpt_raw_batches
        transform = ChatGPTConversationsTransformStrategy()
        result = transform.transform(task, raw)
        df = pd.concat(result)

        for preview in df["preview"]:
            assert preview, "Preview should not be empty"
