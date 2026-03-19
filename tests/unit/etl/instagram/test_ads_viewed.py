from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from context_use.providers.instagram.ads_viewed.pipe import InstagramAdsViewedPipe
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.instagram.conftest import INSTAGRAM_ADS_VIEWED_V1_JSON


class TestInstagramAdsViewedPipe(PipeTestKit):
    pipe_class = InstagramAdsViewedPipe
    expected_extract_count = 3
    expected_transform_count = 3
    fixture_data = INSTAGRAM_ADS_VIEWED_V1_JSON
    fixture_key = "archive/ads_information/ads_and_topics/ads_viewed.json"
    expected_fibre_kind = "ViewAd"
    snapshot_cases = [
        (
            [
                {
                    "timestamp": 1771848416,
                    "media": [],
                    "label_values": [
                        {
                            "label": "URL",
                            "value": "https://www.instagram.com/p/SYNTHETIC_SNAP_AD/",
                            "href": "https://www.instagram.com/p/SYNTHETIC_SNAP_AD/",
                        },
                        {
                            "dict": [
                                {
                                    "dict": [
                                        {
                                            "label": "URL",
                                            "value": "https://brand.example.com",
                                        },
                                        {
                                            "label": "Name",
                                            "value": "Snap Brand",
                                        },
                                        {
                                            "label": "Username",
                                            "value": "snap_brand",
                                        },
                                    ],
                                    "title": "",
                                }
                            ],
                            "title": "Owner",
                        },
                    ],
                    "fbid": "17841401108516601:99999:1771848416::DYIImpressionsData",
                }
            ],
            {
                "unique_key": "10151128ab56e188",
                "preview": "Viewed ad by snap_brand on instagram",
                "asat": datetime(2026, 2, 23, 12, 6, 56, tzinfo=UTC),
                "payload": {
                    "type": "View",
                    "published": "2026-02-23T12:06:56Z",
                    "object": {
                        "type": "Object",
                        "attributedTo": {
                            "type": "Profile",
                            "name": "snap_brand",
                            "url": "https://www.instagram.com/snap_brand",
                        },
                        "url": "https://www.instagram.com/p/SYNTHETIC_SNAP_AD/",
                        "fibreKind": "Ad",
                    },
                    "fibreKind": "ViewAd",
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

    def test_record_fields_with_owner(self, extracted_records) -> None:
        record = extracted_records[0]
        assert record.author == "example_brand"
        assert record.ad_url == "https://www.instagram.com/p/SYNTHETIC_AD_1/"
        assert record.timestamp == 1770753730
        assert record.source is not None

    def test_record_fields_without_owner(self, extracted_records) -> None:
        record = extracted_records[1]
        assert record.author is None
        assert record.ad_url == "https://www.instagram.com/p/SYNTHETIC_AD_2/"
        assert record.timestamp == 1770840130

    def test_payload_object_is_ad(self, transformed_rows) -> None:
        for row in transformed_rows:
            obj = row.payload["object"]
            assert obj["type"] == "Object"
            assert obj["fibreKind"] == "Ad"

    def test_payload_object_url(self, transformed_rows) -> None:
        assert (
            transformed_rows[0].payload["object"]["url"]
            == "https://www.instagram.com/p/SYNTHETIC_AD_1/"
        )

    def test_payload_has_attributed_to_from_owner(self, transformed_rows) -> None:
        attr = transformed_rows[0].payload["object"]["attributedTo"]
        assert attr["type"] == "Profile"
        assert attr["name"] == "example_brand"
        assert attr["url"] == "https://www.instagram.com/example_brand"

    def test_payload_no_attributed_to_when_no_owner(self, transformed_rows) -> None:
        assert "attributedTo" not in transformed_rows[1].payload["object"]

    def test_preview_includes_ad_and_author(self, transformed_rows) -> None:
        preview = transformed_rows[0].preview
        assert "Viewed ad" in preview
        assert "example_brand" in preview
        assert "instagram" in preview.lower()

    def test_preview_without_author(self, transformed_rows) -> None:
        preview = transformed_rows[1].preview
        assert preview == "Viewed ad on instagram"
