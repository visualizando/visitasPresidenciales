from __future__ import annotations

import re
from collections.abc import Iterable

from pipeline.models import ParseResult, RemoteFile
from pipeline.normalize import parse_datetime
from pipeline.parsers.common import find_datetimes, make_record

PERSON_RE = re.compile(
    r"^(?P<name>[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ ,.'-]{2,}?)\s+CUIL\s*:\s*"
    r"(?P<doc>[\d.\-]{8,})(?:\s+(?P<rest>.*))?$",
    re.IGNORECASE,
)
MOVEMENT_RE = re.compile(
    r"(?P<device>[A-Z0-9_. -]+?[_ -](?P<direction>ENTRADA|SALIDA))\s+"
    r"(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<time>\d{1,2}:\d{2}\s*(?:A\.?\s?M\.?|P\.?\s?M\.?|AM|PM)?)\s+"
    r"(?P<status>.+)$",
    re.IGNORECASE,
)
VISITOR_RE = re.compile(
    r"^\s*\d+\s+(?P<name>[A-ZÁÉÍÓÚÜÑ ,.'-]{3,}?)\s+"
    r"(?P<doc>\d{1,2}(?:\.\d{3}){2}|\d{7,11})\s+(?P<rest>.+)$",
    re.IGNORECASE,
)


def parse_casa_pages(
    pages: Iterable[str], remote: RemoteFile, source_id: str, *, family: str = "movement"
) -> ParseResult:
    if family == "visitor":
        return _parse_visitors(pages, remote, source_id)
    result = ParseResult(parser="casa-rosada-movimientos-v1")
    current_name: str | None = None
    current_doc: str | None = None
    for page_number, text in enumerate(pages, start=1):
        for raw_line in text.splitlines():
            line = " ".join(raw_line.split())
            if not line:
                continue
            person = PERSON_RE.match(line)
            if person:
                current_name = person.group("name")
                current_doc = person.group("doc")
                line = person.group("rest") or ""
            movement = MOVEMENT_RE.search(line)
            if not movement or not current_name:
                continue
            occurred = parse_datetime(f"{movement.group('date')} {movement.group('time')}")
            if not occurred:
                result.warnings.append(f"Fecha ilegible en página {page_number}: {line[:120]}")
                continue
            direction = movement.group("direction").lower()
            result.records.append(
                make_record(
                    remote=remote,
                    source_id=source_id,
                    page=page_number,
                    name=current_name,
                    document=current_doc,
                    record_type="movement",
                    raw_text=raw_line,
                    occurred_at=occurred,
                    direction=direction,
                    device=movement.group("device").strip(),
                    access_status=movement.group("status").strip(),
                    quality="high",
                )
            )
    return result


def _parse_visitors(pages: list[str], remote: RemoteFile, source_id: str) -> ParseResult:
    result = ParseResult(parser="casa-rosada-visitantes-v1")
    for page_number, text in enumerate(pages, start=1):
        for raw_line in text.splitlines():
            line = " ".join(raw_line.split())
            match = VISITOR_RE.match(line)
            if not match:
                continue
            dates = find_datetimes(match.group("rest"))
            if not dates:
                continue
            result.records.append(
                make_record(
                    remote=remote,
                    source_id=source_id,
                    page=page_number,
                    name=match.group("name"),
                    document=match.group("doc"),
                    record_type="visitor",
                    raw_text=raw_line,
                    entered_at=dates[0],
                    exited_at=dates[1] if len(dates) > 1 else None,
                    purpose=_text_before_first_date(match.group("rest")),
                    quality="medium" if len(dates) > 1 else "low",
                )
            )
    return result


def _text_before_first_date(value: str) -> str | None:
    match = re.search(r"\d{1,2}[/-]\d{1,2}[/-](?:\d{2}|\d{4})", value)
    return value[: match.start()].strip() if match and match.start() else None
