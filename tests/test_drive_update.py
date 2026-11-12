import hashlib
from datetime import datetime

import pytest

from pipeline import drive_update as update
from pipeline.models import AccessRecord
from pipeline.storage import load_json, write_json_atomic, write_partition


def record(source_id="old", record_id="existing", destination="OFICINA"):
    return AccessRecord(
        record_id=record_id,
        entity_id="person",
        canonical_name="PERSONA",
        document_type=None,
        document_number=None,
        location="olivos",
        record_type="person",
        source_id=source_id,
        source_url="url",
        source_path="source",
        source_page=1,
        entered_at=datetime(2026, 1, 2, 10),
        exited_at=datetime(2026, 1, 2, 11),
        destination=destination,
    )


def seed(tmp_path):
    data = tmp_path / "data"
    relative = "olivos/2025/12/old.parquet"  # Physical path intentionally differs from event year.
    write_partition(data / "partitions" / relative, [record()])
    write_json_atomic(
        data / "manifest.json",
        {
            "files": {
                "legacy": {
                    "source_id": "old",
                    "sha256": "old-hash",
                    "location": "olivos",
                    "status": "active",
                    "partition": relative,
                    "record_count": 1,
                }
            }
        },
    )
    return data


def observation(tmp_path, content=b"%PDF-fixture", fid="new"):
    raw = tmp_path / (fid + ".pdf")
    raw.write_bytes(content)
    return {
        "id": fid,
        "folder_id": "folder",
        "location": "olivos",
        "path": "2026/Enero.pdf",
        "name": "Enero.pdf",
        "url": "https://drive.google.com/file/d/" + fid + "/view",
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
        "local_path": str(raw),
    }


def test_candidate_reconciles_history_without_modifying_base(tmp_path, monkeypatch):
    data = seed(tmp_path)
    original = (data / "manifest.json").read_bytes()
    monkeypatch.setattr(
        update,
        "parse_source",
        lambda item, scratch, sid: ([record(sid, "other", "oficina")], "test", 2026, 1),
    )
    work = tmp_path / "candidate"
    result = update.prepare_update(data, work, [observation(tmp_path)])
    assert result["counts"]["matched_records"] == 1
    assert result["counts"]["new_records"] == 0
    assert (data / "manifest.json").read_bytes() == original
    import pyarrow.parquet as pq

    new = load_json(work / "data/manifest.json", {})["files"]["drive/folder/new"]
    assert (
        pq.read_table(work / "data/partitions" / new["partitions"][0]).to_pylist()[0]["record_id"]
        == "existing"
    )


def test_second_run_and_renaming_do_not_reparse(tmp_path, monkeypatch):
    data = seed(tmp_path)
    monkeypatch.setattr(
        update, "parse_source", lambda item, scratch, sid: ([record(sid)], "test", 2026, 1)
    )
    item = observation(tmp_path)
    update.prepare_update(data, tmp_path / "first", [item])
    monkeypatch.setattr(update, "parse_source", lambda *_: pytest.fail("unchanged file reparsed"))
    result = update.prepare_update(
        tmp_path / "first/data",
        tmp_path / "second",
        [{**item, "name": "Renamed.pdf", "path": "2026/Renamed.pdf"}],
    )
    assert result["counts"] == {"unchanged": 1}
    assert not result["data_changed"]


def test_invalid_replacement_preserves_active_source(tmp_path, monkeypatch):
    data = seed(tmp_path)
    write_json_atomic(
        data / update.STATE,
        {
            "files": {
                "folder/new": {"sha256": "old-hash", "status": "linked", "legacy_paths": ["legacy"]}
            }
        },
    )

    def fail(*_):
        raise ValueError("broken workbook")

    monkeypatch.setattr(update, "parse_source", fail)
    result = update.prepare_update(data, tmp_path / "candidate", [observation(tmp_path)])
    assert result["counts"]["quarantined"] == 1
    assert load_json(data / "manifest.json", {}) == load_json(
        tmp_path / "candidate/data/manifest.json", {}
    )
    assert (tmp_path / "candidate/data/partitions/olivos/2025/12/old.parquet").exists()


def test_valid_replacement_removes_obsolete_partition_in_candidate_only(tmp_path, monkeypatch):
    data = seed(tmp_path)
    write_json_atomic(
        data / update.STATE,
        {
            "files": {
                "folder/new": {"sha256": "old-hash", "status": "linked", "legacy_paths": ["legacy"]}
            }
        },
    )
    monkeypatch.setattr(
        update, "parse_source", lambda item, scratch, sid: ([record(sid)], "test", 2026, 1)
    )
    update.prepare_update(data, tmp_path / "candidate", [observation(tmp_path)])
    assert (data / "partitions/olivos/2025/12/old.parquet").exists()
    assert not (tmp_path / "candidate/data/partitions/olivos/2025/12/old.parquet").exists()


def test_cache_integrity_failure_aborts_before_candidate_is_published(tmp_path):
    data = seed(tmp_path)
    item = observation(tmp_path)
    item["sha256"] = "incorrect"
    with pytest.raises(ValueError, match="checksum"):
        update.prepare_update(data, tmp_path / "candidate", [item])
    assert not (tmp_path / "candidate/report.json").exists()
    assert (data / "partitions/olivos/2025/12/old.parquet").exists()


def test_disappeared_drive_file_does_not_delete_history(tmp_path):
    data = seed(tmp_path)
    update.prepare_update(data, tmp_path / "candidate", [])
    assert (tmp_path / "candidate/data/partitions/olivos/2025/12/old.parquet").exists()


def test_empty_file_is_quarantined_not_an_active_empty_partition(tmp_path):
    data = seed(tmp_path)
    item = {**observation(tmp_path, b""), "comparison": "empty_file"}
    result = update.prepare_update(data, tmp_path / "candidate", [item])
    assert result["counts"]["quarantined"] == 1
    assert (
        "drive/folder/new" not in load_json(tmp_path / "candidate/data/manifest.json", {})["files"]
    )


def test_refuses_to_overwrite_work_directory(tmp_path):
    data = seed(tmp_path)
    with pytest.raises(ValueError):
        update.prepare_update(data, data, [])


def test_2026_xlsx_is_dispatched_without_historical_year_filter(tmp_path, monkeypatch):
    item = observation(tmp_path)
    item.update(path="2026/01. Enero/Planilla 02 ENE 26.xlsx", name="Planilla 02 ENE 26.xlsx")

    def parse(local, path, sid, location, diagnostics):
        assert "2026" in str(local)
        assert location == "olivos"
        return [record(sid)]

    monkeypatch.setattr(update, "_parse_xlsx", parse)
    records, _, year, _ = update.parse_source(item, tmp_path / "scratch", "src")
    assert year == 2026
    assert records[0].source_url == item["url"]


def test_promotion_rolls_back_on_failure(tmp_path, monkeypatch):
    data = seed(tmp_path)
    original = (data / "manifest.json").read_bytes()
    monkeypatch.setattr(
        update, "parse_source", lambda item, scratch, sid: ([record(sid)], "test", 2026, 1)
    )
    work = tmp_path / "candidate"
    update.prepare_update(data, work, [observation(tmp_path)])
    replace = update.os.replace

    def fail_manifest(source, target):
        if source == work / "data/manifest.json":
            raise OSError("disk failure")
        return replace(source, target)

    monkeypatch.setattr(update.os, "replace", fail_manifest)
    with pytest.raises(OSError):
        update.promote_candidate(work / "data", data)
    assert (data / "manifest.json").read_bytes() == original
    assert (data / "partitions/olivos/2025/12/old.parquet").exists()
    assert not (data / update.STATE).exists()


def test_promotion_installs_validated_generation(tmp_path, monkeypatch):
    data = seed(tmp_path)
    monkeypatch.setattr(
        update, "parse_source", lambda item, scratch, sid: ([record(sid)], "test", 2026, 1)
    )
    work = tmp_path / "candidate"
    update.prepare_update(data, work, [observation(tmp_path)])
    update.promote_candidate(work / "data", data)
    assert "drive/folder/new" in load_json(data / "manifest.json", {})["files"]
    assert load_json(data / update.STATE, {})["files"]["folder/new"]["status"] == "imported"


def test_missing_base_partition_aborts(tmp_path):
    data = seed(tmp_path)
    (data / "partitions/olivos/2025/12/old.parquet").unlink()
    with pytest.raises(ValueError, match="partition"):
        update.prepare_update(data, tmp_path / "candidate", [])
    assert not (tmp_path / "candidate").exists()
