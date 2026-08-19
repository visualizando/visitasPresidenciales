from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

Location = Literal["casa-rosada", "olivos"]
RecordType = Literal["movement", "person", "vehicle", "visitor"]
Quality = Literal["high", "medium", "low"]


@dataclass(slots=True)
class RemoteFile:
    url: str
    path: str
    location: Location
    year: int
    month: int
    size: int | None = None
    etag: str | None = None
    last_modified: str | None = None
    sha256: str | None = None


@dataclass(slots=True)
class AccessRecord:
    record_id: str
    entity_id: str
    canonical_name: str
    document_type: str | None
    document_number: str | None
    location: Location
    record_type: RecordType
    source_id: str
    source_url: str
    source_path: str
    source_page: int
    occurred_at: datetime | None = None
    entered_at: datetime | None = None
    exited_at: datetime | None = None
    direction: str | None = None
    device: str | None = None
    destination: str | None = None
    purpose: str | None = None
    activity: str | None = None
    authorized_by: str | None = None
    access_status: str | None = None
    quality: Quality = "medium"
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("occurred_at", "entered_at", "exited_at"):
            if value[key] is not None:
                value[key] = value[key].isoformat()
        return value


@dataclass(slots=True)
class ParseResult:
    parser: str
    records: list[AccessRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ManifestEntry:
    source_id: str
    url: str
    path: str
    location: Location
    year: int
    month: int
    size: int | None
    etag: str | None
    last_modified: str | None
    sha256: str
    parser: str
    record_count: int
    status: Literal["active", "missing", "quarantined"] = "active"
    partition: str | None = None
    processed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
