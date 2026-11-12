import httpx
import pytest

from pipeline.drive_sync import API, cached_version, fetch_version, inventory, valid_id


def test_api_recurses_and_follows_page_tokens():
    def handler(request):
        assert str(request.url).startswith(API)
        if request.url.params["q"].startswith("'child'"):
            return httpx.Response(
                200,
                json={
                    "files": [
                        {"id": "nested", "name": "x.xls", "mimeType": "application/vnd.ms-excel"}
                    ]
                },
            )
        if request.url.params.get("pageToken") == "second":
            return httpx.Response(
                200, json={"files": [{"id": "pdf", "name": "x.pdf", "mimeType": "application/pdf"}]}
            )
        return httpx.Response(
            200,
            json={
                "nextPageToken": "second",
                "files": [
                    {
                        "id": "child",
                        "name": "2026",
                        "mimeType": "application/vnd.google-apps.folder",
                    }
                ],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = inventory(client, "root", "test-key")
    assert result["listing_complete"]
    assert {i["path"] for i in result["files"]} == {"x.pdf", "2026/x.xls"}


def test_html_inventory_never_certifies_completeness():
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text="<html></html>"))
    ) as client:
        result = inventory(client, "root", None)
    assert not result["listing_complete"]
    assert result["warnings"]


def test_invalid_download_preserves_previous_version(tmp_path):
    previous = tmp_path / "file" / "previous.pdf"
    previous.parent.mkdir()
    previous.write_bytes(b"%PDF-old")
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, text="<html>login</html>"))
        ) as client,
        pytest.raises(ValueError, match="signature"),
    ):
        fetch_version(client, {"id": "file", "name": "x.pdf"}, tmp_path)
    assert previous.read_bytes() == b"%PDF-old"
    assert list(previous.parent.iterdir()) == [previous]


def test_changed_file_keeps_both_versions(tmp_path):
    for content in [b"%PDF-first", b"%PDF-second"]:
        with httpx.Client(
            transport=httpx.MockTransport(lambda _, data=content: httpx.Response(200, content=data))
        ) as client:
            fetch_version(client, {"id": "same-id", "name": "../../renamed.pdf"}, tmp_path)
    assert len(list((tmp_path / "same-id").glob("*.pdf"))) == 2


def test_rejects_path_traversal_id():
    with pytest.raises(ValueError):
        valid_id("../escape")


def test_cache_checks_both_remote_and_local_content(tmp_path):
    item = {"id": "file", "name": "a.pdf"}
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"%PDF-test"))
    ) as client:
        previous = {**fetch_version(client, item, tmp_path), "md5Checksum": "remote-md5"}
    assert cached_version({**item, "md5Checksum": "remote-md5"}, previous, tmp_path)
    assert cached_version({**item, "md5Checksum": "changed"}, previous, tmp_path) is None
    assert cached_version(item, previous, tmp_path) is None
    (tmp_path / previous["raw_path"]).write_bytes(b"corrupt")
    assert cached_version({**item, "md5Checksum": "remote-md5"}, previous, tmp_path) is None


def test_office_lock_file_is_not_a_dataset(tmp_path):
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: pytest.fail("must not download"))
    ) as client:
        assert (
            fetch_version(client, {"id": "lock", "name": "~$visitas.xlsx"}, tmp_path)["comparison"]
            == "temporary_office_file"
        )


def test_zero_byte_source_is_reported_separately(tmp_path):
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b""))
    ) as client:
        result = fetch_version(client, {"id": "empty", "name": "a.xlsx"}, tmp_path)
    assert result["comparison"] == "empty_file"
    assert result["size"] == 0
    assert (tmp_path / result["raw_path"]).exists()


def test_listing_preserves_downloaded_inventory(tmp_path, monkeypatch):
    from pipeline import drive_sync
    from pipeline.storage import load_json, write_json_atomic

    original = {"files": [{"id": "file", "sha256": "verified-hash"}]}
    target = tmp_path / "drive/root/inventory.json"
    write_json_atomic(target, original)
    monkeypatch.setattr(drive_sync, "inventory", lambda *_: {"folder_id": "root", "files": []})
    drive_sync.sync_drive("root", tmp_path)
    assert load_json(target, {}) == original
    assert (target.parent / "listing.json").exists()
