from __future__ import annotations


class PostObjectMixin:
    """Asserts every row's payload object is a Post (type=Note, fibreKind=Post)."""

    def test_payload_object_is_post(self, transformed_rows) -> None:
        for row in transformed_rows:
            obj = row.payload["object"]
            assert obj["type"] == "Note"
            assert obj["fibreKind"] == "Post"


class VideoObjectMixin:
    """Asserts every row's payload object is a Video (type=Video)."""

    def test_payload_object_is_video(self, transformed_rows) -> None:
        for row in transformed_rows:
            assert row.payload["object"]["type"] == "Video"


class AttributedToProfileMixin:
    """Asserts every row's payload object carries a Profile attribution."""

    def test_payload_object_has_attributed_to_profile(self, transformed_rows) -> None:
        for row in transformed_rows:
            attr = row.payload["object"].get("attributedTo")
            assert attr is not None, "attributedTo must be present"
            assert attr["type"] == "Profile"
            assert attr["name"], "attributedTo name must be non-empty"
