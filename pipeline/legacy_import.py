from __future__ import annotations

import csv
import hashlib
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urljoin

from pipeline.build_web import build_web_data
from pipeline.models import AccessRecord
from pipeline.normalize import canonical_name, document_identity, entity_id, stable_id
from pipeline.storage import load_json, utc_now, write_json_atomic, write_partition


def import_legacy_tsv(
    legacy_dir: Path,
    data_dir: Path,
    web_data_dir: Path,
    public_base_url: str | None = None,
) -> dict[str, int]:
    partitions_root = data_dir / "partitions"
    if partitions_root.exists():
        for obsolete in partitions_root.rglob("src_legacy_*.parquet"):
            if obsolete.resolve().is_relative_to(partitions_root.resolve()):
                obsolete.unlink()
    sources = _read_sources(legacy_dir / "pdf_sources.tsv")
    partitions: dict[tuple[str, int, int, str], list[AccessRecord]] = defaultdict(list)
    table_specs = {
        "casa_gobierno_accesses.tsv": _casa_record,
        "olivos_accesses.tsv": _olivos_standard_record,
        "olivos_control_turno_accesses.tsv": _olivos_control_record,
        "olivos_monthly_accesses.tsv": _olivos_monthly_record,
        "olivos_vehicle_movements.tsv": _olivos_vehicle_record,
        "olivos_on_foot_movements.tsv": _olivos_on_foot_record,
    }
    imported = 0
    per_source: dict[str, int] = defaultdict(int)
    for filename, converter in table_specs.items():
        path = legacy_dir / filename
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                fixed = {key: _repair(value or "") for key, value in row.items()}
                source = sources.get(fixed.get("source_id", ""))
                if not source:
                    continue
                record = converter(fixed, source, public_base_url)
                if not record:
                    continue
                date = record.occurred_at or record.entered_at or record.exited_at
                if not date or date.year < 2023:
                    continue
                key = (record.location, date.year, date.month, record.source_id)
                partitions[key].append(record)
                imported += 1
                per_source[record.source_id] += 1

    manifest = load_json(
        data_dir / "manifest.json", {"version": 1, "generated_at": None, "files": {}}
    )
    partitions_by_source: dict[str, list[str]] = defaultdict(list)
    for (location, year, month, source_id), records in partitions.items():
        relative = Path(location) / str(year) / f"{month:02d}" / f"{source_id}.parquet"
        write_partition(data_dir / "partitions" / relative, records)
        partitions_by_source[source_id].append(relative.as_posix())
    manifest["files"] = {
        key: value for key, value in manifest["files"].items() if not key.startswith("legacy/")
    }
    for _legacy_id, source in sources.items():
        relative_path = source["relative_path"]
        source_id = stable_id("src_", relative_path)
        url = _source_url(relative_path, legacy_dir, public_base_url)
        original_pdf = legacy_dir.parent / Path(relative_path)
        file_info = original_pdf.stat() if original_pdf.exists() else None
        manifest["files"][relative_path] = {
            "source_id": source_id,
            "url": url,
            "path": relative_path,
            "location": "casa-rosada" if source["site"] == "Casa de Gobierno" else "olivos",
            "year": _source_year(relative_path),
            "month": _source_month(relative_path),
            "size": file_info.st_size if file_info else None,
            "etag": None,
            "last_modified": str(file_info.st_mtime_ns) if file_info else None,
            "sha256": _file_sha256(original_pdf)
            if file_info
            else hashlib.sha256(relative_path.encode()).hexdigest(),
            "parser": "legacy-layout-v1",
            "record_count": per_source.get(source_id, 0),
            "status": "active",
            "partition": None,
            "partitions": sorted(partitions_by_source.get(source_id, [])),
            "processed_at": utc_now(),
        }
    manifest["generated_at"] = utc_now()
    write_json_atomic(data_dir / "manifest.json", manifest)
    web = build_web_data(data_dir, web_data_dir)
    return {"imported": imported, "sources": len(sources), **web}


def _read_sources(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {
            row["source_id"]: {key: _repair(value) for key, value in row.items()}
            for row in csv.DictReader(handle, delimiter="\t")
        }


def _base_record(
    row: dict[str, str],
    source: dict[str, str],
    public_base: str | None,
    *,
    location: str,
    name: str,
    document: str | None,
    record_type: str,
    entered: datetime | None,
    exited: datetime | None,
    destination: str | None = None,
    purpose: str | None = None,
    activity: str | None = None,
    authorized_by: str | None = None,
) -> AccessRecord | None:
    name = canonical_name(name)
    if not name:
        return None
    doc_type, doc_number, _ = document_identity(document)
    person_id = entity_id(name, doc_number)
    source_id = stable_id("src_", source["relative_path"])
    page = int(row.get("page_number") or 1)
    record_id = stable_id("rec_", person_id, location, record_type, entered, exited, destination)
    return AccessRecord(
        record_id=record_id,
        entity_id=person_id,
        canonical_name=name,
        document_type=doc_type,
        document_number=doc_number,
        location=location,  # type: ignore[arg-type]
        record_type=record_type,  # type: ignore[arg-type]
        source_id=source_id,
        source_url=_source_url(source["relative_path"], Path("."), public_base),
        source_path=source["relative_path"],
        source_page=page,
        entered_at=entered,
        exited_at=exited,
        destination=_clean(destination),
        purpose=_clean(purpose),
        activity=_clean(activity),
        authorized_by=_clean(authorized_by),
        quality="high" if entered else "medium",
        raw_text=row.get("visitor_raw", ""),
    )


def _casa_record(row, source, public_base):
    return _base_record(
        row,
        source,
        public_base,
        location="casa-rosada",
        name=row.get("visitor_name") or row.get("visitor_raw", ""),
        document=row.get("visitor_document"),
        record_type="visitor",
        entered=_dt(row.get("entry_iso")),
        exited=_dt(row.get("exit_iso")),
        destination=" · ".join(filter(None, [row.get("dependency"), row.get("access_point")])),
        purpose=row.get("observations"),
        activity=row.get("function"),
        authorized_by=row.get("authorized_by"),
    )


def _olivos_standard_record(row, source, public_base):
    return _base_record(
        row,
        source,
        public_base,
        location="olivos",
        name=row.get("visitor_raw", ""),
        document=None,
        record_type="person",
        entered=_dt(row.get("entry_iso")),
        exited=_dt(row.get("exit_iso")),
        destination=row.get("concurre_para"),
        purpose=row.get("actividad_otro"),
        activity=" · ".join(filter(None, [row.get("actividad_funcionario"), row.get("modo")])),
        authorized_by=row.get("autorizado_por"),
    )


def _olivos_control_record(row, source, public_base):
    entered = _date_time(row.get("register_date_start"), row.get("entry_time_raw"))
    exited = _date_time(row.get("register_date_start"), row.get("exit_time_raw"), entered)
    return _base_record(
        row,
        source,
        public_base,
        location="olivos",
        name=row.get("visitor_raw", ""),
        document=None,
        record_type="person",
        entered=entered,
        exited=exited,
        destination=row.get("concurre_para"),
        purpose=row.get("actividad_otro"),
        activity=row.get("actividad_funcionario"),
        authorized_by=row.get("autorizado_por"),
    )


def _olivos_monthly_record(row, source, public_base):
    return _base_record(
        row,
        source,
        public_base,
        location="olivos",
        name=row.get("visitor_raw", ""),
        document=None,
        record_type="person",
        entered=_dt(row.get("entry_iso")),
        exited=_dt(row.get("exit_iso")),
        destination=row.get("concurre_para"),
        purpose=row.get("meeting"),
        activity=row.get("function"),
        authorized_by=row.get("authorized_by"),
    )


def _olivos_vehicle_record(row, source, public_base):
    return _base_record(
        row,
        source,
        public_base,
        location="olivos",
        name=row.get("visitor_raw", ""),
        document=None,
        record_type="vehicle",
        entered=_dt(row.get("entry_iso")),
        exited=_dt(row.get("exit_iso")),
        destination=row.get("concurre_a"),
        purpose=" · ".join(filter(None, [row.get("actividad_visita"), row.get("actividad_otro")])),
        activity=row.get("actividad_trabajo"),
        authorized_by=row.get("autorizado_por"),
    )


def _olivos_on_foot_record(row, source, public_base):
    return _base_record(
        row,
        source,
        public_base,
        location="olivos",
        name=row.get("visitor_raw", ""),
        document=None,
        record_type="person",
        entered=_dt(row.get("entry_iso")),
        exited=_dt(row.get("exit_iso")),
        destination=row.get("concurre_a"),
        purpose=row.get("motivo"),
        activity=row.get("cargo_o_funcion"),
        authorized_by=row.get("autorizado_por"),
    )


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _date_time(
    date_value: str | None, time_value: str | None, entry: datetime | None = None
) -> datetime | None:
    if not date_value or not time_value or not re.fullmatch(r"\d{1,2}:\d{2}", time_value.strip()):
        return None
    value = datetime.fromisoformat(f"{date_value}T{time_value.strip()}")
    if entry and value < entry:
        value += timedelta(days=1)
    return value


def _repair(value: str) -> str:
    if "Ã" not in value and "Â" not in value:
        return value
    try:
        return value.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return value


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return None if value in {"", "-", "–"} else value


def _source_url(relative: str, legacy_dir: Path, public_base: str | None) -> str:
    if public_base:
        return urljoin(public_base.rstrip("/") + "/", quote(relative.replace("\\", "/")))
    return "local-source:///" + quote(relative.replace("\\", "/"))


def _source_year(path: str) -> int:
    years = [int(value) for value in re.findall(r"20\d{2}", path)]
    return years[-1] if years else 2023


def _source_month(path: str) -> int:
    match = re.search(r"(?:^|/)(0?[1-9]|1[0-2])[_ ]", path.replace("\\", "/"))
    return int(match.group(1)) if match else 1


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
