from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pymupdf

from pipeline.models import AccessRecord, ParseResult, RemoteFile
from pipeline.normalize import canonical_name, document_identity, entity_id, stable_id
from pipeline.parsers import legacy_layout as legacy


def parse_positioned_pdf(path: Path, remote: RemoteFile, source_id: str) -> ParseResult:
    """Parse the recurring government ledgers using their stable column geometry."""
    document = pymupdf.open(path)
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    try:
        if remote.location == "casa-rosada":
            layout = None
            for page_number, source_page in enumerate(document, 1):
                texts = _legacy_page(source_page, page_number)["texts"]
                parsed, layout, problem = legacy.parse_casa_page(
                    source_id, remote.path, page_number, texts, layout
                )
                rows.extend(parsed)
                if problem and texts:
                    warnings.append(f"página {page_number}: {problem}")
            records = [_record_from_casa(row, remote, source_id) for row in rows]
            return ParseResult("casa-rosada-tabla-posicional-v1", records, warnings)

        last_type = None
        control_layout = None
        monthly_layout = None
        for page_number, source_page in enumerate(document, 1):
            texts = _legacy_page(source_page, page_number)["texts"]
            page_type = legacy.detect_olivos_page_type(texts)
            if page_type == "unknown" and last_type in {"control_turno", "monthly_ledger"}:
                page_type = last_type
            page_id = f"{source_id}:{page_number}"
            if page_type == "registro_ingresos":
                _, parsed = legacy.parse_olivos_standard_page(
                    page_id, source_id, remote.path, page_number, texts
                )
                rows.extend((row | {"_kind": "person"}) for row in parsed)
            elif page_type == "control_turno":
                _, _, parsed, control_layout, problem = legacy.parse_olivos_control_page(
                    page_id, source_id, remote.path, page_number, texts, control_layout
                )
                rows.extend((row | {"_kind": "control"}) for row in parsed)
                if problem:
                    warnings.append(f"página {page_number}: {problem}")
            elif page_type == "vehicle_movements":
                _, parsed = legacy.parse_olivos_vehicle_page(
                    page_id, source_id, remote.path, page_number, texts
                )
                rows.extend((row | {"_kind": "vehicle"}) for row in parsed)
            elif page_type == "on_foot_movements":
                _, parsed = legacy.parse_olivos_on_foot_page(
                    page_id, source_id, remote.path, page_number, texts
                )
                rows.extend((row | {"_kind": "on_foot"}) for row in parsed)
            elif page_type == "monthly_ledger":
                parsed, _, _, _, monthly_layout, problem = legacy.parse_olivos_monthly_page(
                    page_id, source_id, remote.path, page_number, texts, monthly_layout
                )
                rows.extend((row | {"_kind": "monthly"}) for row in parsed)
                if problem:
                    warnings.append(f"página {page_number}: {problem}")
            elif len(texts) > 5:
                warnings.append(f"página {page_number}: formato de Olivos desconocido")
            if page_type != "unknown":
                last_type = page_type
        records = [_record_from_olivos(row, remote, source_id) for row in rows]
        return ParseResult("olivos-tabla-posicional-v1", records, warnings)
    finally:
        document.close()


def _legacy_page(page: pymupdf.Page, page_number: int) -> dict[str, Any]:
    # pdftohtml, used by the proven legacy parser, emits CSS pixels at 96 dpi.
    # Poppler's XML output uses approximately 1.4 CSS pixels per PDF point.
    # Keeping that coordinate system lets us reuse the previously verified
    # Olivos column boundaries while PyMuPDF supplies the text spans.
    scale = 1.4
    texts: list[dict[str, Any]] = []
    for block in page.get_text("dict", sort=True)["blocks"]:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                value = legacy.normalize_whitespace(span["text"])
                if not value:
                    continue
                left, top, right, _ = span["bbox"]
                left, top, right = int(left * scale), int(top * scale), int(right * scale)
                texts.append(
                    {
                        "top": top,
                        "left": left,
                        "width": right - left,
                        "right": right,
                        "text": value,
                        "norm": legacy.norm(value),
                    }
                )
    texts.sort(key=lambda item: (item["top"], item["left"]))
    return {"page_number": page_number, "texts": texts}


def _record_from_casa(
    row: dict[str, Any], remote: RemoteFile, source_id: str
) -> AccessRecord:
    return _make_record(
        remote,
        source_id,
        row,
        name=row.get("visitor_name") or row.get("visitor_raw", ""),
        document=row.get("visitor_document"),
        record_type="visitor",
        entered=_datetime(row.get("entry_iso")),
        exited=_datetime(row.get("exit_iso")),
        destination=_join(row.get("dependency"), row.get("access_point")),
        purpose=row.get("observations"),
        activity=row.get("function"),
        authorized_by=row.get("authorized_by"),
    )


def _record_from_olivos(
    row: dict[str, Any], remote: RemoteFile, source_id: str
) -> AccessRecord:
    kind = row["_kind"]
    entered = _datetime(row.get("entry_iso"))
    exited = _datetime(row.get("exit_iso"))
    if kind == "control":
        entered = _date_time(row.get("register_date_start"), row.get("entry_time_raw"))
        exited = _date_time(row.get("register_date_start"), row.get("exit_time_raw"), entered)
    entered = _sanitize_olivos_date(entered, remote)
    exited = _sanitize_olivos_date(exited, remote)
    purpose = row.get("meeting") or row.get("motivo") or row.get("actividad_otro")
    activity = _join(
        row.get("function"),
        row.get("cargo_o_funcion"),
        row.get("actividad_funcionario"),
        row.get("actividad_trabajo"),
        row.get("actividad_visita"),
        row.get("modo"),
    )
    return _make_record(
        remote,
        source_id,
        row,
        name=row.get("visitor_raw", ""),
        document=None,
        record_type="vehicle" if kind == "vehicle" else "person",
        entered=entered,
        exited=exited,
        destination=row.get("concurre_para") or row.get("concurre_a"),
        purpose=purpose,
        activity=activity,
        authorized_by=row.get("authorized_by") or row.get("autorizado_por"),
    )


def _make_record(
    remote: RemoteFile,
    source_id: str,
    row: dict[str, Any],
    *,
    name: str,
    document: str | None,
    record_type: str,
    entered: datetime | None,
    exited: datetime | None,
    destination: str | None,
    purpose: str | None,
    activity: str | None,
    authorized_by: str | None,
) -> AccessRecord:
    name = canonical_name(name)
    document_type, document_number, _ = document_identity(document)
    person_id = entity_id(name, document_number)
    record_id = stable_id(
        "rec_", person_id, remote.location, record_type, entered, exited, destination
    )
    return AccessRecord(
        record_id=record_id,
        entity_id=person_id,
        canonical_name=name,
        document_type=document_type,
        document_number=document_number,
        location=remote.location,
        record_type=record_type,  # type: ignore[arg-type]
        source_id=source_id,
        source_url=remote.url,
        source_path=remote.path,
        source_page=int(row.get("page_number") or 1),
        entered_at=entered,
        exited_at=exited,
        destination=_clean(destination),
        purpose=_clean(purpose),
        activity=_clean(activity),
        authorized_by=_clean(authorized_by),
        quality="high" if entered else "medium",
        raw_text=_join(name, document, destination, purpose, activity) or name,
    )


def _datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _sanitize_olivos_date(value: datetime | None, remote: RemoteFile) -> datetime | None:
    if value is None or abs(value.year - remote.year) <= 1:
        return value
    filename = Path(remote.path).stem
    day = next(
        (
            int(match.group(1))
            for match in re.finditer(r"(?:^|\D)([0-3]?\d)(?:\D|$)", filename)
            if 1 <= int(match.group(1)) <= 31
        ),
        1,
    )
    try:
        return value.replace(year=remote.year, month=remote.month, day=day)
    except ValueError:
        return None


def _date_time(
    date_value: str | None, time_value: str | None, entry: datetime | None = None
) -> datetime | None:
    if not date_value or not time_value:
        return None
    try:
        value = datetime.fromisoformat(f"{date_value}T{time_value.strip()}")
    except ValueError:
        return None
    if entry and value < entry:
        value += timedelta(days=1)
    return value


def _join(*values: str | None) -> str | None:
    result = " · ".join(value.strip() for value in values if value and value.strip())
    return result or None


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value if value and value not in {"-", "–"} else None
