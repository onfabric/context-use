from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_use.providers.airbnb.wishlists import AirbnbWishlistsPipe
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.conftest import AIRBNB_WISHLISTS


class TestAirbnbWishlistsPipe(PipeTestKit):
    pipe_class = AirbnbWishlistsPipe
    expected_extract_count = 3
    expected_transform_count = 3

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/data/json/wishlists.json"
        storage.write(key, json.dumps(AIRBNB_WISHLISTS).encode())
        return storage, key

    def test_skips_bot_created_wishlists(self, pipe_fixture):
        """The AIRCOVER_REBOOK wishlist should be filtered out."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        wishlist_names = {r.wishlist_name for r in records}
        assert "Similar stays for you" not in wishlist_names

    def test_only_user_wishlists(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        wishlist_names = {r.wishlist_name for r in records}
        assert "Barcelona" in wishlist_names
        assert "Tokyo" in wishlist_names

    def test_listing_urls(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            obj = row.payload.get("object", {})
            assert obj.get("url", "").startswith("https://www.airbnb.com/rooms/")
