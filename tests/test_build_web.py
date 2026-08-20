import gzip
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
    assert (output / "search" / "name" / "p.json.gz").exists()
    assert list((output / "events").glob("*.json.gz"))
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
        json.loads(gzip.decompress(path.read_bytes()))
        for path in (output / "cooccurrences").glob("*.json.gz")
    ]
    owner = next(shard["per_1"] for shard in shards if "per_1" in shard)
    assert owner["p"]["per_2"][0] == "GOMEZ LUIS"
    assert "per_3" not in owner["p"]
    assert owner["e"] == [["per_2", "2023-01-02", 0, 0, 30, 1, "09:30", "10:00"]]
    meta = json.loads((output / "cooccurrences" / "meta.json").read_text(encoding="utf-8"))
    assert meta["episode_count"] == 1


def test_builds_person_summary_when_record_has_no_timestamp(tmp_path) -> None:
    data = tmp_path / "data"
    output = tmp_path / "public" / "data"
    record = AccessRecord(
        record_id="rec_without_time",
        entity_id="per_without_time",
        canonical_name="PEREZ SIN HORARIO",
        document_type=None,
        document_number=None,
        location="olivos",
        record_type="person",
        source_id="src_1",
        source_url="https://example.org/olivos/2022/01/01.pdf",
        source_path="olivos/2022/01/01.pdf",
        source_page=1,
        quality="low",
        raw_text="fila sin horario",
    )
    write_partition(data / "partitions" / "olivos" / "2022" / "01" / "src.parquet", [record])
    stats = build_web_data(data, output)
    assert stats["people"] == 1
    people = json.loads(
        gzip.decompress((output / "search" / "name" / "p.json.gz").read_bytes())
    )
    assert people[0]["canonical_name"] == "PEREZ SIN HORARIO"


def test_rankings_count_one_daily_presence_per_person_and_location(tmp_path) -> None:
    data = tmp_path / "data"
    output = tmp_path / "public" / "data"
    common = {
        "entity_id": "per_1",
        "canonical_name": "PEREZ ANA",
        "document_type": "DNI",
        "document_number": "30123456",
        "record_type": "movement",
        "source_id": "src_1",
        "source_url": "https://example.org/source.pdf",
        "source_path": "source.pdf",
        "source_page": 1,
        "quality": "high",
        "raw_text": "fila",
    }
    records = [
        AccessRecord(record_id="rec_1", location="casa-rosada", occurred_at=datetime(2023, 1, 2, 9, 0), **common),
        AccessRecord(record_id="rec_2", location="casa-rosada", occurred_at=datetime(2023, 1, 2, 18, 0), **common),
        AccessRecord(record_id="rec_3", location="olivos", occurred_at=datetime(2023, 1, 2, 20, 0), **common),
        AccessRecord(record_id="rec_4", location="casa-rosada", occurred_at=datetime(2023, 1, 3, 9, 0), **common),
    ]
    write_partition(data / "partitions" / "casa-rosada" / "2023" / "01" / "src.parquet", records)

    build_web_data(data, output)

    rankings = json.loads((output / "analytics" / "rankings.json").read_text(encoding="utf-8"))
    year = rankings["rankings"]["year"]["2023"]
    assert year["casa-rosada"][0]["daily_visits"] == 2
    assert year["olivos"][0]["daily_visits"] == 1
    assert year["all"][0]["daily_visits"] == 3
    assert rankings["rankings"]["presidency"]["fernandez"]["all"][0]["daily_visits"] == 3


def test_builds_coverage_with_gaps_and_quarantined_files(tmp_path) -> None:
    data = tmp_path / "data"
    output = tmp_path / "public" / "data"
    records = [
        AccessRecord(
            record_id="coverage_1",
            entity_id="per_coverage",
            canonical_name="PERSONA COBERTURA",
            document_type=None,
            document_number=None,
            location="casa-rosada",
            record_type="visitor",
            source_id="src_coverage",
            source_url="https://example.org/source.pdf",
            source_path="source.pdf",
            source_page=1,
            occurred_at=datetime(2023, 1, 1, 10, 0),
            quality="high",
            raw_text="fila",
        ),
        AccessRecord(
            record_id="coverage_2",
            entity_id="per_coverage",
            canonical_name="PERSONA COBERTURA",
            document_type=None,
            document_number=None,
            location="casa-rosada",
            record_type="visitor",
            source_id="src_coverage",
            source_url="https://example.org/source.pdf",
            source_path="source.pdf",
            source_page=1,
            occurred_at=datetime(2023, 3, 1, 10, 0),
            quality="high",
            raw_text="fila",
        ),
    ]
    write_partition(data / "partitions" / "casa-rosada" / "2023" / "01" / "src.parquet", records)
    (data / "manifest.json").write_text(
        json.dumps(
            {"files": {"scan.pdf": {"path": "scan.pdf", "location": "olivos", "year": 2023, "month": 2, "status": "quarantined", "record_count": 0, "parser": "no-legible-o-formato-desconocido-v1"}}}
        ),
        encoding="utf-8",
    )

    build_web_data(data, output)

    coverage = json.loads((output / "analytics" / "coverage.json").read_text(encoding="utf-8"))
    casa = next(item for item in coverage["locations"] if item["location"] == "casa-rosada")
    assert casa["gaps"][0]["start_month"] == "2023-02"
    assert coverage["summary"]["quarantined_files"] == 1
    assert coverage["file_issues"][0]["status"] == "quarantined"
