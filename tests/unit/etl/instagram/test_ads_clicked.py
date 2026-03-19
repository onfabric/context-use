from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from context_use.providers.instagram.ads_clicked.pipe import InstagramAdsClickedPipe
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.instagram.conftest import INSTAGRAM_ADS_CLICKED_V1_JSON


class TestInstagramAdsClickedPipe(PipeTestKit):
    pipe_class = InstagramAdsClickedPipe
    expected_extract_count = 3
    expected_transform_count = 3
    fixture_data = INSTAGRAM_ADS_CLICKED_V1_JSON
    fixture_key = "archive/ads_information/ads_and_topics/ads_clicked.json"
    expected_fibre_kind = "ClickAd"
    snapshot_cases = [
        (
            [
                {
                    "timestamp": 1771848416,
                    "media": [],
                    "label_values": [
                        {"label": "Action", "value": "Click"},
                        {"label": "Title", "value": "Game on!"},
                        {
                            "label": "URL",
                            "value": "https://www.instagram.com/p/SNAP_AD/",
                            "href": "https://www.instagram.com/p/SNAP_AD/",
                        },
                    ],
                    "fbid": "17841401108516601:99999:1771848416:3:AdsHistoryData",
                }
            ],
            {
                "unique_key": "557c7ee0c2211a38",
                "preview": "Clicked ad Game on! on instagram",
                "asat": datetime(2026, 2, 23, 12, 6, 56, tzinfo=UTC),
                "payload": {
                    "type": "View",
                    "published": "2026-02-23T12:06:56Z",
                    "object": {
                        "type": "Object",
                        "name": "Game on!",
                        "url": "https://www.instagram.com/p/SNAP_AD/",
                        "fibreKind": "Ad",
                    },
                    "fibreKind": "ClickAd",
                },
            },
        ),
    ]

    def test_non_array_produces_no_rows(self, tmp_path: Path) -> None:
        storage = DiskStorage(str(tmp_path / "store"))
        assert self.fixture_key is not None
        key = self.fixture_key
        storage.write(key, b'{"not": "an array"}')
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        assert len(rows) == 0

    def test_record_fields_with_title(self, extracted_records) -> None:
        record = extracted_records[0]
        assert record.title == "Summer sale!"
        assert record.ad_url == "https://www.instagram.com/p/SYNTHETIC_AD_CLICK_1/"
        assert record.timestamp == 1770753730
        assert record.source is not None

    def test_record_fields_without_title(self, extracted_records) -> None:
        record = extracted_records[1]
        assert record.title is None
        assert record.ad_url == "https://www.instagram.com/p/SYNTHETIC_AD_CLICK_2/"
        assert record.timestamp == 1770840130

    def test_payload_object_is_ad(self, transformed_rows) -> None:
        for row in transformed_rows:
            obj = row.payload["object"]
            assert obj["type"] == "Object"
            assert obj["fibreKind"] == "Ad"

    def test_payload_object_url(self, transformed_rows) -> None:
        assert (
            transformed_rows[0].payload["object"]["url"]
            == "https://www.instagram.com/p/SYNTHETIC_AD_CLICK_1/"
        )

    def test_payload_ad_name_from_title(self, transformed_rows) -> None:
        assert transformed_rows[0].payload["object"]["name"] == "Summer sale!"

    def test_payload_no_name_when_no_title(self, transformed_rows) -> None:
        assert "name" not in transformed_rows[1].payload["object"]

    def test_preview_includes_clicked_and_title(self, transformed_rows) -> None:
        preview = transformed_rows[0].preview
        assert "Clicked" in preview
        assert "Summer sale!" in preview
        assert "instagram" in preview.lower()

    def test_preview_without_title(self, transformed_rows) -> None:
        preview = transformed_rows[1].preview
        assert preview == "Clicked ad on instagram"
