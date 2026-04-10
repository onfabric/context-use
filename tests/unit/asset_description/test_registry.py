from __future__ import annotations

from context_use.providers.registry import get_asset_description_interaction_types


class TestGetAssetDescriptionInteractionTypes:
    def test_returns_opted_in_types(self) -> None:
        import context_use.providers  # noqa: F401 — trigger registration

        types = get_asset_description_interaction_types()
        assert "instagram_posts" in types
        assert "instagram_stories" in types
        assert "instagram_reels" in types

    def test_excludes_non_opted_types(self) -> None:
        import context_use.providers  # noqa: F401

        types = get_asset_description_interaction_types()
        assert "chatgpt_conversations" not in types
        assert "instagram_comments" not in types
