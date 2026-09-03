"""Extrae y cruza personas de las Audiencias de Gestión de Intereses.

Este módulo lee `data/audiencias_unificado.csv` (consolidado por el módulo de
audiencias) y extrae todas las personas identificadas en cada audiencia:

- sujeto_obligado (el funcionario que recibe la audiencia),
- solicitante (quien la solicita),
- persona_representada (individuo representado por el solicitante),
- y las entidades institucionales representadas (persona jurídica, grupo de
  personas u organismo estatal).

A cada persona se le asigna un `entity_id` consistente con la base principal
utilizando `normalize.entity_id(nombre, documento)`, de modo que el cruce con
las personas ya presentes (por DNI/CUIL o por nombre) es directo.

El resultado se publica en dos archivos:

- `data/audiencias_personas.csv` — una fila por (audiencia, rol, persona).
- `data/audiencias_personas_master.csv` — consolidación por `entity_id` con
  nombre canónico, documento, cargos, instituciones y el vínculo con la base
  existente (coincidencia por DNI o por nombre).

El enriquecimiento es un dataset aparte y no modifica el sitio web.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import duckdb
from rapidfuzz import fuzz

from pipeline.normalize import document_identity, entity_id, fold_text, normalize_document
from pipeline.storage import utc_now, write_json_atomic

RAW_UNIFICADO = Path("data/audiencias_unificado.csv")
OUTPUT_PERSONAS = Path("data/audiencias_personas.csv")
OUTPUT_MASTER = Path("data/audiencias_personas_master.json")
OUTPUT_STATE = Path("data/audiencias_personas_state.json")
SEARCH_DOC_DIR = Path("web/public/data/search/document")
SEARCH_NAME_DIR = Path("web/public/data/search/name")
AUDIENCIAS_CANDIDATES = Path("data/curation/audiencias_candidates.csv")
AUDIENCIAS_DECISIONS = Path("data/curation/audiencias_decisions.json")

ROLES = ("sujeto_obligado", "solicitante", "persona_representada")


def _clean(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if not value or value.upper() in {"[NULL]", "NULL", "N/A"}:
        return None
    return value


def _parse_participants_json(value: str | None) -> list[dict[str, str]]:
    """Intenta parsear `participantes_json` con sus participantes adicionales."""
    value = _clean(value)
    if not value:
        return []
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    participants = []
    for item in data:
        if not isinstance(item, dict):
            continue
        nombre = _clean(str(item.get("Nombre") or item.get("nombre") or ""))
        if not nombre:
            continue
        participants.append(
            {
                "nombre": nombre,
                "documento": _clean(str(item.get("id") or item.get("documento") or "")),
                "ocupacion": _clean(str(item.get("Ocupación") or item.get("Ocupacion") or "")),
            }
        )
    return participants


def _persona(nombre: str | None, documento: str | None, rol: str) -> dict[str, Any]:
    """Construye la representación normalizada de una persona de audiencias."""
    nombre = _clean(nombre)
    documento = _clean(documento)
    doc_type: str | None = None
    doc_number: str | None = None
    if documento:
        digits = normalize_document(documento)
        if digits:
            doc_type, doc_number, _ = document_identity(digits)
    eid = entity_id(nombre or "", doc_number)
    return {
        "entity_id": eid,
        "nombre": nombre or "",
        "nombre_normalizado": fold_text(nombre or ""),
        "document_type": doc_type,
        "document_number": doc_number,
        "rol": rol,
    }


def extract_rows(
    con: duckdb.DuckDBPyConnection, unificado: Path = RAW_UNIFICADO
) -> list[dict[str, Any]]:
    """Extrae todas las (audiencia, rol, persona) desde el CSV unificado."""
    rows = con.execute(
        """
        SELECT
            id, fecha,
            sujeto_obligado_nombre, sujeto_obligado_id, sujeto_obligado_cargo,
            sujeto_obligado_dependencia,
            solicitante_nombre, solicitante_id, solicitante_ocupacion,
            persona_representada_nombre, persona_representada_id, persona_representada_ocupacion,
            persona_juridica_representada_nombre,
            grupo_de_personas_representado_nombre,
            organismo_estatal_representado_nombre,
            participantes_json
        FROM read_csv(?, header=true, all_varchar=true)
        """,
        [str(unificado)],
    ).fetchall()
    cols = [
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
    out: list[dict[str, Any]] = []
    for r in rows:
        rec = dict(zip(cols, r, strict=True))

        # Sujeto obligado (funcionario) -> institución = dependencia
        if _clean(rec["sujeto_obligado_nombre"]):
            p = _persona(
                rec["sujeto_obligado_nombre"], rec["sujeto_obligado_id"], "sujeto_obligado"
            )
            p["cargo"] = _clean(rec["sujeto_obligado_cargo"])
            p["institucion"] = _clean(rec["sujeto_obligado_dependencia"])
            p["tipo_institucion"] = "dependencia"
            p["fecha"] = rec["fecha"]
            out.append(p)

        # Solicitante -> institución = entidad representada en la misma fila
        if _clean(rec["solicitante_nombre"]):
            p = _persona(rec["solicitante_nombre"], rec["solicitante_id"], "solicitante")
            p["cargo"] = _clean(rec["solicitante_ocupacion"])
            p["institucion"], p["tipo_institucion"] = _institucion_representada(rec)
            p["fecha"] = rec["fecha"]
            out.append(p)

        # Persona representada (física)
        if _clean(rec["persona_representada_nombre"]):
            p = _persona(
                rec["persona_representada_nombre"],
                rec["persona_representada_id"],
                "persona_representada",
            )
            p["cargo"] = _clean(rec["persona_representada_ocupacion"])
            p["institucion"], p["tipo_institucion"] = _institucion_representada(rec)
            p["fecha"] = rec["fecha"]
            out.append(p)

        # Participantes adicionales del json (complementan los roles)
        for part in _parse_participants_json(rec["participantes_json"]):
            p = _persona(part["nombre"], part["documento"], "participante")
            p["cargo"] = part["ocupacion"]
            p["institucion"] = _institucion_representada(rec)[0]
            p["tipo_institucion"] = _institucion_representada(rec)[1]
            p["fecha"] = rec["fecha"]
            out.append(p)

    return out


def _institucion_representada(rec: dict[str, Any]) -> tuple[str | None, str | None]:
    """Institución representada por solicitante/representado en una fila."""
    for campo, tipo in (
        ("persona_juridica_representada_nombre", "persona_juridica"),
        ("organismo_estatal_representado_nombre", "organismo_estatal"),
        ("grupo_de_personas_representado_nombre", "grupo"),
    ):
        valor = _clean(rec[campo])
        if valor:
            return valor, tipo
    return None, None


def load_base_personas(con: duckdb.DuckDBPyConnection, doc_dir: Path) -> dict[str, tuple[str, str]]:
    """Carga las personas con documento de la base: {dni: (entity_id, canonical_name)}."""
    if not doc_dir.exists():
        return {}
    rows = con.execute(
        """
        SELECT DISTINCT document_number AS dni, first(entity_id) AS eid,
               first(canonical_name) AS nombre
        FROM read_json_auto(?, format='array', union_by_name=true, ignore_errors=true)
        WHERE document_number IS NOT NULL AND document_number != ''
        GROUP BY document_number
        """,
        [str(doc_dir / "*.json.gz")],
    ).fetchall()
    return {str(r[0]): (str(r[1]), str(r[2]) or "") for r in rows}


def load_base_people(con: duckdb.DuckDBPyConnection, doc_dir: Path) -> list[dict[str, Any]]:
    """Carga los registros completos de personas con documento de la base."""
    if not doc_dir.exists():
        return []
    cur = con.execute(
        """
        SELECT * FROM read_json_auto(?, format='array', union_by_name=true, ignore_errors=true)
        WHERE document_number IS NOT NULL AND document_number != ''
        """,
        [str(doc_dir / "*.json.gz")],
    )
    cols = [description[0] for description in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


_curation_fieldnames = [
    "candidate_id",
    "confidence",
    "score",
    "reasons",
    "left_entity_id",
    "left_name",
    "left_document",
    "left_records",
    "left_locations",
    "right_entity_id",
    "right_name",
    "right_document",
    "right_records",
    "right_locations",
    "cargos",
    "instituciones",
]


def build_audiencias_curation(
    unificado: Path = RAW_UNIFICADO,
    candidates_out: Path = AUDIENCIAS_CANDIDATES,
    decisions_out: Path = AUDIENCIAS_DECISIONS,
    base_doc_dir: Path = SEARCH_DOC_DIR,
    name_threshold: int = 96,
) -> dict[str, Any]:
    """Genera candidatos de curación para el cruce audiencias ↔ base.

    Cada candidato representa una identidad de audiencias que por *nombre casi
    exacto* (sin documento en la base) se propone fusionar con una identidad ya
    existente en la base. Los cruces por DNI ya comparten `entity_id` (no hay
    fusión que decidir), por lo que no generan candidato; son ciertos por
    construcción.

    El archivo resultante usa el mismo esquema que `curate-identities`, de modo
    que puede revisarse con::

        uv run accesos curate-identities --candidates data/curation/audiencias_candidates.csv \\
            --decisions data/curation/audiencias_decisions.json
    """
    import csv as _csv

    con = duckdb.connect()
    personas = extract_rows(con, unificado)
    base = load_base_personas(con, base_doc_dir)
    master = consolidate(personas, base, name_threshold=name_threshold)
    base_by_entity = {person["entity_id"]: person for person in load_base_people(con, base_doc_dir)}

    rows: list[dict[str, Any]] = []
    for entry in master:
        # Solo hay una fusión que decidir cuando la consolidación reasignó la
        # identidad hacia la de la base (coincidencia por nombre o variante).
        if entry["match_type"] != "nombre":
            continue
        left_eid = entry["eid_original"]
        right_eid = entry["entity_id"]
        if left_eid == right_eid:
            continue
        right = base_by_entity.get(right_eid)
        if right is None:
            continue
        score = int(
            fuzz.ratio(fold_text(entry["nombre"]), fold_text(entry.get("base_nombre") or ""))
        )
        rows.append(
            {
                "candidate_id": "aud_" + hashlib.sha256(
                    "\x1f".join(sorted((left_eid, right_eid))).encode("utf-8")
                ).hexdigest()[:20],
                "confidence": "review",
                "score": score,
                "reasons": "nombre_casi_exacto|audiencias",
                "left_entity_id": left_eid,
                "left_name": entry["nombre"],
                "left_document": _document_field(
                    entry.get("document_type") or "", entry.get("document_number")
                ),
                "left_records": _audiencia_row_count(personas, left_eid),
                "left_locations": "audiencias",
                "right_entity_id": right_eid,
                "right_name": right.get("canonical_name") or "",
                "right_document": _base_document_field(right),
                "right_records": int(right.get("record_count") or 0),
                "right_locations": "|".join(right.get("locations") or []),
                "cargos": "|".join(entry["cargos"][:8]),
                "instituciones": "|".join(
                    institution
                    for group in entry["instituciones"].values()
                    for institution in group[:3]
                )[:400],
            }
        )

    rows.sort(key=lambda item: (-item["score"], item["left_name"], item["right_name"]))
    candidates_out.parent.mkdir(parents=True, exist_ok=True)
    with candidates_out.open("w", encoding="utf-8", newline="") as handle:
        writer = _csv.DictWriter(handle, fieldnames=_curation_fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    if not decisions_out.exists():
        write_json_atomic(decisions_out, {"version": 3, "merges": [], "rejections": [], "deferred": [], "batches": []})

    stats = {
        "candidatos_por_nombre": len(rows),
        "con_cargo": sum(1 for row in rows if row["cargos"]),
        "con_institucion": sum(1 for row in rows if row["instituciones"]),
    }
    return stats


def apply_audiencias_decisions(
    candidates_out: Path = AUDIENCIAS_CANDIDATES,
    decisions_out: Path = AUDIENCIAS_DECISIONS,
    *,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Aplica automáticamente las decisiones del cruce audiencias ↔ base.

    Regla automática (discriminante según la presencia de documento en cada
    lado del candidato):

    - Si los dos lados tienen documento **distinto**: se trata de dos personas
      distintas que sólo coinciden en el nombre → **reject** automático.
    - Si sólo la base tiene documento y la audiencias no tiene documento: es la
      misma persona (variante de nombre sin documento) → **merge** automático,
      conservando la identidad de la base (con su documento).
    - Si ningún lado tiene documento: queda **pendiente** para revisión manual.

    Sólo escribe las decisiones si `confirmed=True`; en otro caso devuelve la
    previsualización sin tocar el archivo.
    """
    from pipeline.curation import CurationStore

    if not candidates_out.is_file():
        raise FileNotFoundError(f"No existen candidatos: {candidates_out}")

    store = CurationStore(candidates_out, decisions_out)
    pending = _all_pending(store)
    plan = {"merge": 0, "reject": 0, "pendiente": 0}
    for candidate in pending:
        left_doc = candidate.get("left_document") or ""
        right_doc = candidate.get("right_document") or ""
        if left_doc and right_doc:
            plan["reject"] += 1
        elif right_doc:  # solo la base tiene documento
            plan["merge"] += 1
        else:
            plan["pendiente"] += 1

    if not confirmed:
        return {**plan, "confirmacion": False}

    for candidate in pending:
        left_doc = candidate.get("left_document") or ""
        right_doc = candidate.get("right_document") or ""
        candidate_id = candidate["candidate_id"]
        if left_doc and right_doc:
            store.decide(candidate_id, "reject", note="Automático: documentos distintos")
        elif right_doc:
            store.decide(
                candidate_id,
                "merge",
                canonical_entity_id=candidate["right_entity_id"],
                confirmed=True,
                note="Automático: coincidencia por nombre sin documento en audiencias",
            )
    return {**plan, "confirmacion": True}


def _all_pending(store) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    offset = 0
    while True:
        batch = store.list_candidates(status="pending", offset=offset, limit=100)["items"]
        if not batch:
            break
        items.extend(batch)
        offset += len(batch)
    return items


def _audiencia_row_count(personas: list[dict[str, Any]], eid: str) -> int:
    return sum(1 for persona in personas if persona["entity_id"] == eid)


def _base_document_field(person: dict[str, Any]) -> str:
    return _document_field(person.get("document_type") or "", person.get("document_number"))


def _document_field(doc_type: str, number: str | None) -> str:
    return f"{doc_type}:{number}" if number else ""


def load_rejected_pairs(decisions_path: Path) -> set[frozenset[str]]:
    """Carga las parejas rechazadas desde un archivo de decisiones v3."""
    if not decisions_path.is_file():
        return set()
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    pairs: set[frozenset[str]] = set()
    for item in decisions.get("rejections", []):
        left = item.get("left") or item.get("from")
        right = item.get("right") or item.get("into")
        if left and right:
            pairs.add(frozenset((left, right)))
    return pairs


def _is_noise_cargo(value: str) -> bool:
    stripped = re.sub(r"[\W_]+", "", value.strip()).lower()
    if not stripped:
        return True
    return stripped in {"sin datos", "sindato", "s/d", "sd", "na", "n/a"}


def _dedup_ci(values) -> list[str]:
    """Dedup case-insensitivo conservando el primer formato (más común) visto."""
    seen: dict[str, str] = {}
    counts: dict[str, int] = {}
    for value in values:
        if not _is_noise_cargo(value):
            key = fold_text(value)
            counts[key] = counts.get(key, 0) + 1
            if key not in seen:
                seen[key] = value
    return [seen[k] for k in sorted(seen, key=lambda k: (-counts[k], k.lower()))]


def consolidate(
    personas: list[dict[str, Any]],
    base: dict[str, tuple[str, str]],
    name_threshold: int = 96,
    rejected_pairs: set[frozenset[str]] | None = None,
) -> list[dict[str, Any]]:
    """Consolida las personas por `entity_id` y las vincula con la base.

    - Si la persona tiene DNI y ese DNI está en la base de personas con
      documento, se considera coincidencia directa por documento.
    - Si no hay DNI, se intenta una coincidencia por nombre normalizado contra
      un conjunto de nombres de referencia de la base (con puntaje de
      similitud por encima de `name_threshold`).
    - Las parejas en `rejected_pairs` no se fusionan aunque el nombre coincida.
    - Para cada `entity_id` se agregan cargos e instituciones distintos.
    """
    base_entities: dict[str, tuple[str, str]] = {}
    for _dni, (eid, nombre) in base.items():
        if nombre:
            base_entities.setdefault(fold_text(nombre), (eid, nombre))

    base_names = list(base_entities.keys())
    # Agrupar nombres de base por primer token para acotar la búsqueda por nombre.
    base_by_first_token: dict[str, list[str]] = {}
    for name in base_names:
        tokens = [t for t in name.split() if t]
        if tokens:
            base_by_first_token.setdefault(tokens[0], []).append(name)

    # Primera pasada: persona -> entity id + detección de coincidencia.
    personas_ids: dict[str, list[dict[str, Any]]] = {}
    for persona in personas:
        eid = persona["entity_id"]
        personas_ids.setdefault(eid, []).append(persona)

    master: dict[str, dict[str, Any]] = {}
    for eid, records in personas_ids.items():
        eid_original = eid
        # Nombre "más completo" (mayor cantidad de tokens).
        nombre_completo = max((r["nombre"] for r in records), key=lambda n: n.count(" "))
        doc_number = next((r["document_number"] for r in records if r["document_number"]), None)
        doc_type = next((r["document_type"] for r in records if r["document_type"]), None)

        en_base = False
        match_type: str | None = None
        base_name = None
        # Coincidencia por documento.
        if doc_number and doc_number in base:
            en_base = True
            match_type = "dni"
            base_eid, base_name = base[doc_number]
            if base_eid != eid:
                # El DNI existe en la base con otro entity_id (variante de
                # nombre): adoptamos el entity_id de la base como canónico.
                eid = base_eid
        # Coincidencia por nombre (solo si no hay documento o no se cruzó por DNI).
        if not en_base:
            nombre_norm = fold_text(nombre_completo)
            matched_name = _match_by_name(nombre_norm, base_by_first_token, name_threshold)
            if matched_name is not None and matched_name in base_entities:
                target_eid, base_name = base_entities[matched_name]
                pair = frozenset((eid_original, target_eid))
                if rejected_pairs is None or pair not in rejected_pairs:
                    en_base = True
                    match_type = "nombre"
                    eid = target_eid

        cargos = _dedup_ci(r["cargo"] for r in records if r.get("cargo"))
        instituciones: dict[str, list[str]] = {}
        for r in records:
            if r.get("institucion"):
                instituciones.setdefault(r["tipo_institucion"] or "otra", [])
                instituciones[r["tipo_institucion"] or "otra"] = _dedup_ci(
                    instituciones[r["tipo_institucion"] or "otra"] + [r["institucion"]]
                )
        roles = sorted({r["rol"] for r in records})

        master[eid] = {
            "entity_id": eid,
            "eid_original": eid_original,
            "nombre": nombre_completo,
            "nombre_normalizado": fold_text(nombre_completo),
            "document_type": doc_type,
            "document_number": doc_number,
            "en_base": en_base,
            "match_type": match_type,
            "base_nombre": base_name,
            "cargos": cargos,
            "instituciones": instituciones,
            "roles": roles,
            "aporte_audiencia": {"cargos": len(cargos) > 0, "instituciones": any(instituciones)},
        }

    return list(master.values())


def _match_by_name(
    nombre_norm: str,
    base_by_first_token: dict[str, list[str]],
    threshold: int,
) -> str | None:
    """Devuelve un nombre de base solo si la similitud es prácticamente exacta.

    Usa `fuzz.ratio` (sensibilidad a la cantidad de tokens/caracteres, no al
    subconjunto) con un umbral alto para evitar falsos positivos, y exige que
    el nombre de la audiencia tenga al menos dos tokens significativos.
    """
    if not nombre_norm:
        return None
    tokens = [t for t in nombre_norm.split() if t]
    if len(tokens) < 2:
        return None
    candidates = base_by_first_token.get(tokens[0], [])
    best = (0, None)
    for candidate in candidates:
        score = fuzz.ratio(nombre_norm, candidate)
        if score > best[0]:
            best = (score, candidate)
    if best[0] >= threshold:
        return best[1]
    return None


def build_enrichment(
    unificado: Path = RAW_UNIFICADO,
    personas_out: Path = OUTPUT_PERSONAS,
    master_out: Path = OUTPUT_MASTER,
    state_out: Path = OUTPUT_STATE,
    base_doc_dir: Path = SEARCH_DOC_DIR,
    name_threshold: int = 96,
    decisions_path: Path | None = None,
) -> dict[str, Any]:
    con = duckdb.connect()
    personas = extract_rows(con, unificado)
    base = load_base_personas(con, base_doc_dir)
    rejected_pairs = load_rejected_pairs(decisions_path) if decisions_path else None
    master = consolidate(personas, base, name_threshold=name_threshold, rejected_pairs=rejected_pairs)

    # CSV de filas persona por audiencia (aplanado).
    flat_rows = []
    for p in personas:
        flat_rows.append(
            {
                "entity_id": p["entity_id"],
                "nombre": p["nombre"],
                "document_type": p["document_type"],
                "document_number": p["document_number"],
                "rol": p["rol"],
                "cargo": p.get("cargo"),
                "institucion": p.get("institucion"),
                "tipo_institucion": p.get("tipo_institucion"),
                "fecha": p.get("fecha"),
            }
        )
    _write_flat_csv(con, flat_rows, personas_out)
    _write_master_json(con, master, master_out)

    stats = {
        "filas_personas": len(flat_rows),
        "personas_unicas": len(master),
        "en_base_por_dni": sum(1 for m in master if m["match_type"] == "dni"),
        "en_base_por_nombre": sum(1 for m in master if m["match_type"] == "nombre"),
        "nuevas": sum(1 for m in master if not m["en_base"]),
        "con_cargo": sum(1 for m in master if m["cargos"]),
        "con_institucion": sum(1 for m in master if any(m["instituciones"])),
    }
    write_json_atomic(
        state_out,
        {"version": 1, **stats, "generated_at": utc_now()},
    )
    return stats


def _write_flat_csv(con: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]], path: Path) -> None:
    import csv as _csv

    path.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "entity_id",
        "nombre",
        "document_type",
        "document_number",
        "rol",
        "cargo",
        "institucion",
        "tipo_institucion",
        "fecha",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = _csv.DictWriter(handle, fieldnames=cols, delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_master_json(
    con: duckdb.DuckDBPyConnection, master: list[dict[str, Any]], path: Path
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(master, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unificado", type=Path, default=RAW_UNIFICADO)
    parser.add_argument("--personas-out", type=Path, default=OUTPUT_PERSONAS)
    parser.add_argument("--master-out", type=Path, default=OUTPUT_MASTER)
    parser.add_argument("--base-doc-dir", type=Path, default=SEARCH_DOC_DIR)
    parser.add_argument("--name-threshold", type=int, default=96)
    args = parser.parse_args()
    stats = build_enrichment(
        unificado=args.unificado,
        personas_out=args.personas_out,
        master_out=args.master_out,
        base_doc_dir=args.base_doc_dir,
        name_threshold=args.name_threshold,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
