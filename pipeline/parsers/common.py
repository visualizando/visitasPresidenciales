from __future__ import annotations

import re
from datetime import datetime

from pipeline.models import AccessRecord, RemoteFile
from pipeline.normalize import (
    canonical_name,
    document_identity,
    entity_id,
    parse_datetime,
    stable_id,
)

DATE_TIME_RE = re.compile(
    r"(?P<date>\d{1,2}[/-]\d{1,2}[/-](?:\d{2}|\d{4}))\s+"
    r"(?P<time>\d{1,2}:\d{2}\s*(?:A\.?\s?M\.?|P\.?\s?M\.?|AM|PM)?)",
    re.IGNORECASE,
)


def make_record(
    *,
    remote: RemoteFile,
    source_id: str,
    page: int,
    name: str,
    document: str | None,
    record_type: str,
    raw_text: str,
    occurred_at: datetime | None = None,
    entered_at: datetime | None = None,
    exited_at: datetime | None = None,
    direction: str | None = None,
    device: str | None = None,
    destination: str | None = None,
    purpose: str | None = None,
    activity: str | None = None,
    authorized_by: str | None = None,
    access_status: str | None = None,
    quality: str = "medium",
) -> AccessRecord:
    clean_name = canonical_name(name)
    doc_type, doc_number, _ = document_identity(document)
    person_id = entity_id(clean_name, doc_number)
    logical_time = occurred_at or entered_at or exited_at
    record_id = stable_id(
        "rec_",
        person_id,
        remote.location,
        record_type,
        logical_time.isoformat() if logical_time else "",
        exited_at.isoformat() if exited_at else "",
        direction,
        device,
        destination,
    )
    return AccessRecord(
        record_id=record_id,
        entity_id=person_id,
        canonical_name=clean_name,
        document_type=doc_type,
        document_number=doc_number,
        location=remote.location,
        record_type=record_type,  # type: ignore[arg-type]
        source_id=source_id,
        source_url=remote.url,
        source_path=remote.path,
        source_page=page,
        occurred_at=occurred_at,
        entered_at=entered_at,
        exited_at=exited_at,
        direction=direction,
        device=device,
        destination=destination,
        purpose=purpose,
        activity=activity,
        authorized_by=authorized_by,
        access_status=access_status,
        quality=quality,  # type: ignore[arg-type]
        raw_text=raw_text.strip(),
    )


def find_datetimes(text: str, default_date: datetime | None = None) -> list[datetime]:
    values: list[datetime] = []
    for match in DATE_TIME_RE.finditer(text):
        value = parse_datetime(
            f"{match.group('date')} {match.group('time')}", default_date=default_date
        )
        if value:
            values.append(value)
    return values
