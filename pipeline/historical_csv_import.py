from __future__ import annotations

import csv
import hashlib
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from pipeline.build_web import build_web_data
from pipeline.models import AccessRecord
from pipeline.normalize import canonical_name, document_identity, entity_id, stable_id
from pipeline.storage import load_json, utc_now, write_json_atomic, write_partition

SOURCE_PATH = "historical/olivos/datos_olivos-csv.csv"


def import_olivos_historical_csv(
    source_csv: Path,
    data_dir: Path,
    web_data_dir: Path,
    *,
    first_year: int = 2020,
    last_year: int = 2021,
) -> dict[str, int]:
    """Import the previously unified Olivos CSV in a reproducible, idempotent way."""
    source_id = stable_id("src_", SOURCE_PATH)
    partitions_root = data_dir / "partitions"
    for previous in partitions_root.rglob(f"{source_id}.parquet") if partitions_root.exists() else []:
        previous.unlink()

    partitions: dict[tuple[int, int], list[AccessRecord]] = defaultdict(list)
    diagnostics = defaultdict(int)
    with source_csv.open(encoding="utf-8-sig", newline="") as handle:
        for line_number, row in enumerate(csv.DictReader(handle), start=2):
            record = _record_from_row(row, source_id, line_number, first_year, last_year, diagnostics)
            if not record:
                continue
            timestamp = record.entered_at or record.exited_at
            assert timestamp is not None
            partitions[(timestamp.year, timestamp.month)].append(record)

    partitions_by_source = []
    for (year, month), records in sorted(partitions.items()):
        relative = Path("olivos") / str(year) / f"{month:02d}" / f"{source_id}.parquet"
        write_partition(partitions_root / relative, records)
        partitions_by_source.append(relative.as_posix())

    manifest = load_json(
        data_dir / "manifest.json", {"version": 1, "generated_at": None, "files": {}}
    )
    info = source_csv.stat()
    manifest["files"][SOURCE_PATH] = {
        "source_id": source_id,
        "url": "local-source:///" + quote(SOURCE_PATH),
        "path": SOURCE_PATH,
        "location": "olivos",
        "year": first_year,
        "month": 1,
        "size": info.st_size,
        "etag": None,
        "last_modified": str(info.st_mtime_ns),
        "sha256": _file_sha256(source_csv),
        "parser": "olivos-csv-historico-v1",
        "record_count": sum(len(records) for records in partitions.values()),
        "status": "active",
        "partition": None,
        "partitions": partitions_by_source,
        "processed_at": utc_now(),
        "import_diagnostics": dict(sorted(diagnostics.items())),
    }
    manifest["generated_at"] = utc_now()
    write_json_atomic(data_dir / "manifest.json", manifest)
    web = build_web_data(data_dir, web_data_dir)
    return {"imported": sum(len(records) for records in partitions.values()), **dict(diagnostics), **web}


def _record_from_row(
    row: dict[str, str],
    source_id: str,
    line_number: int,
    first_year: int,
    last_year: int,
    diagnostics: defaultdict[str, int],
) -> AccessRecord | None:
    try:
        access_date = date.fromisoformat((row.get("dia") or "").strip())
    except ValueError:
        diagnostics["invalid_date"] += 1
        return None
    if not first_year <= access_date.year <= last_year:
        diagnostics["outside_year_range"] += 1
        return None

    name = canonical_name(row.get("nombre") or "")
    if not name:
        diagnostics["missing_name"] += 1
        return None
    entered = _timestamp(row.get("entrada"))
    exited = _timestamp(row.get("salida"))
    if entered is None and exited is None:
        diagnostics["missing_timestamp"] += 1
        return None
    if entered and entered.date() != access_date:
        diagnostics["entry_date_mismatch"] += 1
        return None
    if exited and exited.date() not in {access_date, access_date + timedelta(days=1)}:
        diagnostics["exit_date_mismatch"] += 1
        exited = None

    document_type, document_number, _ = document_identity(row.get("doc"))
    person_id = entity_id(name, document_number)
    destination = _clean(row.get("fin"))
    activity = _clean(row.get("hoja"))
    record_id = stable_id("rec_", source_id, line_number, person_id, entered, exited, destination)
    raw_text = " | ".join(
        f"{key}={value}" for key, value in row.items() if value and key not in {"Column"}
    )
    return AccessRecord(
        record_id=record_id,
        entity_id=person_id,
        canonical_name=name,
        document_type=document_type,
        document_number=document_number,
        location="olivos",
        record_type="person",
        source_id=source_id,
        source_url="local-source:///" + quote(SOURCE_PATH),
        source_path=SOURCE_PATH,
        source_page=line_number,
        entered_at=entered,
        exited_at=exited,
        destination=destination,
        activity=activity,
        quality="high" if entered and exited else "medium",
        raw_text=raw_text,
    )


def _timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=None)


def _clean(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
