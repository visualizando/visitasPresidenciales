import httpx

from pipeline import audiencias, unify_audiencias


def client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_parse_download_url() -> None:
    result = audiencias._parse_download_url(
        "http://datos.mininterior.gob.ar/dataset/abc/resource/uuid/download/audiencias-2005.csv"
    )
    assert result is not None
    assert (result["year"], result["name"], result["is_bis"]) == (
        2005,
        "audiencias-2005.csv",
        False,
    )
    assert result["url"].endswith("audiencias-2005.csv")

    result = audiencias._parse_download_url(
        "http://x/dataset/a/resource/uuid/download/2017.csv"
    )
    assert result is not None
    assert (result["year"], result["name"]) == (2017, "audiencias-2017.csv")

    result = audiencias._parse_download_url(
        "http://x/dataset/a/resource/uuid/download/audiencias-2016-bis-sistema-nuevo.csv"
    )
    assert result is not None
    assert (result["year"], result["is_bis"], result["name"]) == (
        2016,
        True,
        "audiencias-2016-bis.csv",
    )

    # El archivo de 2004 usa el nombre audiencias-2004b.csv
    result = audiencias._parse_download_url(
        "http://x/dataset/a/resource/uuid/download/audiencias-2004b.csv"
    )
    assert result is not None
    assert (result["year"], result["name"], result["is_bis"]) == (
        2004,
        "audiencias-2004.csv",
        False,
    )

    assert audiencias._parse_download_url("http://x/no-csv-here.pdf") is None
    assert audiencias._parse_download_url("http://x/archivo-sin-anio.csv") is None


def test_discover_audiencias(monkeypatch) -> None:
    html = """
    <html><body>
      <h1>Dataset</h1>
      <li>
        <a href="/dataset/abc/resource/1/audiencias-gestion">Audiencias Año 2005 CSV</a>
        <a href="http://datos.mininterior.gob.ar/dataset/x/resource/u1/download/audiencias-2005.csv">Ir al recurso</a>
      </li>
      <li>
        <a href="http://datos.mininterior.gob.ar/dataset/x/resource/u2/download/audiencias-2016-bis-sistema-nuevo.csv">Ir al recurso</a>
      </li>
      <li>
        <a href="http://datos.mininterior.gob.ar/dataset/x/resource/u3/download/2024.csv">Ir al recurso</a>
      </li>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    monkeypatch.setattr(audiencias, "_client", lambda: client_for(handler))
    resources = audiencias.discover_audiencias()
    assert [(r["year"], r["name"]) for r in resources] == [
        (2005, "audiencias-2005.csv"),
        (2016, "audiencias-2016-bis.csv"),
        (2024, "audiencias-2024.csv"),
    ]


NUEVO_HEADER = [
    "id", "fecha", "fecha_de_publicacion", "sintesis", "lugar", "lat",
    "lng", "motivo", "interes_invocado", "direccion", "sujeto_obligado_id",
    "sujeto_obligado_nombre", "sujeto_obligado_tipo_id", "sujeto_obligado_pais",
    "sujeto_obligado_cargo", "sujeto_obligado_dependencia", "solicitante_id",
    "solicitante_nombre", "solicitante_tipo_id", "solicitante_pais",
    "solicitante_ocupacion", "solicitante_presente", "persona_representada_id",
    "persona_representada_tipo_id", "persona_representada_nombre",
    "persona_representada_pais", "persona_representada_ocupacion",
    "persona_juridica_representada_nombre", "persona_juridica_representada_pais",
    "persona_juridica_representada_cuit", "grupo_de_personas_representado_nombre",
    "grupo_de_personas_representado_descripcion",
    "grupo_de_personas_representado_pais",
    "organismo_estatal_representado_nombre", "organismo_estatal_representado_pais",
    "participantes_json",
]


VIEJO_HEADER = [
    "id", "id_audiencia", "apellido_sujeto_obligado", "nombre_sujeto_obligado",
    "cargo_sujeto_obligado", "dependencia_sujeto_obligado", "super_dependencia",
    "fecha_solicitud_audiencia", "apellido_solicitante", "nombre_solicitante",
    "cargo_solicitante", "tipo_documento_solicitante", "numero_documento_solicitante",
    "interes_invocado", "caracter_en_que_participa",
    "apellido_descripcion_representado", "nombre_representado",
    "cargo_representado", "domicilio_representado",
    "numero_documento_representadoo", "fecha_hora_audiencia", "lugar_audiencia",
    "objeto_audiencia", "participante_audiencia", "estado_cancelada_audiencia",
    "estado_audiencia", "sintesis_audiencia", "created_at", "updated_at",
    "es_persona_juridica", "derivada_a_apellido", "derivada_a_nombre",
    "derivada_a_cargo",
]


def _write_csv(path, header, rows, encoding="latin-1") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [";".join(header)] + [";".join(row) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding=encoding)


def test_unify_combina_esquemas(tmp_path) -> None:
    raw = tmp_path / "raw"
    # Formato viejo
    viejo_row = {
        "id": "1", "id_audiencia": "100", "apellido_sujeto_obligado": "Perez",
        "nombre_sujeto_obligado": "Juan", "cargo_sujeto_obligado": "Ministro",
        "dependencia_sujeto_obligado": "Min", "super_dependencia": "MN",
        "fecha_solicitud_audiencia": "2010-01-01", "apellido_solicitante": "Garcia",
        "nombre_solicitante": "Ana", "cargo_solicitante": "Abogada",
        "tipo_documento_solicitante": "DNI", "numero_documento_solicitante": "123",
        "interes_invocado": "Colectivo", "caracter_en_que_participa": "Rep",
        "apellido_descripcion_representado": "Empresa", "nombre_representado": "Rep",
        "cargo_representado": "Dir", "domicilio_representado": "Dir",
        "numero_documento_representadoo": "99", "fecha_hora_audiencia": "2010-03-01 10:00",
        "lugar_audiencia": "Casa", "objeto_audiencia": "objeto",
        "participante_audiencia": "Juan Perez", "estado_cancelada_audiencia": "",
        "estado_audiencia": "Realizada", "sintesis_audiencia": "sintesis",
        "created_at": "t1", "updated_at": "t2", "es_persona_juridica": "1",
        "derivada_a_apellido": "", "derivada_a_nombre": "", "derivada_a_cargo": "",
    }
    _write_csv(raw / "audiencias-2010.csv", VIEJO_HEADER, [
        [viejo_row[column] for column in VIEJO_HEADER]
    ])
    # Formato nuevo
    nuevo_row = {
        "id": "2", "fecha": "2020-05-01 09:00", "fecha_de_publicacion": "2020-06-01",
        "sintesis": "sintesis nueva", "lugar": "lugar nuevo", "lat": "0", "lng": "0",
        "motivo": "motivo", "interes_invocado": "Colectivo", "direccion": "dir",
        "sujeto_obligado_id": "11", "sujeto_obligado_nombre": "Lopez, Maria",
        "sujeto_obligado_tipo_id": "dni", "sujeto_obligado_pais": "Argentina",
        "sujeto_obligado_cargo": "Directora", "sujeto_obligado_dependencia": "Dep",
        "solicitante_id": "55", "solicitante_nombre": "Ramirez, Jose",
        "solicitante_tipo_id": "dni", "solicitante_pais": "Argentina",
        "solicitante_ocupacion": "Consultor", "solicitante_presente": "Si",
        "persona_representada_id": "66", "persona_representada_tipo_id": "dni",
        "persona_representada_nombre": "Carlos", "persona_representada_pais": "Argentina",
        "persona_representada_ocupacion": "Rep",
        "persona_juridica_representada_nombre": "Empresa SA",
        "persona_juridica_representada_pais": "Argentina",
        "persona_juridica_representada_cuit": "30500000000",
        "grupo_de_personas_representado_nombre": "Grupo",
        "grupo_de_personas_representado_descripcion": "desc",
        "grupo_de_personas_representado_pais": "Argentina",
        "organismo_estatal_representado_nombre": "Org",
        "organismo_estatal_representado_pais": "Argentina",
        "participantes_json": "[]",
    }
    _write_csv(
        raw / "audiencias-2020.csv",
        NUEVO_HEADER,
        [[nuevo_row[column] for column in NUEVO_HEADER]],
    )

    output = tmp_path / "unificado.csv"
    result = unify_audiencias.unify(raw, output)
    assert result["total"] == 2

    import duckdb

    con = duckdb.connect()
    rows = con.execute(
        f"SELECT id, sujeto_obligado_nombre, sujeto_obligado_cargo, "
        f"id_audiencia, es_persona_juridica FROM read_csv('{output}', header=true) "
        f"ORDER BY id"
    ).fetchall()
    col_count = len(
        con.execute(f"DESCRIBE SELECT * FROM read_csv('{output}', header=true)").fetchall()
    )
    # 36 modernas + 12 extra
    assert col_count == 48
    # Formato viejo normalizado
    assert rows[0] == (1, "Perez, Juan", "Ministro", 100, 1)
    # Formato nuevo conserva sus valores y las columnas extra quedan vacías
    assert rows[1][:3] == (2, "Lopez, Maria", "Directora")
    assert rows[1][3] is None
    assert rows[1][4] is None


def test_detect_format(tmp_path) -> None:
    viejo = tmp_path / "viejo.csv"
    viejo.write_text(
        "id;id_audiencia;apellido_sujeto_obligado;fecha_hora_audiencia;resto\n1;2;X;3;4\n",
        encoding="latin-1",
    )
    nuevo = tmp_path / "nuevo.csv"
    nuevo.write_text(
        "id;fecha;sujeto_obligado_nombre;participantes_json\n1;2020-01-01;X;[]\n",
        encoding="latin-1",
    )
    assert unify_audiencias.detect_format(viejo) == "viejo"
    assert unify_audiencias.detect_format(nuevo) == "nuevo"


def test_download_audiencia_reencoded_to_utf8(monkeypatch, tmp_path) -> None:
    latin_text = "audiencias;fecha\n1;2020-01-01;Mart\u00edn Siracusa\n"  # latin-1 with accents
    payload = latin_text.encode("latin-1")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)

    monkeypatch.setattr(audiencias, "_client", lambda: client_for(handler))
    target = tmp_path / "audiencias-2024.csv"
    sha = audiencias.download_audiencia("http://x/download/2024.csv", target)
    assert target.read_bytes().startswith(b"audiencias;")
    assert sha  # sha256 computado
    assert len(sha) == 64


def test_update_audiencias_incremental(monkeypatch, tmp_path) -> None:
    resources = [
        {"year": 2024, "name": "audiencias-2024.csv",
         "url": "http://x/download/2024.csv", "is_bis": False},
    ]
    # Contenido latin-1 de una sola fila (formato nuevo)
    row = {column: "" for column in NUEVO_HEADER}
    row.update({"id": "1", "fecha": "2024-01-01 09:00", "sujeto_obligado_nombre": "Lopez, Maria"})
    nuevo_csv = (";".join(NUEVO_HEADER) + "\n" + ";".join(row[column] for column in NUEVO_HEADER) + "\n").encode(
        "latin-1"
    )

    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, content=nuevo_csv)

    monkeypatch.setattr(audiencias, "_client", lambda: client_for(handler))
    monkeypatch.setattr(audiencias, "discover_audiencias", lambda: list(resources))

    data_dir = tmp_path / "data"
    result = audiencias.update_audiencias(data_dir=data_dir)
    assert result["discovered"] == 1
    assert result["downloaded"] == 1
    assert result["changed"] == 1
    assert result["unified"] is True
    assert (data_dir / "audiencias_unificado.csv").exists()
    assert (data_dir / "audiencias_state.json").exists()

    # Segunda corrida: nada cambió -> no descarga de nuevo, no re-unifica
    state_after_first = audiencias.load_state(data_dir / "audiencias_state.json")
    result2 = audiencias.update_audiencias(data_dir=data_dir)
    assert result2["changed"] == 0
    assert result2["unified"] is False
    state_after_second = audiencias.load_state(data_dir / "audiencias_state.json")
    # Los archivos (y sus hashes/tamaños) no cambian; solo se renueva last_updated.
    assert state_after_second["files"] == state_after_first["files"]

    # Tercera corrida forzada: vuelve a descargar y unificar
    result3 = audiencias.update_audiencias(data_dir=data_dir, force=True)
    assert result3["changed"] == 1
    assert result3["unified"] is True
