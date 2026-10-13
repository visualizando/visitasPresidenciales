from pipeline.models import RemoteFile
from pipeline.update import _entry_belongs_to_source, _needs_download, _source_url_prefix


def test_does_not_retry_unchanged_quarantined_file() -> None:
    remote = RemoteFile(
        "file:///empty.pdf",
        "olivos/2021/09/empty.pdf",
        "olivos",
        2021,
        9,
        size=0,
        last_modified="123",
    )
    old = {
        "status": "quarantined",
        "size": 0,
        "last_modified": "123",
        "sha256": "known",
    }

    assert not _needs_download(remote, old)
    remote.last_modified = "124"
    assert _needs_download(remote, old)


def test_source_prefix_matches_local_directory(tmp_path) -> None:
    assert _source_url_prefix(str(tmp_path)) == tmp_path.resolve().as_uri()


def test_source_prefix_matches_remote_base() -> None:
    assert _source_url_prefix("https://example.org/raw/") == "https://example.org/raw"


def test_entry_belongs_to_source_uses_url_prefix() -> None:
    prefix = "https://example.org/raw"

    assert _entry_belongs_to_source({"url": "https://example.org/raw/a/b.pdf"}, prefix)
    assert not _entry_belongs_to_source({"url": "https://example.org/rawish/a.pdf"}, prefix)
    assert not _entry_belongs_to_source({"url": "file:///tmp/other/a.pdf"}, prefix)
    assert not _entry_belongs_to_source({"url": None}, prefix)
    assert not _entry_belongs_to_source({"url": "https://example.org/raw/a.pdf"}, None)
