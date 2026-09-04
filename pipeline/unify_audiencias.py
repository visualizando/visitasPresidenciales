"""Unifica y normaliza los CSV anuales de Audiencias de Gestión de Intereses.

Descarga previa: los archivos viven en data/raw/*.csv (encoding latin-1).
Existen dos esquemas a lo largo de los años:

- Formato viejo (2004-2016): columnas *_sujeto_obligado, *_solicitante,
  *_representado, fecha_hora_audiencia, id_audiencia, etc. (33 columnas).
- Formato nuevo (2016 bis y 2017-2025): fecha, sujeto_obligado_nombre,
  participantes_json, etc. (36 columnas).

Este script normaliza ambos a un esquema único (el del formato nuevo) y escribe
un CSV en UTF-8 con separador ';'. Las columnas del formato viejo que no tienen
equivalente moderno se conservan como columnas adicionales para no perder
información. La columnas que un esquema no posee quedan vacías.
"""

from __future__ import annotations

import argparse
import codecs
import json
import tempfile
from pathlib import Path

import duckdb

RAW_DIR = Path("data/raw")
OUTPUT = Path("data/audiencias_unificado.csv.gz")

# Columnas del esquema moderno (formato 2016 bis / 2017-2025)
NUEVAS_COLS = [
    "id", "fecha", "fecha_de_publicacion", "sintesis", "lugar", "lat", "lng",
    "motivo", "interes_invocado", "direccion",
    "sujeto_obligado_id", "sujeto_obligado_nombre", "sujeto_obligado_tipo_id",
    "sujeto_obligado_pais", "sujeto_obligado_cargo", "sujeto_obligado_dependencia",
    "solicitante_id", "solicitante_nombre", "solicitante_tipo_id",
    "solicitante_pais", "solicitante_ocupacion", "solicitante_presente",
    "persona_representada_id", "persona_representada_tipo_id",
    "persona_representada_nombre", "persona_representada_pais",
    "persona_representada_ocupacion",
    "persona_juridica_representada_nombre", "persona_juridica_representada_pais",
    "persona_juridica_representada_cuit",
    "grupo_de_personas_representado_nombre",
    "grupo_de_personas_representado_descripcion",
    "grupo_de_personas_representado_pais",
    "organismo_estatal_representado_nombre", "organismo_estatal_representado_pais",
    "participantes_json",
]

# Columnas del formato viejo sin equivalente moderno (se conservan)
EXTRA_COLS = [
    "id_audiencia", "fecha_solicitud_audiencia", "caracter_en_que_participa",
    "domicilio_representado", "estado_cancelada_audiencia", "estado_audiencia",
    "es_persona_juridica", "derivada_a_apellido", "derivada_a_nombre",
    "derivada_a_cargo", "created_at", "updated_at",
]


def _reencode_latin1_to_utf8(in_path: Path, out_dir: Path, chunk_size: int = 1 << 20) -> Path:
    out_path = out_dir / in_path.name
    with in_path.open("rb") as src, out_path.open("wb") as dst:
        reader = codecs.getreader("latin-1")(src)
        dst.write("\ufeff".encode("utf-8"))
        while True:
            chunk = reader.read(chunk_size)
            if not chunk:
                break
            dst.write(chunk.encode("utf-8"))
    return out_path


def _load_viejo(con: duckdb.DuckDBPyConnection, tmp: Path, name: str, table: str) -> None:
    """Normaliza un CSV del formato viejo (2004-2016) a las columnas unificadas."""
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE {table} AS
        SELECT
            id,
            NULL                       AS fecha_de_publicacion,
            sintesis_audiencia         AS sintesis,
            lugar_audiencia            AS lugar,
            NULL                       AS lat,
            NULL                       AS lng,
            objeto_audiencia           AS motivo,
            interes_invocado           AS interes_invocado,
            NULL                       AS direccion,
            NULL                       AS sujeto_obligado_id,
            trim(concat_ws(', ', apellido_sujeto_obligado, nombre_sujeto_obligado))
                                       AS sujeto_obligado_nombre,
            NULL                       AS sujeto_obligado_tipo_id,
            NULL                       AS sujeto_obligado_pais,
            cargo_sujeto_obligado      AS sujeto_obligado_cargo,
            dependencia_sujeto_obligado AS sujeto_obligado_dependencia,
            numero_documento_solicitante AS solicitante_id,
            trim(concat_ws(', ', apellido_solicitante, nombre_solicitante))
                                       AS solicitante_nombre,
            tipo_documento_solicitante AS solicitante_tipo_id,
            NULL                       AS solicitante_pais,
            cargo_solicitante          AS solicitante_ocupacion,
            NULL                       AS solicitante_presente,
            numero_documento_representadoo AS persona_representada_id,
            NULL                       AS persona_representada_tipo_id,
            trim(concat_ws(', ', apellido_descripcion_representado, nombre_representado))
                                       AS persona_representada_nombre,
            NULL                       AS persona_representada_pais,
            cargo_representado         AS persona_representada_ocupacion,
            NULL                       AS persona_juridica_representada_nombre,
            NULL                       AS persona_juridica_representada_pais,
            NULL                       AS persona_juridica_representada_cuit,
            NULL                       AS grupo_de_personas_representado_nombre,
            NULL                       AS grupo_de_personas_representado_descripcion,
            NULL                       AS grupo_de_personas_representado_pais,
            NULL                       AS organismo_estatal_representado_nombre,
            NULL                       AS organismo_estatal_representado_pais,
            participante_audiencia     AS participantes_json,
            -- columnas extra del formato viejo
            fecha_hora_audiencia       AS fecha,
            id_audiencia,
            fecha_solicitud_audiencia,
            caracter_en_que_participa,
            domicilio_representado,
            estado_cancelada_audiencia,
            estado_audiencia,
            es_persona_juridica,
            derivada_a_apellido,
            derivada_a_nombre,
            derivada_a_cargo,
            created_at,
            updated_at
        FROM read_csv('{tmp / name}', header=true, all_varchar=true, delim=';')
        """
    )


def _load_nuevo(con: duckdb.DuckDBPyConnection, tmp: Path, name: str, table: str) -> None:
    """Normaliza un CSV del formato nuevo (2016 bis, 2017-2025)."""
    null_extra = ", ".join(f"NULL AS \"{c}\"" for c in EXTRA_COLS)
    cols = ", ".join(f'"{c}"' for c in NUEVAS_COLS) + ", " + null_extra
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE {table} AS
        SELECT {cols}
        FROM read_csv('{tmp / name}', header=true, all_varchar=true, delim=';')
        """
    )


def _is_viejo(con: duckdb.DuckDBPyConnection, tmp: Path, name: str) -> bool:
    cols = con.execute(
        f"DESCRIBE SELECT * FROM read_csv('{tmp / name}', header=true, all_varchar=true, delim=';')"
    ).fetchall()
    col_names = {c[0] for c in cols}
    return "fecha_hora_audiencia" in col_names


def detect_format(path: Path) -> str:
    """Devuelve 'viejo' o 'nuevo' según el esquema de un CSV anual de audiencias."""
    with path.open("rb") as handle:
        raw = handle.read(4096)
    try:
        header = raw.decode("latin-1").splitlines()[0]
    except (IndexError, UnicodeDecodeError):
        raise ValueError(f"No se pudo leer el encabezado de {path}") from None
    columns = {column.strip() for column in header.split(";")}
    return "viejo" if "fecha_hora_audiencia" in columns else "nuevo"


def unify(raw_dir: Path, output: Path) -> dict[str, int]:
    """Normaliza todos los CSV anuales de `raw_dir` y escribe el CSV unificado.

    Devuelve un dict con las filas totales y el conteo por formato.
    """
    raw_dir = Path(raw_dir)
    output = Path(output)
    csv_files = sorted(raw_dir.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No se encontraron archivos CSV en {raw_dir}")

    counts = {"viejo": 0, "nuevo": 0}
    con = duckdb.connect()

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        tables: list[str] = []
        for i, csvf in enumerate(csv_files):
            utf8 = _reencode_latin1_to_utf8(csvf, tmp)
            table = f"t_{i}"
            if detect_format(csvf) == "viejo":
                _load_viejo(con, tmp, utf8.name, table)
                counts["viejo"] += _row_count(con, table)
            else:
                _load_nuevo(con, tmp, utf8.name, table)
                counts["nuevo"] += _row_count(con, table)
            tables.append(table)

        all_cols = NUEVAS_COLS + EXTRA_COLS
        # Unimos cada tabla seleccionando exactamente todas las columnas.
        combined = " UNION ALL ".join(
            "SELECT " + ", ".join(f'"{c}"' for c in all_cols) + f" FROM {t}" for t in tables
        )
        con.execute(f"CREATE OR REPLACE TABLE unificado AS {combined}")

        # DuckDB comprime automaticamente cuando el destino termina en .gz.
        con.execute(
            f"COPY unificado TO '{output}' (HEADER, DELIMITER ';', QUOTE '\"')"
        )

    counts["total"] = con.execute("SELECT count(*) FROM unificado").fetchone()[0]
    counts["columnas"] = len(NUEVAS_COLS) + len(EXTRA_COLS)
    return counts


def _row_count(con: duckdb.DuckDBPyConnection, table: str) -> int:
    return con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", default=str(RAW_DIR), help="Carpeta con los CSV anuales (latin-1).")
    parser.add_argument("--output", default=str(OUTPUT), help="CSV de salida.")
    args = parser.parse_args()
    result = unify(args.raw, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
