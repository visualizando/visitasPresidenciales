from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path

import pymupdf

from pipeline.models import AccessRecord, ParseResult, RemoteFile
from pipeline.normalize import fold_text
from pipeline.parsers.common import find_datetimes, make_record

SPANISH_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}
VISITOR_DAY_RE = re.compile(
    r"(?:lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)\W+"
    r"(\d{1,2})\s*([a-záéíóú]+)\W+(20\d{2})",
    re.IGNORECASE,
)
VISITOR_ROW_RE = re.compile(
    r"^(?P<name>.*?)\s+NDoc:\s*(?P<document>\d{7,11})\s+(?P<context>.*?)\s+"
    r"(?P<entry>\d{1,2}:\d{2})\s+(?P<exit>\d{1,2}:\d{2})\s+(?P<site>\S+)\s*$",
    re.IGNORECASE,
)
LIST_ROW_RE = re.compile(
    r"^(?P<visitor>.*?\([^)]*\))\s+(?P<context>.*?)\s+"
    r"(?P<entry>\d{1,2}/\d{1,2}/20\d{2}\s+\d{1,2}:\d{2})\s+"
    r"(?P<exit>\d{1,2}/\d{1,2}/20\d{2}\s+\d{1,2}:\d{2})\s*$"
)


def parse_historical_tables(path: Path, remote: RemoteFile, source_id: str) -> ParseResult:
    """Parse native historical tables that predate the recurring 2023 layouts."""
    filename = remote.path.lower()
    if remote.location == "casa-rosada" and not any(
        word in filename for word in ("listado", "visitante")
    ):
        return ParseResult("tabla-historica-no-aplicable-v1")

    result = ParseResult(
        "olivos-tabla-historica-v1"
        if remote.location == "olivos"
        else "casa-rosada-listado-historico-v1"
    )
    document = pymupdf.open(path)
    try:
        for page_number, page in enumerate(document, 1):
            tables = page.find_tables().tables
            for table in tables:
                rows = table.extract()
                if remote.location == "olivos":
                    result.records.extend(
                        parse_olivos_table(rows, remote, source_id, page_number)
                    )
                else:
                    result.records.extend(
                        parse_casa_table(rows, remote, source_id, page_number)
                    )
    finally:
        document.close()
    return result


def parse_casa_historical_visitors(
    pages: Iterable[str], remote: RemoteFile, source_id: str
) -> ParseResult:
    """Parse the 2019-2021 visitor ledger with one date heading per page."""
    result = ParseResult("casa-rosada-visitantes-historico-v1")
    current_date: datetime | None = None
    for page_number, text in enumerate(pages, 1):
        for raw_line in text.splitlines():
            line = " ".join(raw_line.split())
            day = VISITOR_DAY_RE.search(line.lower())
            if day:
                month = SPANISH_MONTHS.get(day.group(2).lower())
                if month:
                    current_date = datetime(int(day.group(3)), month, int(day.group(1)))
                continue
            row = VISITOR_ROW_RE.match(line)
            if not row or not current_date:
                continue
            entered = _at_time(current_date, row.group("entry"))
            exited = _at_time(current_date, row.group("exit"))
            if exited < entered:
                exited += timedelta(days=1)
            result.records.append(
                make_record(
                    remote=remote,
                    source_id=source_id,
                    page=page_number,
                    name=row.group("name"),
                    document=row.group("document"),
                    record_type="visitor",
                    raw_text=raw_line,
                    entered_at=entered,
                    exited_at=exited,
                    destination=row.group("site"),
                    purpose=row.group("context"),
                    quality="high",
                )
            )
    return result


def parse_casa_historical_list_pages(
    pages: Iterable[str], remote: RemoteFile, source_id: str
) -> ParseResult:
    """Parse spreadsheet-exported visitor lists without expensive table detection."""
    result = ParseResult("casa-rosada-listado-historico-lineal-v1")
    for page_number, text in enumerate(pages, 1):
        for raw_line in text.splitlines():
            line = " ".join(raw_line.split())
            row = LIST_ROW_RE.match(line)
            if not row:
                continue
            name, document = _visitor(row.group("visitor"))
            dates = find_datetimes(f"{row.group('entry')} {row.group('exit')}")
            if not name or not fold_text(name) or len(dates) < 2:
                continue
            result.records.append(
                make_record(
                    remote=remote,
                    source_id=source_id,
                    page=page_number,
                    name=name,
                    document=document,
                    record_type="visitor",
                    raw_text=raw_line,
                    entered_at=dates[0],
                    exited_at=dates[1],
                    activity=row.group("context") or None,
                    quality="high",
                )
            )
    return result


def _at_time(day: datetime, value: str) -> datetime:
    hour, minute = (int(part) for part in value.split(":"))
    return day.replace(hour=hour, minute=minute)


def _period_date(value: datetime | None, source_year: int) -> datetime | None:
    if value is None or abs(value.year - source_year) > 1:
        return None
    return value


def parse_olivos_table(
    rows: list[list[str | None]], remote: RemoteFile, source_id: str, page: int
) -> list[AccessRecord]:
    if len(rows) < 2:
        return []
    header_rows = rows[:2]
    headers = [
        fold_text(" ".join(_cell(row, index) for row in header_rows))
        for index in range(max(len(row) for row in header_rows))
    ]
    name_index = _column(headers, "APELLIDO Y NOMBRE")
    document_index = _column(headers, "DOCUMENTO")
    destination_index = _column(headers, "CONCURRE")
    authorized_index = _column(headers, "AUTORIZADO")
    entry_index = _column(headers, "HORA ENTRADA")
    exit_index = _column(headers, "HORA SALIDA")
    required = (
        name_index,
        document_index,
        destination_index,
        authorized_index,
        entry_index,
        exit_index,
    )
    if any(index is None for index in required):
        return []

    records: list[AccessRecord] = []
    for row in rows[2:]:
        name = _cell(row, name_index)
        if not name or fold_text(name) in {"APELLIDO Y NOMBRE", "SIN NOVEDAD"}:
            continue
        entry_dates = find_datetimes(_cell(row, entry_index))
        exit_dates = find_datetimes(_cell(row, exit_index))
        entered = _period_date(entry_dates[0] if entry_dates else None, remote.year)
        exited = _period_date(exit_dates[0] if exit_dates else None, remote.year)
        if not entered and not exited:
            continue
        context = [
            _cell(row, index)
            for index in range((destination_index or 0) + 1, authorized_index or 0)
        ]
        record_type = "vehicle" if len(headers) == 10 else "person"
        records.append(
            make_record(
                remote=remote,
                source_id=source_id,
                page=page,
                name=name,
                document=_cell(row, document_index),
                record_type=record_type,
                raw_text=" | ".join(_cell(row, index) for index in range(len(row))),
                entered_at=entered,
                exited_at=exited,
                destination=_cell(row, destination_index),
                activity=" · ".join(value for value in context if value) or None,
                authorized_by=_cell(row, authorized_index),
                quality="high" if entered and exited else "medium",
            )
        )
    return records


def parse_casa_table(
    rows: list[list[str | None]], remote: RemoteFile, source_id: str, page: int
) -> list[AccessRecord]:
    if not rows or len(rows[0]) < 7:
        return []
    header = fold_text(" ".join(_cell(rows[0], index) for index in range(len(rows[0]))))
    starts_with_header = "VISITA" in header and "FECHA DE ENTRADA" in header
    records: list[AccessRecord] = []
    for row in rows[1:] if starts_with_header else rows:
        name, document = _visitor(_cell(row, 0))
        dates = find_datetimes(f"{_cell(row, 5)} {_cell(row, 6)}")
        if not name or not dates:
            continue
        records.append(
            make_record(
                remote=remote,
                source_id=source_id,
                page=page,
                name=name,
                document=document,
                record_type="visitor",
                raw_text=" | ".join(_cell(row, index) for index in range(len(row))),
                entered_at=dates[0],
                exited_at=dates[1] if len(dates) > 1 else None,
                destination=_cell(row, 4),
                purpose=_cell(row, 2),
                activity=_cell(row, 1),
                authorized_by=_cell(row, 3),
                quality="high" if len(dates) > 1 else "medium",
            )
        )
    return records


def _column(headers: list[str], label: str) -> int | None:
    return next((index for index, value in enumerate(headers) if label in value), None)


def _cell(row: list[str | None], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return " ".join(str(row[index] or "").replace("\n", " ").split())


def _visitor(value: str) -> tuple[str, str | None]:
    match = re.match(r"^(.*?)\s*\(([\d. -]{7,})\)\s*$", value)
    if not match:
        return value, None
    return match.group(1).strip(), match.group(2).strip()
