from __future__ import annotations

import json

from context_use.models.etl_task import EtlTask, EtlTaskStatus
from context_use.providers.google.search.pipe import GoogleSearchPipe
from context_use.providers.google.youtube.pipe import GoogleYoutubePipe
from context_use.storage.disk import DiskStorage


def _make_task(pipe_class: type, key: str) -> EtlTask:
    return EtlTask(
        archive_id="a1",
        provider=pipe_class.provider,
        interaction_type=pipe_class.interaction_type,
        source_uris=[key],
        status=EtlTaskStatus.CREATED.value,
    )


class TestFileSchemaGateSearch:
    """Verify that structurally invalid files are skipped entirely."""

    def test_missing_required_field_skips_file(self, tmp_path: object) -> None:
        storage = DiskStorage(str(tmp_path))
        key = "archive/Portability/My Activity/Search/MyActivity.json"
        bad_data = [{"title": "Searched for python"}]
        storage.write(key, json.dumps(bad_data).encode())

        pipe = GoogleSearchPipe()
        task = _make_task(GoogleSearchPipe, key)
        rows = list(pipe.run(task, storage))
        assert rows == []
        assert pipe.error_count >= 1

    def test_valid_file_passes_gate(self, tmp_path: object) -> None:
        storage = DiskStorage(str(tmp_path))
        key = "archive/Portability/My Activity/Search/MyActivity.json"
        data = [
            {
                "header": "Search",
                "title": "Searched for python",
                "titleUrl": "https://www.google.com/search?q=python",
                "time": "2025-06-15T10:30:00.000Z",
                "products": ["Search"],
            }
        ]
        storage.write(key, json.dumps(data).encode())

        pipe = GoogleSearchPipe()
        task = _make_task(GoogleSearchPipe, key)
        rows = list(pipe.run(task, storage))
        assert len(rows) == 1
        assert pipe.error_count == 0

    def test_completely_wrong_structure_skips_file(self, tmp_path: object) -> None:
        storage = DiskStorage(str(tmp_path))
        key = "archive/Portability/My Activity/Search/MyActivity.json"
        bad_data = [{"totally": "different", "structure": True}]
        storage.write(key, json.dumps(bad_data).encode())

        pipe = GoogleSearchPipe()
        task = _make_task(GoogleSearchPipe, key)
        rows = list(pipe.run(task, storage))
        assert rows == []
        assert pipe.error_count >= 1


class TestFileSchemaGateYoutube:
    """Verify YouTube file schema gate with typed subtitles."""

    def test_malformed_subtitles_skips_file(self, tmp_path: object) -> None:
        storage = DiskStorage(str(tmp_path))
        key = "archive/Portability/My Activity/YouTube/MyActivity.json"
        bad_data = [
            {
                "header": "YouTube",
                "title": "Watched something",
                "titleUrl": "https://www.youtube.com/watch?v=abc",
                "subtitles": [{"wrong_key": "no name field"}],
                "time": "2025-06-15T10:30:00.000Z",
                "products": ["YouTube"],
            }
        ]
        storage.write(key, json.dumps(bad_data).encode())

        pipe = GoogleYoutubePipe()
        task = _make_task(GoogleYoutubePipe, key)
        rows = list(pipe.run(task, storage))
        assert rows == []
        assert pipe.error_count >= 1

    def test_valid_youtube_data_passes_gate(self, tmp_path: object) -> None:
        storage = DiskStorage(str(tmp_path))
        key = "archive/Portability/My Activity/YouTube/MyActivity.json"
        data = [
            {
                "header": "YouTube",
                "title": "Watched Cool Video",
                "titleUrl": "https://www.youtube.com/watch?v=abc",
                "subtitles": [
                    {
                        "name": "Cool Channel",
                        "url": "https://www.youtube.com/channel/UC000001",
                    }
                ],
                "time": "2025-06-15T10:30:00.000Z",
                "products": ["YouTube"],
            }
        ]
        storage.write(key, json.dumps(data).encode())

        pipe = GoogleYoutubePipe()
        task = _make_task(GoogleYoutubePipe, key)
        rows = list(pipe.run(task, storage))
        assert len(rows) == 1
        assert pipe.error_count == 0

    def test_subtitles_without_url_passes(self, tmp_path: object) -> None:
        storage = DiskStorage(str(tmp_path))
        key = "archive/Portability/My Activity/YouTube/MyActivity.json"
        data = [
            {
                "header": "YouTube",
                "title": "Subscribed to Cool Channel",
                "titleUrl": "https://www.youtube.com/channel/UC000001",
                "time": "2025-06-15T10:36:00.000Z",
                "products": ["YouTube"],
            }
        ]
        storage.write(key, json.dumps(data).encode())

        pipe = GoogleYoutubePipe()
        task = _make_task(GoogleYoutubePipe, key)
        rows = list(pipe.run(task, storage))
        assert len(rows) == 1
        assert pipe.error_count == 0
