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
    assert (output / "exports" / "olivos" / "2023" / "01.csv.gz").exists()
