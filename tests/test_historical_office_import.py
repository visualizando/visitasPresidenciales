from datetime import datetime, time
from pathlib import Path

from pipeline.historical_office_import import _cell_datetime, _parse_olivos_rows
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
