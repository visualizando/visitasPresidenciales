import json
from datetime import datetime

from pipeline.build_web import build_web_data
from pipeline.models import AccessRecord
from pipeline.storage import write_partition


def test_builds_empty_web_dataset(tmp_path) -> None:
    output = tmp_path / "public" / "data"
    stats = build_web_data(tmp_path / "data", output)
    assert stats == {"records": 0, "people": 0, "exports": 0}
    assert '"record_count":0' in (output / "meta.json").read_text(encoding="utf-8")


def test_builds_search_events_analytics_and_csv(tmp_path) -> None:
    data = tmp_path / "data"
    output = tmp_path / "public" / "data"
    record = AccessRecord(
        record_id="rec_1",
        entity_id="per_1",
        canonical_name="PEREZ ANA",
        document_type="DNI",
        document_number="30123456",
        location="olivos",
        record_type="person",
        source_id="src_1",
        source_url="https://example.org/olivos/2023/01/01.pdf",
        source_path="olivos/2023/01/01.pdf",
        source_page=1,
        entered_at=datetime(2023, 1, 1, 9, 0),
        exited_at=datetime(2023, 1, 1, 10, 0),
        purpose="REUNIÓN",
        quality="high",
        raw_text="fila",
    )
    write_partition(data / "partitions" / "olivos" / "2023" / "01" / "src.parquet", [record])
    stats = build_web_data(data, output)
    assert stats["records"] == 1
    assert stats["people"] == 1
    assert (output / "search" / "name" / "p.json").exists()
    assert list((output / "events").glob("*.json"))
    assert (output / "exports" / "2023.csv.gz").exists()
    exports = json.loads((output / "exports" / "index.json").read_text(encoding="utf-8"))
    assert exports == [{"year": 2023, "records": 1, "path": "2023.csv.gz"}]


def test_builds_deduplicated_cooccurrence_episodes(tmp_path) -> None:
    data = tmp_path / "data"
    output = tmp_path / "public" / "data"
    common = {
        "document_type": None,
        "document_number": None,
        "location": "casa-rosada",
        "record_type": "visitor",
        "source_id": "src_1",
        "source_url": "https://example.org/rosada/2023/01.pdf",
        "source_path": "rosada/2023/01.pdf",
        "source_page": 1,
        "quality": "high",
        "raw_text": "fila",
    }
    records = [
        AccessRecord(
            record_id="rec_1",
            entity_id="per_1",
            canonical_name="PEREZ ANA",
            entered_at=datetime(2023, 1, 2, 9, 0),
            exited_at=datetime(2023, 1, 2, 10, 0),
            destination="SECRETARIA GENERAL · BALCARCE 24",
            **common,
        ),
        AccessRecord(
            record_id="rec_2",
            entity_id="per_2",
            canonical_name="GOMEZ LUIS",
            entered_at=datetime(2023, 1, 2, 9, 30),
            exited_at=datetime(2023, 1, 2, 10, 30),
            destination="SECRETARIA GENERAL - BALCARCE 24",
            **common,
        ),
        AccessRecord(
            record_id="rec_3",
            entity_id="per_3",
            canonical_name="LOPEZ MARIA",
            entered_at=datetime(2023, 1, 2, 9, 30),
            exited_at=datetime(2023, 1, 2, 10, 30),
            destination="RIVADAVIA 250",
            **common,
        ),
    ]
    write_partition(
        data / "partitions" / "casa-rosada" / "2023" / "01" / "src.parquet",
        records,
    )

    build_web_data(data, output)

    shards = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (output / "cooccurrences").glob("*.json")
        if path.name != "meta.json"
    ]
    owner = next(shard["per_1"] for shard in shards if "per_1" in shard)
    assert owner["p"]["per_2"][0] == "GOMEZ LUIS"
    assert "per_3" not in owner["p"]
    assert owner["e"] == [["per_2", "2023-01-02", 0, 0, 30, 1, "09:30", "10:00"]]
    meta = json.loads((output / "cooccurrences" / "meta.json").read_text(encoding="utf-8"))
    assert meta["episode_count"] == 1
