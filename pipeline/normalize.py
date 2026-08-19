from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime


def fold_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9]+", " ", ascii_text)).strip().upper()


def canonical_name(value: str) -> str:
    return fold_text(value)


def normalize_document(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    return digits or None


def valid_cuil(value: str | None) -> bool:
    digits = normalize_document(value)
    if not digits or len(digits) != 11:
        return False
    weights = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    total = sum(int(digit) * weight for digit, weight in zip(digits[:10], weights, strict=True))
    check = 11 - (total % 11)
    expected = 0 if check == 11 else 9 if check == 10 else check
    return expected == int(digits[-1])


def document_identity(value: str | None) -> tuple[str | None, str | None, str | None]:
    """Return display type, normalized document and conservative identity key.

    A valid CUIL and its embedded DNI intentionally share the same identity key.
    """
    digits = normalize_document(value)
    if not digits:
        return None, None, None
    if len(digits) == 11 and valid_cuil(digits):
        dni = digits[2:10].lstrip("0") or "0"
        return "CUIL", digits, f"DNI:{dni}"
    if 7 <= len(digits) <= 8:
        return "DNI", digits, f"DNI:{digits.lstrip('0') or '0'}"
    return "DOCUMENTO", digits, f"DOC:{digits}"


def entity_id(name: str, document: str | None) -> str:
    _, _, identity = document_identity(document)
    material = identity or f"NAME:{canonical_name(name)}"
    return "per_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]


def stable_id(prefix: str, *parts: object) -> str:
    material = "\x1f".join("" if part is None else str(part) for part in parts)
    return prefix + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def parse_datetime(value: str, *, default_date: datetime | None = None) -> datetime | None:
    cleaned = value.strip().upper().replace("A.M.", "AM").replace("P.M.", "PM")
    cleaned = cleaned.replace("A. M.", "AM").replace("P. M.", "PM")
    formats = (
        "%d/%m/%Y %I:%M %p",
        "%d/%m/%y %I:%M %p",
        "%d/%m/%Y %H:%M",
        "%d/%m/%y %H:%M",
        "%d-%m-%Y %I:%M %p",
        "%d-%m-%y %I:%M %p",
        "%d-%m-%Y %H:%M",
        "%d-%m-%y %H:%M",
    )
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    if default_date:
        for fmt in ("%I:%M %p", "%H:%M"):
            try:
                parsed = datetime.strptime(cleaned, fmt)
                return default_date.replace(hour=parsed.hour, minute=parsed.minute, second=0)
            except ValueError:
                continue
    return None
