import csv
import json

import duckdb

from pipeline import enrich_audiencias
from pipeline.enrich_audiencias import (
    _dedup_ci,
    _is_noise_cargo,
    _match_by_name,
    consolidate,
    extract_rows,
)
from pipeline.normalize import entity_id

# Cabeceras en el mismo orden que recibe extract_rows (subset de 48 columnas).
FLAT_HEADER = [
    "id",
    "fecha",
    "sujeto_obligado_nombre",
    "sujeto_obligado_id",
    "sujeto_obligado_cargo",
    "sujeto_obligado_dependencia",
    "solicitante_nombre",
    "solicitante_id",
    "solicitante_ocupacion",
    "persona_representada_nombre",
    "persona_representada_id",
    "persona_representada_ocupacion",
    "persona_juridica_representada_nombre",
    "grupo_de_personas_representado_nombre",
    "organismo_estatal_representado_nombre",
    "participantes_json",
]


def _make_unificado(tmp_path):
    """Crea un CSV unificado pequeño con dos audiencias y devuelve su path."""
    rows = [
        [
            "1",
            "2024-03-01 09:00",
            "Lopez, Maria",
            "",
            "Directora",
            "Ministerio",
            "Ramirez, Jose",
            "12345678",
            "Consultor",
            "Carlos",
            "87654321",
            "Representante",
            "",
            "",
            "Agencia X",
            "[]",
        ],
        [
            "2",
            "2024-04-01 10:00",
            "Lopez, Maria",
            "",
            "Directora",
            "Ministerio",
            "Ramirez, Jose",
            "12345678",
            "Consultor",
            "",
            "",
            "",
            "Empresa SA",
            "",
            "",
            "[]",
        ],
    ]
    path = tmp_path / "audiencias_unificado.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(FLAT_HEADER)
        writer.writerows(rows)
    return path


def test_extract_rows_por_rol(tmp_path) -> None:
    path = _make_unificado(tmp_path)
    con = duckdb.connect()
    personas = extract_rows(con, path)
    # 2 audiencias x (sujeto + solicitante [+ representado en la primera])
    assert len(personas) == 5

    sujetos = [p for p in personas if p["rol"] == "sujeto_obligado"]
    assert len(sujetos) == 2
    assert all(p["cargo"] == "Directora" for p in sujetos)
    assert all(p["institucion"] == "Ministerio" for p in sujetos)
    assert all(p["tipo_institucion"] == "dependencia" for p in sujetos)

    solicitantes = [p for p in personas if p["rol"] == "solicitante"]
    assert len(solicitantes) == 2
    # Solicitante con DNI -> identidad por dni
    assert all(p["document_number"] == "12345678" for p in solicitantes)
    assert all(p["institucion"] == "Agencia X" for p in solicitantes[0:1])

    representados = [p for p in personas if p["rol"] == "persona_representada"]
    assert len(representados) == 1
    assert representados[0]["document_number"] == "87654321"


def test_extract_rows_entity_id_consistente(tmp_path) -> None:
    path = _make_unificado(tmp_path)
    con = duckdb.connect()
    personas = extract_rows(con, path)
    solicitante = next(p for p in personas if p["rol"] == "solicitante")
    # El entity_id debe ser idéntico al de la base principal para el mismo
    # nombre+documento (consistencia del cruce).
    expected = entity_id("Ramirez, Jose", "12345678")
    assert solicitante["entity_id"] == expected


def test_consolidate_uni_nombre_y_dedup() -> None:
    # Una misma persona aparece dos veces con cargos en distinto caso y con ruido.
    dni = "12345678"
    eid = entity_id("Ramirez, Jose", dni)
    personas = [
        {
            "entity_id": eid,
            "nombre": "Ramirez, Jose",
            "nombre_normalizado": "RAMIREZ JOSE",
            "document_type": "DNI",
            "document_number": dni,
            "rol": "solicitante",
            "cargo": "Consultor",
            "institucion": "Agencia",
            "tipo_institucion": "organismo_estatal",
        },
        {
            "entity_id": eid,
            "nombre": "Ramirez, Jose",
            "nombre_normalizado": "RAMIREZ JOSE",
            "document_type": "DNI",
            "document_number": dni,
            "rol": "solicitante",
            "cargo": "consultor",
            "institucion": "Agencia",
            "tipo_institucion": "organismo_estatal",
        },
        {
            "entity_id": eid,
            "nombre": "Ramirez, Jose",
            "nombre_normalizado": "RAMIREZ JOSE",
            "document_type": "DNI",
            "document_number": dni,
            "rol": "solicitante",
            "cargo": "------------",
            "institucion": "Agencia",
            "tipo_institucion": "organismo_estatal",
        },
    ]
    # base: la persona ya existe con su DNI.
    base = {dni: (eid, "Ramirez Jose")}
    master = consolidate(personas, base, name_threshold=96)
    assert len(master) == 1
    entry = master[0]
    assert entry["en_base"] is True
    assert entry["match_type"] == "dni"
    # dedup case-insensitive + ruido filtrado
    assert entry["cargos"] == ["Consultor"]
    assert entry["instituciones"]["organismo_estatal"] == ["Agencia"]


def test_consolidate_por_dni_adopta_entity_base() -> None:
    # El DNI ya existe en la base con otro entity_id (variante de nombre):
    # el cruce debe adoptar el entity_id de la base como canónico.
    dni = "12345678"
    eid_aud = entity_id("Ramirez, Jose", dni)
    eid_base = entity_id("Ramirez Jose", dni)
    personas = [
        {
            "entity_id": eid_aud,
            "nombre": "Ramirez, Jose",
            "nombre_normalizado": "RAMIREZ JOSE",
            "document_type": "DNI",
            "document_number": dni,
            "rol": "solicitante",
            "cargo": "Consultor",
            "institucion": None,
            "tipo_institucion": None,
        }
    ]
    base = {dni: (eid_base, "Ramirez Jose")}
    master = consolidate(personas, base, name_threshold=96)
    assert master[0]["entity_id"] == eid_base
    assert master[0]["match_type"] == "dni"


def test_match_by_name_exacto_no_falsos_positivos() -> None:
    bucket = {"SALGADO": ["SALGADO JUAN"], "RAMIREZ": ["RAMIREZ JUAN CARLOS"]}
    # coincidencia casi exacta
    assert _match_by_name("SALGADO JUAN", bucket, 96) == "SALGADO JUAN"
    # nombres con tokens extra NO deben matchear por debajo del umbral alto
    assert _match_by_name("SALGADO BROCAL JUAN CARLOS", bucket, 96) is None
    assert _match_by_name("RAMIREZ CARLOS", bucket, 96) is None
    # requiere dos tokens significativos
    assert _match_by_name("PEREZ", {"PEREZ": ["PEREZ EDUARDO"]}, 96) is None


def test_consolidate_por_nombre() -> None:
    # persona sin DNI que coincide casi exacto con un nombre en base
    nombre = "Del Rio, Carlos"
    personas = [
        {
            "entity_id": entity_id(nombre, None),
            "nombre": nombre,
            "nombre_normalizado": "DEL RIO CARLOS",
            "document_type": None,
            "document_number": None,
            "rol": "solicitante",
            "cargo": "Abogado",
            "institucion": "Agencia",
            "tipo_institucion": "organismo_estatal",
        }
    ]
    base = {"11111111": (entity_id("Del Rio Carlos", "11111111"), "Del Rio Carlos")}
    master = consolidate(personas, base, name_threshold=96)
    assert len(master) == 1
    assert master[0]["match_type"] == "nombre"
    assert master[0]["en_base"] is True
    # adoptó el entity_id de la base
    assert master[0]["entity_id"] == entity_id("Del Rio Carlos", "11111111")


def test_helpers() -> None:
    assert _is_noise_cargo("------------") is True
    assert _is_noise_cargo("Ministro") is False
    assert _dedup_ci(["Ministro", "ministro", "Ministro"]) == ["Ministro"]
    assert _dedup_ci(["------------"]) == []


def test_build_enrichment_genera_archivos(tmp_path) -> None:
    unificado = _make_unificado(tmp_path)
    personas_out = tmp_path / "audiencias_personas.csv"
    master_out = tmp_path / "audiencias_personas_master.json"
    state_out = tmp_path / "audiencias_personas_state.json"
    stats = enrich_audiencias.build_enrichment(
        unificado=unificado,
        personas_out=personas_out,
        master_out=master_out,
        state_out=state_out,
        base_doc_dir=tmp_path / "no_docs",  # no hay base de personas con documento
        name_threshold=96,
    )
    assert stats["filas_personas"] == 5
    assert stats["personas_unicas"] >= 3
    assert personas_out.exists()
    assert master_out.exists()
    master = json.loads(master_out.read_text(encoding="utf-8"))
    assert all("entity_id" in m for m in master)
    assert all("cargos" in m for m in master)
    assert all("instituciones" in m for m in master)


def _write_document_shard(dir, persons) -> None:
    """Escribe un shard de personas con documento en el formato de la base."""
    import gzip

    dir.mkdir(parents=True, exist_ok=True)
    path = dir / "00.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(persons, handle, ensure_ascii=False)


def test_build_audiencias_curation_genera_candidatos(tmp_path) -> None:
    import csv as _csv

    from pipeline.curation import CurationStore

    unificado = _make_unificado(tmp_path)
    # Base con "Del Rio Carlos" (con DNI). El solicitante "Ramirez, Jose" de las
    # audiencias NO coincide por nombre, así que no genera candidato.
    base_person = {
        "entity_id": entity_id("Del Rio Carlos", "11111111"),
        "canonical_name": "Del Rio Carlos",
        "document_type": "DNI",
        "document_number": "11111111",
        "record_count": 3,
        "locations": ["olivos"],
    }
    doc_dir = tmp_path / "docs"
    _write_document_shard(doc_dir, [base_person])

    candidates = tmp_path / "audiencias_candidates.csv"
    decisions = tmp_path / "audiencias_decisions.json"
    stats = enrich_audiencias.build_audiencias_curation(
        unificado=unificado,
        candidates_out=candidates,
        decisions_out=decisions,
        base_doc_dir=doc_dir,
        name_threshold=96,
    )
    assert candidates.exists()
    assert decisions.exists()
    with candidates.open(encoding="utf-8", newline="") as handle:
        rows = list(_csv.DictReader(handle))
    # "Ramirez, Jose" no matchea con nadie de la base por nombre: no hay candidato.
    assert rows == []
    assert stats["candidatos_por_nombre"] == 0

    # Cargable por la interfaz de curación existente.
    store = CurationStore(candidates, decisions)
    assert store.summary()["total"] == 0


def test_build_audiencias_curation_con_coincidencia_por_nombre(tmp_path) -> None:
    import csv as _csv

    from pipeline.curation import CurationStore

    # Un audiencia con "Del Rio, Carlos" sin documento, que coincide exacto por
    # nombre con la persona de la base.
    rows = [
        [
            "1", "2024-03-01 09:00",
            "", "", "", "",
            "Del Rio, Carlos", "", "Abogado",
            "", "", "",
            "", "", "Agencia X", "[]",
        ],
    ]
    unificado = tmp_path / "audiencias_unificado.csv"
    with unificado.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(FLAT_HEADER)
        writer.writerows(rows)

    base_eid = entity_id("Del Rio Carlos", "11111111")
    base_person = {
        "entity_id": base_eid,
        "canonical_name": "Del Rio Carlos",
        "document_type": "DNI",
        "document_number": "11111111",
        "record_count": 3,
        "locations": ["olivos"],
    }
    doc_dir = tmp_path / "docs"
    _write_document_shard(doc_dir, [base_person])

    candidates = tmp_path / "audiencias_candidates.csv"
    decisions = tmp_path / "audiencias_decisions.json"
    enrich_audiencias.build_audiencias_curation(
        unificado=unificado,
        candidates_out=candidates,
        decisions_out=decisions,
        base_doc_dir=doc_dir,
        name_threshold=96,
    )
    with candidates.open(encoding="utf-8", newline="") as handle:
        rows = list(_csv.DictReader(handle))
    assert len(rows) == 1
    row = rows[0]
    # left = identidad de audiencias (por nombre), right = identidad de la base (por DNI)
    assert entity_id("Del Rio, Carlos", None) == row["left_entity_id"]
    assert row["right_entity_id"] == base_eid
    assert row["right_document"] == "DNI:11111111"
    assert row["confidence"] == "review"

    # La interfaz de curación la carga y puede revisarse.
    store = CurationStore(candidates, decisions)
    assert store.summary()["total"] == 1
    assert store.summary()["review"] == 1
    listing = store.list_candidates(status="pending", limit=10)
    assert listing["total"] == 1
    assert listing["items"][0]["cargos"] == "Abogado"


def test_consolidate_respects_rejected_pairs(tmp_path) -> None:
    # "Del Rio, Carlos" sin DNI coincide por nombre con la base, pero la
    # fusión fue rechazada (distintas personas con nombre parecido).
    path = _make_unificado(tmp_path)
    con = duckdb.connect()
    personas = extract_rows(con, path)
    # La audiencias tiene "Ramirez, Jose" con DNI 12345678 (no name-match
    # problem), así que agrego una fila ficticia para Del Rio sin documento.
    basePath = _make_unificado(tmp_path)
    rows_extra = [
        [
            "3", "2024-05-01 11:00",
            "", "", "", "",
            "Del Rio, Carlos", "", "Abogado",
            "", "", "",
            "", "", "", "[]",
        ],
    ]
    with basePath.open("w", encoding="utf-8", newline="") as handle:
        w = csv.writer(handle, delimiter=";")
        w.writerow(FLAT_HEADER)
        w.writerows(rows_extra)
    personas2 = extract_rows(con, basePath)
    all_personas = personas + personas2

    base_dni = "11111111"
    base_eid = entity_id("Del Rio Carlos", base_dni)
    base = {base_dni: (base_eid, "Del Rio Carlos")}
    aud_eid_del_rio = entity_id("Del Rio, Carlos", None)

    # Sin rechazo: Del Rio se fusiona en la base.
    m_ok = consolidate(all_personas, base, name_threshold=96, rejected_pairs=None)
    merged_entry = next((e for e in m_ok if e["entity_id"] == base_eid), None)
    assert merged_entry is not None
    assert merged_entry["match_type"] == "nombre"

    # Con rechazo de la pareja (aud_eid, base_eid): Del Rio queda independiente.
    rejected = {frozenset((aud_eid_del_rio, base_eid))}
    m_rej = consolidate(all_personas, base, name_threshold=96, rejected_pairs=rejected)
    kept_entry = next((e for e in m_rej if e["entity_id"] == aud_eid_del_rio), None)
    assert kept_entry is not None
    assert kept_entry["en_base"] is False
    assert kept_entry["match_type"] is None
    assert kept_entry["nombre"] == "Del Rio, Carlos"
