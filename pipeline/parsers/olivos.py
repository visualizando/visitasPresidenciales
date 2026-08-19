from __future__ import annotations

import re
from datetime import datetime

from pipeline.models import ParseResult, RemoteFile
from pipeline.parsers.common import find_datetimes, make_record

DATE_HEADING_RE = re.compile(
    r"(?:D[IÍ]A|FECHA)\s+(?P<day>\d{1,2})\s+(?:DE\s+)?(?P<month>[A-ZÁÉÍÓÚ]+)\s+(?:DE\s+)?(?P<year>20\d{2})",
    re.IGNORECASE,
)
ROW_RE = re.compile(
    r"^\s*\d+\s+(?P<name>[A-ZÁÉÍÓÚÜÑ ,.'-]{3,}?)\s+"
    r"(?P<doc>\d{1,2}(?:\.\d{3}){2}|\d{7,11})\s+(?P<rest>.+)$",
    re.IGNORECASE,
)
MONTHS = {
    "ENERO": 1,
    "FEBRERO": 2,
    "MARZO": 3,
    "ABRIL": 4,
    "MAYO": 5,
    "JUNIO": 6,
    "JULIO": 7,
    "AGOSTO": 8,
    "SEPTIEMBRE": 9,
    "SETIEMBRE": 9,
    "OCTUBRE": 10,
    "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}


def parse_olivos_pages(pages: list[str], remote: RemoteFile, source_id: str) -> ParseResult:
    result = ParseResult(parser="olivos-planillas-v1")
    document_date: datetime | None = None
    for page_number, text in enumerate(pages, start=1):
        heading = DATE_HEADING_RE.search(text)
        if heading:
            month = MONTHS.get(heading.group("month").upper())
            if month:
                document_date = datetime(
                    int(heading.group("year")), month, int(heading.group("day"))
                )
        page_upper = text.upper()
        if "VEHÍCULO" in page_upper or "VEHICULO" in page_upper:
            record_type = "vehicle"
        else:
            record_type = "person"
        for raw_line in text.splitlines():
            line = " ".join(raw_line.split())
            match = ROW_RE.match(line)
            if not match:
                continue
            dates = find_datetimes(match.group("rest"), default_date=document_date)
            if not dates:
                continue
            rest = match.group("rest")
            prefix = rest[: _first_date_offset(rest)].strip()
            destination, purpose, activity = _split_context(prefix)
            result.records.append(
                make_record(
                    remote=remote,
                    source_id=source_id,
                    page=page_number,
                    name=match.group("name"),
                    document=match.group("doc"),
                    record_type=record_type,
                    raw_text=raw_line,
                    entered_at=dates[0],
                    exited_at=dates[1] if len(dates) > 1 else None,
                    destination=destination,
                    purpose=purpose,
                    activity=activity,
                    quality="high" if len(dates) > 1 else "medium",
                )
            )
    return result


def _first_date_offset(value: str) -> int:
    match = re.search(r"\d{1,2}[/-]\d{1,2}[/-](?:\d{2}|\d{4})", value)
    return match.start() if match else len(value)


def _split_context(value: str) -> tuple[str | None, str | None, str | None]:
    tokens = value.split()
    if not tokens:
        return None, None, None
    administration = next(
        (
            i
            for i, token in enumerate(tokens)
            if token in {"ADMINISTRACIÓN", "ADMINISTRACION", "VISITA", "TRABAJO", "OTRO"}
        ),
        None,
    )
    if administration is None:
        return value, None, None
    destination = " ".join(tokens[:administration]) or None
    activity = tokens[administration]
    purpose = " ".join(tokens[administration + 1 :]) or None
    return destination, purpose, activity
