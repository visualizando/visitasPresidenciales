from pipeline.models import RemoteFile
from pipeline.update import _needs_download


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
