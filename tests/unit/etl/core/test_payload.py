import datetime

import pytest
from pydantic import ValidationError

from context_use.activitystreams.objects import Event
from context_use.etl.payload.core import make_thread_payload
from context_use.etl.payload.models import (
    Application,
    FibreAddObjectToCollection,
    FibreCollection,
    FibreCollectionFavourites,
    FibreComment,
    FibreCreateObject,
    FibreDislike,
    FibreFollowedBy,
    FibreFollowing,
    FibreImage,
    FibreLike,
    FibrePost,
    FibreReceiveMessage,
    FibreSearch,
    FibreSendMessage,
    FibreTextMessage,
    FibreVideo,
    FibreViewObject,
    Image,
    Note,
    Page,
    Person,
    Profile,
    Video,
)


class TestFibreModels:
    def test_text_message_preview(self):
        msg = FibreTextMessage(content="Hello World")  # pyright: ignore[reportCallIssue]
        assert msg.get_preview() == 'message "Hello World"'

    def test_text_message_truncation(self):
        long = "x" * 200
        msg = FibreTextMessage(content=long)  # pyright: ignore[reportCallIssue]
        preview = msg.get_preview()
        assert preview is not None
        assert "..." in preview
        assert len(preview) < 120

    def test_send_message_roundtrip(self):
        msg = FibreTextMessage(content="hi")  # pyright: ignore[reportCallIssue]
        target = Application(name="assistant")  # pyright: ignore[reportCallIssue]
        send = FibreSendMessage(object=msg, target=target)  # pyright: ignore[reportCallIssue]

        d = send.to_dict()
        assert d["fibreKind"] == "SendMessage"
        assert d["object"]["content"] == "hi"
        assert d["target"]["name"] == "assistant"

        # Unique key should be deterministic
        assert send.unique_key() == send.unique_key()

    def test_receive_message_preview(self):
        msg = FibreTextMessage(content="world")  # pyright: ignore[reportCallIssue]
        actor = Application(name="bot")  # pyright: ignore[reportCallIssue]
        recv = FibreReceiveMessage(object=msg, actor=actor)  # pyright: ignore[reportCallIssue]

        preview = recv.get_preview("TestProvider")
        assert preview is not None
        assert "Received" in preview
        assert "bot" in preview

    def test_create_object_image(self):
        img = Image(url="http://example.com/pic.jpg")  # pyright: ignore[reportCallIssue]
        create = FibreCreateObject(object=img)  # pyright: ignore[reportCallIssue]
        assert create.get_preview("Instagram") == "Posted image on Instagram"

    def test_create_object_video(self):
        vid = Video(url="http://example.com/clip.mp4")  # pyright: ignore[reportCallIssue]
        create = FibreCreateObject(object=vid)  # pyright: ignore[reportCallIssue]
        assert create.get_preview() == "Posted video"


class TestFibreGetContent:
    def test_image_content(self):
        img = FibreImage(url="http://example.com/pic.jpg", content="sunset")  # pyright: ignore[reportCallIssue]
        assert img.get_content() == "sunset"

    def test_image_no_content(self):
        img = FibreImage(url="http://example.com/pic.jpg")  # pyright: ignore[reportCallIssue]
        assert img.get_content() is None

    def test_video_content(self):
        vid = FibreVideo(url="http://example.com/vid.mp4", content="cooking tutorial")  # pyright: ignore[reportCallIssue]
        assert vid.get_content() == "cooking tutorial"

    def test_video_no_content(self):
        vid = FibreVideo(url="http://example.com/vid.mp4")  # pyright: ignore[reportCallIssue]
        assert vid.get_content() is None

    def test_text_message_content(self):
        msg = FibreTextMessage(content="Hello World")  # pyright: ignore[reportCallIssue]
        assert msg.get_content() == "Hello World"

    def test_text_message_no_content(self):
        msg = FibreTextMessage()  # pyright: ignore[reportCallIssue]
        assert msg.get_content() is None

    def test_create_object_with_caption(self):
        img = Image(url="http://example.com/pic.jpg", content="latte art")  # pyright: ignore[reportCallIssue]
        create = FibreCreateObject(object=img)  # pyright: ignore[reportCallIssue]
        assert create.get_content() == "latte art"

    def test_create_object_no_caption(self):
        img = Image(url="http://example.com/pic.jpg")  # pyright: ignore[reportCallIssue]
        create = FibreCreateObject(object=img)  # pyright: ignore[reportCallIssue]
        assert create.get_content() is None

    def test_send_message_content(self):
        msg = FibreTextMessage(content="hi")  # pyright: ignore[reportCallIssue]
        target = Application(name="assistant")  # pyright: ignore[reportCallIssue]
        send = FibreSendMessage(object=msg, target=target)  # pyright: ignore[reportCallIssue]
        assert send.get_content() == "hi"

    def test_receive_message_content(self):
        msg = FibreTextMessage(content="world")  # pyright: ignore[reportCallIssue]
        actor = Application(name="bot")  # pyright: ignore[reportCallIssue]
        recv = FibreReceiveMessage(object=msg, actor=actor)  # pyright: ignore[reportCallIssue]
        assert recv.get_content() == "world"

    def test_view_object_content(self):
        page = Page(name="Python asyncio docs", url="http://example.com")  # pyright: ignore[reportCallIssue]
        view = FibreViewObject(object=page)  # pyright: ignore[reportCallIssue]
        assert view.get_content() == "Python asyncio docs"

    def test_view_object_with_author(self):
        post = FibrePost(  # pyright: ignore[reportCallIssue]
            attributedTo=Profile(name="alice"),  # pyright: ignore[reportCallIssue]
        )
        view = FibreViewObject(object=post)  # pyright: ignore[reportCallIssue]
        assert view.get_content() == "by alice"

    def test_like_post_content(self):
        post = FibrePost(  # pyright: ignore[reportCallIssue]
            attributedTo=Profile(name="alice"),  # pyright: ignore[reportCallIssue]
        )
        like = FibreLike(object=post)  # pyright: ignore[reportCallIssue]
        assert like.get_content() == "alice"

    def test_like_video_content(self):
        vid = Video(name="cool clip")  # pyright: ignore[reportCallIssue]
        like = FibreLike(object=vid)  # pyright: ignore[reportCallIssue]
        assert like.get_content() == "cool clip"

    def test_comment_content(self):
        note = Note(content="amazing!")  # pyright: ignore[reportCallIssue]
        comment = FibreComment(object=note)  # pyright: ignore[reportCallIssue]
        assert comment.get_content() == "amazing!"

    def test_search_profile_content(self):
        profile = Profile(name="alice")  # pyright: ignore[reportCallIssue]
        search = FibreSearch(object=profile)  # pyright: ignore[reportCallIssue]
        assert search.get_content() == "alice"

    def test_search_page_content(self):
        page = Page(name="python tutorial")  # pyright: ignore[reportCallIssue]
        search = FibreSearch(object=page)  # pyright: ignore[reportCallIssue]
        assert search.get_content() == "python tutorial"

    def test_add_to_collection_post_content(self):
        post = FibrePost(  # pyright: ignore[reportCallIssue]
            attributedTo=Profile(name="alice"),  # pyright: ignore[reportCallIssue]
        )
        fav = FibreCollectionFavourites()  # pyright: ignore[reportCallIssue]
        add = FibreAddObjectToCollection(object=post, target=fav)  # pyright: ignore[reportCallIssue]
        assert add.get_content() == "alice"

    def test_followed_by_content(self):
        fb = FibreFollowedBy(  # pyright: ignore[reportCallIssue]
            actor=Person(name="alice"),  # pyright: ignore[reportCallIssue]
        )
        assert fb.get_content() == "alice"

    def test_following_content(self):
        fg = FibreFollowing(  # pyright: ignore[reportCallIssue]
            object=Profile(name="bob"),  # pyright: ignore[reportCallIssue]
        )
        assert fg.get_content() == "bob"


class TestMakeThreadPayload:
    def test_send_message(self):
        data = {
            "type": "Create",
            "fibre_kind": "SendMessage",
            "object": {
                "type": "Note",
                "fibre_kind": "TextMessage",
                "content": "hi",
            },
            "target": {"type": "Application", "name": "bot"},
        }
        payload = make_thread_payload(data)
        assert isinstance(payload, FibreSendMessage)

    def test_create_object(self):
        data = {
            "type": "Create",
            "fibre_kind": "Create",
            "object": {"type": "Video", "url": "http://example.com/v.mp4"},
        }
        payload = make_thread_payload(data)
        assert isinstance(payload, FibreCreateObject)


class TestFibreAsat:
    def test_get_asat_with_published(self):
        dt = datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC)
        msg = FibreTextMessage(content="test", published=dt)  # pyright: ignore[reportCallIssue]
        assert msg.get_asat() == dt

    def test_get_asat_without_published(self):
        msg = FibreTextMessage(content="test")  # pyright: ignore[reportCallIssue]
        assert msg.get_asat() is None


class TestFibreLike:
    def test_reaction_rejects_empty_content(self):
        post = FibrePost()  # pyright: ignore[reportCallIssue]
        with pytest.raises(ValidationError, match="non-empty"):
            FibreLike(object=post, content="")  # pyright: ignore[reportCallIssue]

    def test_preview_post(self):
        post = FibrePost(  # pyright: ignore[reportCallIssue]
            attributedTo=Profile(name="alice"),  # pyright: ignore[reportCallIssue]
        )
        like = FibreLike(object=post)  # pyright: ignore[reportCallIssue]
        assert like.get_preview("Instagram") == "Liked post by alice on Instagram"

    def test_preview_video(self):
        vid = Video()  # pyright: ignore[reportCallIssue]
        like = FibreLike(object=vid)  # pyright: ignore[reportCallIssue]
        assert like.get_preview() == "Liked video"


class TestFibreDislike:
    def test_reaction_rejects_empty_content(self):
        post = FibrePost()  # pyright: ignore[reportCallIssue]
        with pytest.raises(ValidationError, match="non-empty"):
            FibreDislike(object=post, content="")  # pyright: ignore[reportCallIssue]

    def test_preview_post(self):
        post = FibrePost(  # pyright: ignore[reportCallIssue]
            attributedTo=Profile(name="alice"),  # pyright: ignore[reportCallIssue]
        )
        dislike = FibreDislike(object=post)  # pyright: ignore[reportCallIssue]
        assert dislike.get_preview("YouTube") == "Disliked post by alice on YouTube"

    def test_preview_video(self):
        vid = Video()  # pyright: ignore[reportCallIssue]
        dislike = FibreDislike(object=vid)  # pyright: ignore[reportCallIssue]
        assert dislike.get_preview() == "Disliked video"

    def test_type_is_dislike(self):
        vid = Video()  # pyright: ignore[reportCallIssue]
        dislike = FibreDislike(object=vid)  # pyright: ignore[reportCallIssue]
        assert dislike.type == "Dislike"
        assert dislike.fibreKind == "Reaction"


class TestFibreComment:
    def test_preview_with_reply_to(self):
        note = Note(content="amazing!")  # pyright: ignore[reportCallIssue]
        post = FibrePost(  # pyright: ignore[reportCallIssue]
            attributedTo=Profile(name="alice"),  # pyright: ignore[reportCallIssue]
        )
        comment = FibreComment(object=note, inReplyTo=post)  # pyright: ignore[reportCallIssue]
        preview = comment.get_preview("Instagram")
        assert preview is not None
        assert "Commented" in preview
        assert "alice" in preview
        assert "Instagram" in preview

    def test_preview_without_reply_to(self):
        note = Note(content="standalone comment")  # pyright: ignore[reportCallIssue]
        comment = FibreComment(object=note)  # pyright: ignore[reportCallIssue]
        preview = comment.get_preview()
        assert preview is not None
        assert "Commented" in preview


class TestFibreSearch:
    def test_preview_profile(self):
        profile = Profile(name="alice")  # pyright: ignore[reportCallIssue]
        search = FibreSearch(object=profile)  # pyright: ignore[reportCallIssue]
        assert search.get_preview() == 'Searched for profile "alice"'

    def test_preview_post(self):
        post = FibrePost()  # pyright: ignore[reportCallIssue]
        search = FibreSearch(object=post)  # pyright: ignore[reportCallIssue]
        assert search.get_preview() == "Searched for post"


class TestFibreAddObjectToCollection:
    def test_preview_saved_to_favourites(self):
        post = FibrePost(  # pyright: ignore[reportCallIssue]
            attributedTo=Profile(name="alice"),  # pyright: ignore[reportCallIssue]
        )
        fav = FibreCollectionFavourites()  # pyright: ignore[reportCallIssue]
        add = FibreAddObjectToCollection(object=post, target=fav)  # pyright: ignore[reportCallIssue]
        assert add.get_preview("Instagram") == "Saved post by alice on Instagram"

    def test_preview_saved_to_named_collection(self):
        post = FibrePost()  # pyright: ignore[reportCallIssue]
        coll = FibreCollection(name="Travel")  # pyright: ignore[reportCallIssue]
        add = FibreAddObjectToCollection(object=post, target=coll)  # pyright: ignore[reportCallIssue]
        assert add.get_preview() == 'Saved to "Travel" post'


class TestFibreFollowedBy:
    def test_is_inbound(self):
        fb = FibreFollowedBy(  # pyright: ignore[reportCallIssue]
            actor=Person(name="alice"),  # pyright: ignore[reportCallIssue]
        )
        assert fb.is_inbound() is True

    def test_preview(self):
        fb = FibreFollowedBy(  # pyright: ignore[reportCallIssue]
            actor=Person(name="alice"),  # pyright: ignore[reportCallIssue]
        )
        assert fb.get_preview("Instagram") == "Followed by alice on Instagram"

    def test_rejects_both_actor_and_object(self):
        with pytest.raises(ValidationError):
            FibreFollowedBy(  # pyright: ignore[reportCallIssue]
                actor=Person(name="alice"),  # pyright: ignore[reportCallIssue]
                object=Profile(name="bob"),  # pyright: ignore[reportCallIssue]
            )

    def test_rejects_missing_actor(self):
        with pytest.raises(ValidationError):
            FibreFollowedBy()  # pyright: ignore[reportCallIssue]


class TestFibreFollowing:
    def test_is_not_inbound(self):
        fg = FibreFollowing(  # pyright: ignore[reportCallIssue]
            object=Profile(name="bob"),  # pyright: ignore[reportCallIssue]
        )
        assert fg.is_inbound() is False

    def test_preview(self):
        fg = FibreFollowing(  # pyright: ignore[reportCallIssue]
            object=Profile(name="bob"),  # pyright: ignore[reportCallIssue]
        )
        assert fg.get_preview("Instagram") == "Following bob on Instagram"

    def test_rejects_both_actor_and_object(self):
        with pytest.raises(ValidationError):
            FibreFollowing(  # pyright: ignore[reportCallIssue]
                actor=Person(name="alice"),  # pyright: ignore[reportCallIssue]
                object=Profile(name="bob"),  # pyright: ignore[reportCallIssue]
            )


class TestFibreViewObjectWidened:
    def test_view_post_preview(self):
        post = FibrePost(  # pyright: ignore[reportCallIssue]
            attributedTo=Profile(name="alice"),  # pyright: ignore[reportCallIssue]
        )
        view = FibreViewObject(object=post)  # pyright: ignore[reportCallIssue]
        preview = view.get_preview("Instagram")
        assert preview is not None
        assert "Viewed post" in preview
        assert "alice" in preview
        assert "Instagram" in preview

    def test_view_video_still_works(self):
        vid = Video(name="clip")  # pyright: ignore[reportCallIssue]
        view = FibreViewObject(object=vid)  # pyright: ignore[reportCallIssue]
        preview = view.get_preview()
        assert preview is not None
        assert "Viewed video" in preview

    def test_view_page_still_works(self):
        page = Page(name="example", url="http://example.com")  # pyright: ignore[reportCallIssue]
        view = FibreViewObject(object=page)  # pyright: ignore[reportCallIssue]
        preview = view.get_preview()
        assert preview is not None
        assert "Viewed page" in preview

    def test_view_event_preview(self):
        event = Event(name="3-night stay from 2024-01-15")  # pyright: ignore[reportCallIssue]
        view = FibreViewObject(object=event)  # pyright: ignore[reportCallIssue]
        preview = view.get_preview("Airbnb")
        assert preview is not None
        assert "Viewed event" in preview
        assert "3-night stay" in preview
        assert "Airbnb" in preview

    def test_view_event_roundtrip(self):
        event = Event(  # pyright: ignore[reportCallIssue]
            name="3-night stay from 2024-01-15",
            url="https://www.airbnb.com/rooms/123",
        )
        view = FibreViewObject(object=event)  # pyright: ignore[reportCallIssue]
        d = view.to_dict()
        result = make_thread_payload(d)
        assert isinstance(result, FibreViewObject)
        assert result.unique_key() == view.unique_key()


class TestFibreReceiveMessageWithPerson:
    def test_person_actor_preview(self):
        msg = FibreTextMessage(content="hello")  # pyright: ignore[reportCallIssue]
        actor = Person(name="host")  # pyright: ignore[reportCallIssue]
        recv = FibreReceiveMessage(object=msg, actor=actor)  # pyright: ignore[reportCallIssue]
        preview = recv.get_preview("Airbnb")
        assert preview is not None
        assert "Received" in preview
        assert "host" in preview

    def test_person_actor_participant_label(self):
        msg = FibreTextMessage(content="hello")  # pyright: ignore[reportCallIssue]
        actor = Person(name="host")  # pyright: ignore[reportCallIssue]
        recv = FibreReceiveMessage(object=msg, actor=actor)  # pyright: ignore[reportCallIssue]
        assert recv.get_participant_label() == "host"

    def test_person_actor_roundtrip(self):
        msg = FibreTextMessage(content="hello")  # pyright: ignore[reportCallIssue]
        actor = Person(name="host")  # pyright: ignore[reportCallIssue]
        recv = FibreReceiveMessage(object=msg, actor=actor)  # pyright: ignore[reportCallIssue]
        d = recv.to_dict()
        result = make_thread_payload(d)
        assert isinstance(result, FibreReceiveMessage)
        assert result.unique_key() == recv.unique_key()


class TestMakeThreadPayloadRoundTrip:
    """Construct → to_dict → make_thread_payload → same type + same unique_key."""

    def _roundtrip(self, fibre):
        d = fibre.to_dict()
        return make_thread_payload(d)

    def test_like_roundtrip(self):
        post = FibrePost(  # pyright: ignore[reportCallIssue]
            attributedTo=Profile(name="alice"),  # pyright: ignore[reportCallIssue]
        )
        like = FibreLike(object=post)  # pyright: ignore[reportCallIssue]
        result = self._roundtrip(like)
        assert isinstance(result, FibreLike)
        assert result.unique_key() == like.unique_key()

    def test_dislike_roundtrip(self):
        vid = Video(name="bad video")  # pyright: ignore[reportCallIssue]
        dislike = FibreDislike(object=vid)  # pyright: ignore[reportCallIssue]
        result = self._roundtrip(dislike)
        assert isinstance(result, FibreDislike)
        assert result.unique_key() == dislike.unique_key()

    def test_comment_roundtrip(self):
        note = Note(content="great!")  # pyright: ignore[reportCallIssue]
        post = FibrePost(  # pyright: ignore[reportCallIssue]
            attributedTo=Profile(name="bob"),  # pyright: ignore[reportCallIssue]
        )
        comment = FibreComment(object=note, inReplyTo=post)  # pyright: ignore[reportCallIssue]
        result = self._roundtrip(comment)
        assert isinstance(result, FibreComment)
        assert result.unique_key() == comment.unique_key()

    def test_search_roundtrip(self):
        search = FibreSearch(  # pyright: ignore[reportCallIssue]
            object=Profile(name="alice"),  # pyright: ignore[reportCallIssue]
        )
        result = self._roundtrip(search)
        assert isinstance(result, FibreSearch)
        assert result.unique_key() == search.unique_key()

    def test_add_to_favourites_roundtrip(self):
        add = FibreAddObjectToCollection(  # pyright: ignore[reportCallIssue]
            object=FibrePost(  # pyright: ignore[reportCallIssue]
                url="http://example.com/post/1",
            ),
            target=FibreCollectionFavourites(),  # pyright: ignore[reportCallIssue]
        )
        result = self._roundtrip(add)
        assert isinstance(result, FibreAddObjectToCollection)
        assert isinstance(result.target, FibreCollectionFavourites)
        assert result.unique_key() == add.unique_key()

    def test_add_to_named_collection_roundtrip(self):
        add = FibreAddObjectToCollection(  # pyright: ignore[reportCallIssue]
            object=FibrePost(  # pyright: ignore[reportCallIssue]
                url="http://example.com/post/2",
                attributedTo=Profile(name="alice"),  # pyright: ignore[reportCallIssue]
            ),
            target=FibreCollection(name="Travel"),  # pyright: ignore[reportCallIssue]
        )
        result = self._roundtrip(add)
        assert isinstance(result, FibreAddObjectToCollection)
        assert isinstance(result.target, FibreCollection)
        assert not isinstance(result.target, FibreCollectionFavourites)
        assert result.target.name == "Travel"
        assert result.unique_key() == add.unique_key()

    def test_followed_by_roundtrip(self):
        fb = FibreFollowedBy(  # pyright: ignore[reportCallIssue]
            actor=Person(name="alice"),  # pyright: ignore[reportCallIssue]
        )
        result = self._roundtrip(fb)
        assert isinstance(result, FibreFollowedBy)
        assert result.unique_key() == fb.unique_key()

    def test_following_roundtrip(self):
        fg = FibreFollowing(  # pyright: ignore[reportCallIssue]
            object=Profile(name="bob"),  # pyright: ignore[reportCallIssue]
        )
        result = self._roundtrip(fg)
        assert isinstance(result, FibreFollowing)
        assert result.unique_key() == fg.unique_key()

    def test_view_post_roundtrip(self):
        view = FibreViewObject(  # pyright: ignore[reportCallIssue]
            object=FibrePost(  # pyright: ignore[reportCallIssue]
                attributedTo=Profile(name="alice"),  # pyright: ignore[reportCallIssue]
            ),
        )
        result = self._roundtrip(view)
        assert isinstance(result, FibreViewObject)
        assert result.unique_key() == view.unique_key()
