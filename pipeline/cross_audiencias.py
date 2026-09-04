"""Cross-reference audiencias de interes with Casa Rosada access events.

For each person who appears in both datasets, find dates where they had an
audiencia AND a Casa Rosada visit on the same day.  These confirmed matches
reveal which ``lugar`` and ``sujeto_obligado`` values correspond to meetings
held at Casa Rosada.

The patterns extracted from confirmed matches are then applied to ALL
audiencias to classify them as:
  - ``confirmed``: same person, same date matched a CR visit
  - ``likely``: same official or same lugar was confirmed at CR in other cases
  - ``unconfirmed``: no pattern matched
"""

from __future__ import annotations

import csv
import glob
import gzip
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pipeline.normalize import fold_text

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CRPatterns:
    """Patterns extracted from confirmed date-matches."""

    officials: dict[str, dict[str, int]]
    lugares: dict[str, dict[str, int]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "officials": self.officials,
            "lugares": self.lugares,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CRPatterns:
        return cls(officials=data.get("officials", {}), lugares=data.get("lugares", {}))


@dataclass
class AudienciaClassification:
    audiencia_id: str
    status: str  # "confirmed" | "likely" | "unconfirmed"
    official_name: str
    official_cargo: str
    lugar: str
    date: str
    cr_destination: str  # empty for "likely" matches
    cr_record_id: str  # record_id of the matched CR event (empty unless confirmed)
    confidence: str  # "high" (confirmed) | "medium" (likely) | "low"


@dataclass
class CrossResult:
    per_entity: dict[str, list[AudienciaClassification]]
    patterns: CRPatterns
    confirmed_count: int
    likely_count: int
    unconfirmed_count: int


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_cr_events(events_dir: Path) -> list[dict[str, str]]:
    """Load Casa Rosada events from gzipped JSON shards.

    Returns a list of dicts with entity_id, date (YYYY-MM-DD), destination,
    and canonical_name.
    """
    events: list[dict[str, str]] = []
    for shard in sorted(glob.glob(str(events_dir / "*.json.gz"))):
        with gzip.open(shard, "rt", encoding="utf-8") as handle:
            for event in json.load(handle):
                eid = event.get("entity_id")
                entered = event.get("entered_at") or event.get("occurred_at") or ""
                dest = event.get("destination") or ""
                if eid and entered:
                    try:
                        dt = datetime.fromisoformat(entered.replace("Z", "+00:00"))
                        events.append({
                            "entity_id": eid,
                            "record_id": event.get("record_id", ""),
                            "date": dt.strftime("%Y-%m-%d"),
                            "entered_at": event.get("entered_at") or "",
                            "destination": dest.strip(),
                            "canonical_name": event.get("canonical_name", ""),
                        })
                    except (ValueError, TypeError):
                        pass
    return events


def load_audiencias_rows(unificado: Path) -> list[dict[str, str]]:
    """Load all rows from the unified audiencias CSV (plain or .gz)."""
    opener = gzip.open if unificado.suffix == ".gz" else open
    with opener(unificado, "rt", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


def _normalize_lugar(lugar: str) -> str:
    """Normalize lugar field for consistent matching."""
    value = fold_text(lugar).strip()
    for prefix in ("- ", "– ", "— "):
        if value.startswith(prefix):
            value = value[len(prefix):]
    return value.strip()


def _normalize_sujeto(nombre: str) -> str:
    """Normalize sujeto_obligado_nombre for consistent matching."""
    return fold_text(nombre).strip().upper()


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def find_date_matches(
    aud_rows: list[dict[str, str]],
    cr_events: list[dict[str, str]],
    master: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find audiencias that coincide with a CR visit on the same date.

    Returns a list of confirmed match dicts.
    """
    # Build entity_id lookup from master
    eid_lookup: dict[tuple[str, str], str] = {}
    for m in master:
        key = (fold_text(m["nombre"]).strip().upper(), m.get("document_number") or "")
        eid_lookup[key] = m["entity_id"]

    # Index CR events by entity_id
    cr_by_entity: dict[str, list[dict[str, str]]] = defaultdict(list)
    for event in cr_events:
        cr_by_entity[event["entity_id"]].append(event)

    confirmed: list[dict[str, Any]] = []
    for row in aud_rows:
        nombre = (row.get("solicitante_nombre") or "").strip().upper()
        doc = (row.get("solicitante_id") or "").strip()
        fecha = (row.get("fecha") or "").strip()[:10]
        eid = eid_lookup.get((fold_text(nombre).strip().upper(), doc))
        if not eid or not fecha:
            continue
        for cr in cr_by_entity.get(eid, []):
            if cr["date"] == fecha:
                confirmed.append({
                    "audiencia_id": row.get("id", ""),
                    "entity_id": eid,
                    "date": fecha,
                    "lugar": _normalize_lugar(row.get("lugar", "")),
                    "sujeto_nombre": _normalize_sujeto(row.get("sujeto_obligado_nombre", "")),
                    "sujeto_cargo": (row.get("sujeto_obligado_cargo") or "").strip(),
                    "cr_destination": cr["destination"],
                    "cr_record_id": cr.get("record_id", ""),
                    "cr_entered_at": cr.get("entered_at", ""),
                })
                break  # one match per audiencia row is enough
    return confirmed


def extract_patterns(confirmed: list[dict[str, Any]]) -> CRPatterns:
    """Extract lugar- and official-to-CR-destination patterns from confirmed matches."""
    officials: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    lugares: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for match in confirmed:
        lu = match["lugar"]
        su = match["sujeto_nombre"]
        dest = match["cr_destination"]
        if lu:
            lugares[lu][dest] += 1
        if su:
            officials[su][dest] += 1

    # Convert inner defaultdicts to plain dicts
    return CRPatterns(
        officials={k: dict(v) for k, v in officials.items()},
        lugares={k: dict(v) for k, v in lugares.items()},
    )


def classify_audiencias(
    aud_rows: list[dict[str, str]],
    confirmed: list[dict[str, Any]],
    patterns: CRPatterns,
    master: list[dict[str, Any]],
) -> CrossResult:
    """Classify every audiencia row as confirmed, likely, or unconfirmed.

    A row is ``confirmed`` if it appears in the confirmed matches list.
    A row is ``likely`` if its lugar or sujeto_obligado was confirmed at CR
    in at least one other match (pattern-based inference).
    Otherwise it is ``unconfirmed``.
    """
    # Build entity_id lookup
    eid_lookup: dict[tuple[str, str], str] = {}
    for m in master:
        key = (fold_text(m["nombre"]).strip().upper(), m.get("document_number") or "")
        eid_lookup[key] = m["entity_id"]

    # Index confirmed by audiencia_id for fast lookup
    confirmed_ids: dict[str, dict[str, Any]] = {
        m["audiencia_id"]: m for m in confirmed if m.get("audiencia_id")
    }

    # Pre-compute minimum thresholds for "likely" patterns
    # A lugar/official needs at least 2 confirmed matches to be used as pattern
    MIN_PATTERN_COUNT = 2
    lugar_set: set[str] = set()
    for lu, dests in patterns.lugares.items():
        if sum(dests.values()) >= MIN_PATTERN_COUNT:
            lugar_set.add(lu)
    official_set: set[str] = set()
    for su, dests in patterns.officials.items():
        if sum(dests.values()) >= MIN_PATTERN_COUNT:
            official_set.add(su)

    per_entity: dict[str, list[AudienciaClassification]] = defaultdict(list)
    confirmed_count = 0
    likely_count = 0
    unconfirmed_count = 0

    for row in aud_rows:
        audiencia_id = row.get("id", "")
        nombre = (row.get("solicitante_nombre") or "").strip().upper()
        doc = (row.get("solicitante_id") or "").strip()
        fecha = (row.get("fecha") or "").strip()[:10]
        lugar = _normalize_lugar(row.get("lugar", ""))
        sujeto_nombre = _normalize_sujeto(row.get("sujeto_obligado_nombre", ""))
        sujeto_cargo = (row.get("sujeto_obligado_cargo") or "").strip()
        eid = eid_lookup.get((fold_text(nombre).strip().upper(), doc))
        if not eid:
            continue

        # Check if directly confirmed
        if audiencia_id in confirmed_ids:
            cr_dest = confirmed_ids[audiencia_id]["cr_destination"]
            cr_rec = confirmed_ids[audiencia_id].get("cr_record_id", "")
            classification = AudienciaClassification(
                audiencia_id=audiencia_id,
                status="confirmed",
                official_name=sujeto_nombre,
                official_cargo=sujeto_cargo,
                lugar=lugar,
                date=fecha,
                cr_destination=cr_dest,
                cr_record_id=cr_rec,
                confidence="high",
            )
            per_entity[eid].append(classification)
            confirmed_count += 1
            continue

        # Check if likely (pattern match)
        lugar_match = lugar in lugar_set
        official_match = sujeto_nombre in official_set
        if lugar_match or official_match:
            classification = AudienciaClassification(
                audiencia_id=audiencia_id,
                status="likely",
                official_name=sujeto_nombre,
                official_cargo=sujeto_cargo,
                lugar=lugar,
                date=fecha,
                cr_destination="",
                cr_record_id="",
                confidence="medium",
            )
            per_entity[eid].append(classification)
            likely_count += 1
            continue

        # Unconfirmed
        classification = AudienciaClassification(
            audiencia_id=audiencia_id,
            status="unconfirmed",
            official_name=sujeto_nombre,
            official_cargo=sujeto_cargo,
            lugar=lugar,
            date=fecha,
            cr_destination="",
            cr_record_id="",
            confidence="low",
        )
        per_entity[eid].append(classification)
        unconfirmed_count += 1

    return CrossResult(
        per_entity=dict(per_entity),
        patterns=patterns,
        confirmed_count=confirmed_count,
        likely_count=likely_count,
        unconfirmed_count=unconfirmed_count,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def cross_audiencias(
    unificado: Path,
    events_dir: Path,
    master: list[dict[str, Any]],
) -> CrossResult:
    """Run the full cross-reference pipeline.

    1. Load CR events and audiencias rows
    2. Find date-matches (same person, same day)
    3. Extract patterns from confirmed matches
    4. Classify all audiencias
    """
    cr_events = load_cr_events(events_dir)
    aud_rows = load_audiencias_rows(unificado)
    confirmed = find_date_matches(aud_rows, cr_events, master)
    patterns = extract_patterns(confirmed)
    return classify_audiencias(aud_rows, confirmed, patterns, master)
