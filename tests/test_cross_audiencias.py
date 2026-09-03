from __future__ import annotations

import csv
import json
from pathlib import Path

from pipeline.cross_audiencias import (
    CRPatterns,
    classify_audiencias,
    extract_patterns,
    find_date_matches,
    load_audiencias_rows,
    load_cr_events,
)
from pipeline.normalize import entity_id

FLAT_HEADER = [
    "id", "fecha", "fecha_de_publicacion", "sintesis", "lugar", "lat", "lng",
    "motivo", "interes_invocado", "direccion", "sujeto_obligado_id",
    "sujeto_obligado_nombre", "sujeto_obligado_tipo_id",
    "sujeto_obligado_pais", "sujeto_obligado_cargo",
    "sujeto_obligado_dependencia", "solicitante_id", "solicitante_nombre",
    "solicitante_tipo_id", "solicitante_pais", "solicitante_ocupacion",
    "solicitante_presente", "persona_representada_id",
    "persona_representada_tipo_id", "persona_representada_nombre",
    "persona_representada_pais", "persona_representada_ocupacion",
    "persona_juridica_representada_nombre",
    "persona_juridica_representada_pais", "persona_juridica_representada_cuit",
    "grupo_de_personas_representado_nombre",
    "grupo_de_personas_representado_descripcion",
    "grupo_de_personas_representado_pais",
    "organismo_estatal_representado_nombre",
    "organismo_estatal_representado_pais", "participantes_json",
    "id_audiencia", "fecha_solicitud_audiencia",
    "caracter_en_que_participa", "domicilio_representado",
    "estado_cancelada_audiencia", "estado_audiencia",
    "es_persona_juridica", "derivada_a_apellido", "derivada_a_nombre",
    "derivada_a_cargo", "created_at", "updated_at",
]


def _write_audiencias_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(FLAT_HEADER)
        writer.writerows(rows)


def _write_events_shard(path: Path, events: list[dict]) -> None:

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(events).encode("utf-8")
    with path.open("wb") as handle:
        import gzip as gz

        with gz.GzipFile(fileobj=handle, mode="wb", compresslevel=9, mtime=0) as archive:
            archive.write(payload)


def test_find_date_matches(tmp_path: None) -> None:
    """Audiencia + CR visit on the same day = confirmed match."""
    doc = "22333444"
    eid = entity_id("PEREZ CARLOS", doc)
    unificado = tmp_path / "audiencias.csv"
    _write_audiencias_csv(unificado, [
        ["1", "2024-06-15", "", "", "Despacho Canciller", "", "",
         "", "", "", "", "GOMEZ MARIA", "", "", "Ministro", "",
         doc, "PEREZ CARLOS", "", "", "", "", "", "", "", "",
         "", "", "", "", "", "", "", "", "", "", "", "", "",
         "", "", "", "", "", "", "", ""],
    ])
    events_dir = tmp_path / "events"
    _write_events_shard(events_dir / "aa.json.gz", [{
        "entity_id": eid,
        "entered_at": "2024-06-15T10:00:00Z",
        "exited_at": "2024-06-15T12:00:00Z",
        "destination": "MINISTERIO RELACIONES EXTERIORES - RIVADAVIA 250",
        "canonical_name": "PEREZ CARLOS",
    }])
    master = [{
        "entity_id": eid,
        "nombre": "PEREZ, CARLOS",
        "document_number": doc,
    }]
    aud_rows = load_audiencias_rows(unificado)
    cr_events = load_cr_events(events_dir)
    matches = find_date_matches(aud_rows, cr_events, master)
    assert len(matches) == 1
    assert matches[0]["entity_id"] == eid
    assert matches[0]["cr_destination"] == "MINISTERIO RELACIONES EXTERIORES - RIVADAVIA 250"
    assert matches[0]["sujeto_nombre"] == "GOMEZ MARIA"


def test_find_date_no_match_different_date(tmp_path: None) -> None:
    """Different dates = no match."""
    doc = "22333444"
    eid = entity_id("PEREZ CARLOS", doc)
    unificado = tmp_path / "audiencias.csv"
    _write_audiencias_csv(unificado, [
        ["1", "2024-06-15", "", "", "Despacho Canciller", "", "",
         "", "", "", "", "GOMEZ MARIA", "", "", "Ministro", "",
         doc, "PEREZ CARLOS", "", "", "", "", "", "", "", "",
         "", "", "", "", "", "", "", "", "", "", "", "", "",
         "", "", "", "", "", "", "", "", ""],
    ])
    events_dir = tmp_path / "events"
    _write_events_shard(events_dir / "aa.json.gz", [{
        "entity_id": eid,
        "entered_at": "2024-06-20T10:00:00Z",
        "exited_at": "2024-06-20T12:00:00Z",
        "destination": "SOME DESTINATION",
        "canonical_name": "PEREZ CARLOS",
    }])
    master = [{"entity_id": eid, "nombre": "PEREZ, CARLOS", "document_number": doc}]
    matches = find_date_matches(load_audiencias_rows(unificado), load_cr_events(events_dir), master)
    assert len(matches) == 0


def test_extract_patterns_groups_by_official() -> None:
    """Patterns aggregate multiple confirmed matches by official."""
    confirmed = [
        {"lugar": "DESPACHO CANCILLER", "sujeto_nombre": "GOMEZ MARIA", "cr_destination": "RIVADAVIA 250"},
        {"lugar": "DESPACHO CANCILLER", "sujeto_nombre": "GOMEZ MARIA", "cr_destination": "RIVADAVIA 250"},
        {"lugar": "DESPACHO MINISTRO", "sujeto_nombre": "LOPEZ JUAN", "cr_destination": "BALCARCE 50"},
    ]
    patterns = extract_patterns(confirmed)
    assert patterns.officials["GOMEZ MARIA"]["RIVADAVIA 250"] == 2
    assert patterns.officials["LOPEZ JUAN"]["BALCARCE 50"] == 1
    assert patterns.lugares["DESPACHO CANCILLER"]["RIVADAVIA 250"] == 2


def test_classify_audiencias_confirmed_and_likely(tmp_path: None) -> None:
    """Confirmed match stays confirmed; same official in other rows = likely."""
    doc1 = "22333444"
    doc2 = "33444555"
    eid1 = entity_id("PEREZ CARLOS", doc1)
    eid2 = entity_id("LOPEZ ANA", doc2)
    unificado = tmp_path / "audiencias.csv"
    # Two people: PEREZ has a date-match, LOPEZ has a date-match with same official
    # This gives GOMEZ MARIA 2 confirmed matches (meeting threshold)
    _write_audiencias_csv(unificado, [
        ["1", "2024-06-15", "", "", "DESPACHO CANCILLER", "", "",
         "", "", "", "", "GOMEZ MARIA", "", "", "Ministro", "",
         doc1, "PEREZ CARLOS", "", "", "", "", "", "", "", "",
         "", "", "", "", "", "", "", "", "", "", "", "", "",
         "", "", "", "", "", "", "", "", ""],
        ["2", "2024-06-15", "", "", "DESPACHO CANCILLER", "", "",
         "", "", "", "", "GOMEZ MARIA", "", "", "Ministro", "",
         doc2, "LOPEZ ANA", "", "", "", "", "", "", "", "",
         "", "", "", "", "", "", "", "", "", "", "", "", "",
         "", "", "", "", "", "", "", "", ""],
        ["3", "2024-07-20", "", "", "DESPACHO CANCILLER", "", "",
         "", "", "", "", "GOMEZ MARIA", "", "", "Ministro", "",
         doc1, "PEREZ CARLOS", "", "", "", "", "", "", "", "",
         "", "", "", "", "", "", "", "", "", "", "", "", "",
         "", "", "", "", "", "", "", "", ""],
    ])
    events_dir = tmp_path / "events"
    _write_events_shard(events_dir / "aa.json.gz", [
        {"entity_id": eid1, "entered_at": "2024-06-15T10:00:00Z",
         "exited_at": "2024-06-15T12:00:00Z", "destination": "RIVADAVIA 250",
         "canonical_name": "PEREZ CARLOS"},
        {"entity_id": eid2, "entered_at": "2024-06-15T10:00:00Z",
         "exited_at": "2024-06-15T12:00:00Z", "destination": "RIVADAVIA 250",
         "canonical_name": "LOPEZ ANA"},
    ])
    master = [
        {"entity_id": eid1, "nombre": "PEREZ, CARLOS", "document_number": doc1},
        {"entity_id": eid2, "nombre": "LOPEZ, ANA", "document_number": doc2},
    ]
    aud_rows = load_audiencias_rows(unificado)
    cr_events = load_cr_events(events_dir)
    confirmed = find_date_matches(aud_rows, cr_events, master)
    # Both PEREZ and LOPEZ matched on 2024-06-15
    assert len(confirmed) == 2
    patterns = extract_patterns(confirmed)
    # GOMEZ MARIA now has 2 confirmed matches (meets MIN_PATTERN_COUNT)
    assert sum(patterns.officials.get("GOMEZ MARIA", {}).values()) >= 2
    result = classify_audiencias(aud_rows, confirmed, patterns, master)

    # PEREZ: row 1 = confirmed, row 3 = likely (same official)
    perez_clfs = result.per_entity[eid1]
    assert len(perez_clfs) == 2
    statuses = {c.status for c in perez_clfs}
    assert "confirmed" in statuses
    assert "likely" in statuses


def test_classify_audiencias_unconfirmed(tmp_path: None) -> None:
    """Audiencia with no CR match and no pattern = unconfirmed."""
    doc = "22333444"
    eid = entity_id("PEREZ CARLOS", doc)
    unificado = tmp_path / "audiencias.csv"
    _write_audiencias_csv(unificado, [
        ["1", "2024-06-15", "", "", "PUERTO ENSENADA", "", "",
         "", "", "", "", "DESCONOCIDO RARO", "", "", "Cargo Raro", "",
         doc, "PEREZ CARLOS", "", "", "", "", "", "", "", "",
         "", "", "", "", "", "", "", "", "", "", "", "", "",
         "", "", "", "", "", "", "", "", ""],
    ])
    events_dir = tmp_path / "events"
    _write_events_shard(events_dir / "aa.json.gz", [])
    master = [{"entity_id": eid, "nombre": "PEREZ, CARLOS", "document_number": doc}]
    aud_rows = load_audiencias_rows(unificado)
    cr_events = load_cr_events(events_dir)
    confirmed = find_date_matches(aud_rows, cr_events, master)
    patterns = extract_patterns(confirmed)
    result = classify_audiencias(aud_rows, confirmed, patterns, master)

    classifications = result.per_entity[eid]
    assert len(classifications) == 1
    assert classifications[0].status == "unconfirmed"
    assert result.confirmed_count == 0
    assert result.likely_count == 0
    assert result.unconfirmed_count == 1


def test_cr_patterns_roundtrip() -> None:
    """CRPatterns survives a dict roundtrip."""
    patterns = CRPatterns(
        officials={"GOMEZ MARIA": {"RIVADAVIA 250": 5}},
        lugares={"DESPACHO CANCILLER": {"RIVADAVIA 250": 3}},
    )
    data = patterns.to_dict()
    restored = CRPatterns.from_dict(data)
    assert restored.officials == patterns.officials
    assert restored.lugares == patterns.lugares
