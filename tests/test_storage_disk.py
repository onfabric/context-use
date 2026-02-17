"""Unit tests for DiskStorage."""

from pathlib import Path

from contextuse.storage.disk import DiskStorage


class TestDiskStorage:
    def test_write_read(self, tmp_path: Path):
        s = DiskStorage(str(tmp_path / "store"))
        s.write("a/b.txt", b"hello")
        assert s.read("a/b.txt") == b"hello"

    def test_exists(self, tmp_path: Path):
        s = DiskStorage(str(tmp_path / "store"))
        assert not s.exists("missing.txt")
        s.write("found.txt", b"here")
        assert s.exists("found.txt")

    def test_list_keys(self, tmp_path: Path):
        s = DiskStorage(str(tmp_path / "store"))
        s.write("p/one.txt", b"1")
        s.write("p/two.txt", b"2")
        s.write("q/three.txt", b"3")
        keys = s.list_keys("p")
        assert sorted(keys) == ["p/one.txt", "p/two.txt"]

    def test_list_keys_empty(self, tmp_path: Path):
        s = DiskStorage(str(tmp_path / "store"))
        assert s.list_keys("nope") == []

    def test_delete(self, tmp_path: Path):
        s = DiskStorage(str(tmp_path / "store"))
        s.write("del.txt", b"bye")
        assert s.exists("del.txt")
        s.delete("del.txt")
        assert not s.exists("del.txt")

    def test_open_stream(self, tmp_path: Path):
        s = DiskStorage(str(tmp_path / "store"))
        s.write("stream.txt", b"streaming content")
        with s.open_stream("stream.txt") as f:
            assert f.read() == b"streaming content"

