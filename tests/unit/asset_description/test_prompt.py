from __future__ import annotations

from datetime import UTC, datetime

from context_use.asset_description.prompt import (
    AssetDescriptionPromptBuilder,
    AssetDescriptionSchema,
)
from context_use.models.thread import Thread


def _make_thread(
    *,
    thread_id: str = "t1",
    asset_uri: str | None = "archive/pic.jpg",
    caption: str | None = None,
    content: str | None = None,
) -> Thread:
    obj: dict = {"type": "Image"}
    if caption is not None:
        obj["content"] = caption
    payload = {"type": "Create", "fibre_kind": "Create", "object": obj}
    return Thread(
        id=thread_id,
        unique_key=f"uk-{thread_id}",
        provider="Instagram",
        interaction_type="instagram_posts",
        payload=payload,
        version="1.1.0",
        asat=datetime(2025, 1, 1, tzinfo=UTC),
        asset_uri=asset_uri,
        content=content,
    )


class TestAssetDescriptionPromptBuilder:
    def test_filters_non_asset_threads(self) -> None:
        threads = [
            _make_thread(thread_id="a1", asset_uri="archive/pic.jpg"),
            _make_thread(thread_id="a2", asset_uri=None),
        ]
        builder = AssetDescriptionPromptBuilder(threads)
        prompts = builder.build()
        assert len(prompts) == 1
        assert prompts[0].item_id == "a1"

    def test_filters_video_assets(self) -> None:
        threads = [
            _make_thread(thread_id="img", asset_uri="archive/pic.jpg"),
            _make_thread(thread_id="mp4", asset_uri="archive/clip.mp4"),
            _make_thread(thread_id="mov", asset_uri="archive/clip.mov"),
            _make_thread(thread_id="webm", asset_uri="archive/clip.webm"),
            _make_thread(thread_id="png", asset_uri="archive/shot.png"),
        ]
        builder = AssetDescriptionPromptBuilder(threads)
        prompts = builder.build()
        ids = [p.item_id for p in prompts]
        assert ids == ["img", "png"]

    def test_uses_raw_content_not_enriched(self) -> None:
        thread = _make_thread(
            caption="sunset at the beach",
            content=(
                "A person watching a golden sunset at the beach.\n\nsunset at the beach"
            ),
        )
        builder = AssetDescriptionPromptBuilder([thread])
        prompts = builder.build()
        assert len(prompts) == 1
        assert "sunset at the beach" in prompts[0].prompt
        assert "A person watching" not in prompts[0].prompt

    def test_asset_uris_is_single_item_list(self) -> None:
        thread = _make_thread(asset_uri="archive/photo.jpg")
        prompts = AssetDescriptionPromptBuilder([thread]).build()
        assert prompts[0].asset_uris == ["archive/photo.jpg"]

    def test_fallback_when_no_caption(self) -> None:
        thread = _make_thread(caption=None)
        prompts = AssetDescriptionPromptBuilder([thread]).build()
        assert "No caption provided" in prompts[0].prompt

    def test_response_schema_set(self) -> None:
        thread = _make_thread()
        prompts = AssetDescriptionPromptBuilder([thread]).build()
        assert prompts[0].response_schema == AssetDescriptionSchema.json_schema()

    def test_empty_threads_yields_no_prompts(self) -> None:
        prompts = AssetDescriptionPromptBuilder([]).build()
        assert prompts == []


class TestAssetDescriptionSchema:
    def test_json_schema_has_description_field(self) -> None:
        schema = AssetDescriptionSchema.json_schema()
        assert "description" in schema["properties"]

    def test_format_schema_for_prompt(self) -> None:
        text = AssetDescriptionSchema.format_schema_for_prompt()
        assert "`description`" in text
