from __future__ import annotations

import pytest
from pydantic import ValidationError

from context_use.providers.google.schemas import GoogleActivityFileItem
from context_use.providers.google.youtube.schemas import (
    GoogleYoutubeFileItem,
    GoogleYoutubeSubtitle,
)


class TestGoogleActivityFileItem:
    def test_valid_search_item(self) -> None:
        item = GoogleActivityFileItem.model_validate(
            {
                "header": "Search",
                "title": "Searched for python",
                "time": "2025-06-15T10:30:00.000Z",
                "products": ["Search"],
                "activityControls": ["Web & App Activity"],
            }
        )
        assert item.header == "Search"
        assert item.title == "Searched for python"
        assert item.titleUrl is None

    def test_valid_item_with_all_optional_fields(self) -> None:
        item = GoogleActivityFileItem.model_validate(
            {
                "header": "Discover",
                "title": "Visited Content From Discover",
                "time": "2025-07-20T12:30:00.000Z",
                "titleUrl": "https://example.com",
                "products": ["Discover"],
                "activityControls": ["Web & App Activity"],
                "locationInfos": [{"name": "At this area"}],
                "details": [{"name": "Technology - viewed"}],
                "subtitles": [{"name": "Including topics:"}],
            }
        )
        assert item.locationInfos == [{"name": "At this area"}]
        assert item.details == [{"name": "Technology - viewed"}]

    def test_tolerates_extra_fields(self) -> None:
        item = GoogleActivityFileItem.model_validate(
            {
                "header": "Search",
                "title": "Searched for python",
                "time": "2025-06-15T10:30:00.000Z",
                "brandNewField": "should not break",
            }
        )
        assert item.title == "Searched for python"

    def test_missing_title_raises(self) -> None:
        with pytest.raises(ValidationError):
            GoogleActivityFileItem.model_validate(
                {
                    "header": "Search",
                    "time": "2025-06-15T10:30:00.000Z",
                }
            )

    def test_missing_time_raises(self) -> None:
        with pytest.raises(ValidationError):
            GoogleActivityFileItem.model_validate(
                {
                    "header": "Search",
                    "title": "Searched for python",
                }
            )

    def test_missing_header_raises(self) -> None:
        with pytest.raises(ValidationError):
            GoogleActivityFileItem.model_validate(
                {
                    "title": "Searched for python",
                    "time": "2025-06-15T10:30:00.000Z",
                }
            )

    def test_invalid_time_format_raises(self) -> None:
        with pytest.raises(ValidationError):
            GoogleActivityFileItem.model_validate(
                {
                    "header": "Search",
                    "title": "Searched for python",
                    "time": "not-a-date",
                }
            )


class TestGoogleYoutubeSubtitle:
    def test_valid_with_url(self) -> None:
        sub = GoogleYoutubeSubtitle.model_validate(
            {
                "name": "Cooking Channel",
                "url": "https://www.youtube.com/channel/UC000001",
            }
        )
        assert sub.name == "Cooking Channel"
        assert sub.url == "https://www.youtube.com/channel/UC000001"

    def test_valid_without_url(self) -> None:
        sub = GoogleYoutubeSubtitle.model_validate({"name": "Some Channel"})
        assert sub.url is None

    def test_missing_name_raises(self) -> None:
        with pytest.raises(ValidationError):
            GoogleYoutubeSubtitle.model_validate({"url": "https://example.com"})


class TestGoogleYoutubeFileItem:
    def test_valid_watched_item(self) -> None:
        item = GoogleYoutubeFileItem.model_validate(
            {
                "header": "YouTube",
                "title": "Watched How to Make Pasta at Home",
                "titleUrl": "https://www.youtube.com/watch?v=abc123",
                "subtitles": [
                    {
                        "name": "Cooking Channel",
                        "url": "https://www.youtube.com/channel/UC000001",
                    }
                ],
                "time": "2025-06-15T10:30:00.000Z",
                "products": ["YouTube"],
            }
        )
        assert item.subtitles is not None
        assert len(item.subtitles) == 1
        assert item.subtitles[0].name == "Cooking Channel"

    def test_valid_without_subtitles(self) -> None:
        item = GoogleYoutubeFileItem.model_validate(
            {
                "header": "YouTube",
                "title": "Searched for pasta recipes",
                "time": "2025-06-15T10:20:00.000Z",
                "products": ["YouTube"],
            }
        )
        assert item.subtitles is None

    def test_subtitle_missing_name_raises(self) -> None:
        with pytest.raises(ValidationError):
            GoogleYoutubeFileItem.model_validate(
                {
                    "header": "YouTube",
                    "title": "Watched something",
                    "time": "2025-06-15T10:30:00.000Z",
                    "subtitles": [{"url": "https://example.com"}],
                }
            )

    def test_tolerates_extra_fields(self) -> None:
        item = GoogleYoutubeFileItem.model_validate(
            {
                "header": "YouTube",
                "title": "Watched something",
                "time": "2025-06-15T10:30:00.000Z",
                "futureField": True,
            }
        )
        assert item.title == "Watched something"
