from datetime import datetime, time
from pathlib import Path
from types import SimpleNamespace

from pipeline.historical_office_import import (
    _cell_datetime,
    _entry_is_current,
    _entry_matches_metadata,
    _infer_date,
    _parse_olivos_rows,
    _source_period,
)
from pipeline.models import RemoteFile
from pipeline.parsers.positioned import _sanitize_olivos_date


def test_parses_olivos_rows_with_document_and_times() -> None:
    rows = [
        ["PLANILLA TURNO DEL DIA 08 DE ENERO DE 2016"],
        [
            "Nro",
            "AUTORIDAD",
            "DOCUMENTO",
            "CONCURRE A:",
            "AUTORIZADO POR",
            "HORA ENTRADA",
            "HORA SALIDA",
        ],
        [1, "Pérez Ana", "30.123.456", "Jefatura", "Administración", time(14, 30), "1655"],
        [2, "SIN NOVEDAD", "", "", "", "", ""],
    ]

    result = _parse_olivos_rows(
        rows,
        "Hoja1",
        Path("Planilla de ingreso 08 ENE 16.xlsx"),
        "raw/olivos/2016/Planilla de ingreso 08 ENE 16.xlsx",
        "src_test",
        1,
        {},  # type: ignore[arg-type]
    )

    assert len(result) == 1
    assert result[0].canonical_name == "PEREZ ANA"
    assert result[0].document_number == "30123456"
    assert result[0].entered_at == datetime(2016, 1, 8, 14, 30)
    assert result[0].exited_at == datetime(2016, 1, 8, 16, 55)


def test_parses_compact_docx_clock() -> None:
    assert _cell_datetime("0735", datetime(2019, 6, 1)) == datetime(2019, 6, 1, 7, 35)


def test_repairs_truncated_and_stale_excel_years() -> None:
    default = datetime(2019, 5, 28)
    assert _cell_datetime("28-5-198 17:26", default) == datetime(2019, 5, 28, 17, 26)
    assert _cell_datetime(datetime(2017, 5, 28, 8, 15), default) == datetime(
        2019, 5, 28, 8, 15
    )


def test_repairs_implausible_pdf_year_from_filename() -> None:
    remote = RemoteFile(
        "file:///source.pdf",
        "Ingresos Quinta de Olivos/2023/3. Marzo/PLANILLAS DE INGRESOS 27 MAR 23-.pdf",
        "olivos",
        2023,
        3,
    )
    assert _sanitize_olivos_date(datetime(2000, 1, 1, 7, 26), remote) == datetime(
        2023, 3, 27, 7, 26
    )


def test_source_period_uses_nearest_year_instead_of_parent_range() -> None:
    path = Path(
        "Ingresos Quinta de Olivos 2016-2019/AÑO 2017/5-MAYO 2017/26-05 a pie.xls"
    )
    assert _source_period(path) == (2017, 5)


def test_infer_date_prefers_source_period_over_stale_template_year() -> None:
    source = Path("Ingresos Quinta de Olivos 2016-2019/AÑO 2018/1-ENERO/02-01 VISITAS.xlsx")
    rows = [["PLANILLA TURNO DEL DIA 31 DE ENERO DE 2019"]]
    assert _infer_date(source, "AUDIENCIAS", rows) == datetime(2018, 1, 2)


def test_parses_headerless_daily_on_foot_register_without_inventing_times() -> None:
    rows = [
        ["RESIDENCIA PRESIDENCIAL DE OLIVOS"],
        ["DIRECCION DE SEGURIDAD"],
        ["PLANILLA DE MOVIMIENTO DEL DIA 01 DE SEPTIEMBRE DE 2017"],
        ["Pérez Ana", 30_123_456, "Jefatura"],
        ["SIN NOVEDAD", "", ""],
    ]
    result = _parse_olivos_rows(
        rows,
        "Hoja1",
        Path("AÑO 2017/9-SEPTIEMBRE 17/INGRESO A PIE/01-09 A PIE.xlsx"),
        "raw/Ingresos Quinta de Olivos/AÑO 2017/9-SEPTIEMBRE 17/INGRESO A PIE/01.xlsx",
        "src_test",
        1,
        {},  # type: ignore[arg-type]
    )

    assert len(result) == 1
    assert result[0].canonical_name == "PEREZ ANA"
    assert result[0].document_number == "30123456"
    assert result[0].occurred_at == datetime(2017, 9, 1)
    assert result[0].entered_at is None
    assert result[0].exited_at is None
    assert result[0].quality == "medium"


def test_parses_daily_vehicle_register_and_keeps_plate_as_device() -> None:
    rows = [
        ["PLANILLA DE MOVIMIENTO VEHICULAR DEL DIA 01 DE AGOSTO DE 2018"],
        ["AA123BB", "Pérez Ana", 30_123_456, "Jefatura"],
    ]
    result = _parse_olivos_rows(
        rows,
        "Hoja1",
        Path("AÑO 2018/8-AGOSTO/VEHICULO 2018/01 AGOSTO Vehiculo.xlsx"),
        "raw/Ingresos Quinta de Olivos/AÑO 2018/8-AGOSTO/VEHICULO/01.xlsx",
        "src_test",
        1,
        {},  # type: ignore[arg-type]
    )

    assert len(result) == 1
    assert result[0].record_type == "vehicle"
    assert result[0].device == "AA123BB"
    assert result[0].destination == "Jefatura"
    assert result[0].occurred_at == datetime(2018, 8, 1)


def test_daily_register_discards_institutional_headers_groups_and_plates() -> None:
    rows = [
        ["PLANILLA DE MOVIMIENTO VEHICULAR DEL DIA 01 DE AGOSTO DE 2018"],
        ["AA123BB", "2018 AÑO DEL CENTENARIO DE LA REFORMA UNIVERSITARIA", "", ""],
        ["AB123CD", "24 MENORES", "", ""],
        ["AC123DE", "AA675WK", "", ""],
    ]
    result = _parse_olivos_rows(
        rows,
        "Hoja1",
        Path("AÑO 2018/8-AGOSTO/VEHICULO 2018/01 AGOSTO Vehiculo.xlsx"),
        "raw/Ingresos Quinta de Olivos/AÑO 2018/8-AGOSTO/VEHICULO/01.xlsx",
        "src_test",
        1,
        {},  # type: ignore[arg-type]
    )
    assert result == []


def test_current_manifest_entry_is_skipped_only_when_partitions_exist(tmp_path: Path) -> None:
    partition = tmp_path / "olivos/2017/01/source.parquet"
    partition.parent.mkdir(parents=True)
    partition.touch()
    entry = {
        "sha256": "abc",
        "status": "active",
        "parser": "olivos-xlsx-historico-v2",
        "partitions": ["olivos/2017/01/source.parquet"],
    }

    assert _entry_is_current(entry, "abc", tmp_path)
    partition.unlink()
    assert not _entry_is_current(entry, "abc", tmp_path)


def test_current_quarantined_entry_needs_no_partition(tmp_path: Path) -> None:
    entry = {
        "sha256": "abc",
        "status": "quarantined",
        "parser": "pdf-sin-texto-extraible-v1",
        "partitions": [],
    }
    assert _entry_is_current(entry, "abc", tmp_path)


def test_current_entry_can_be_skipped_from_stable_local_metadata(tmp_path: Path) -> None:
    entry = {
        "sha256": "abc",
        "size": 123,
        "last_modified": "456",
        "status": "active",
        "parser": "olivos-xls-historico-v1",
        "partitions": [],
    }
    info = SimpleNamespace(st_size=123, st_mtime_ns=456)
    assert _entry_matches_metadata(entry, info, tmp_path)
