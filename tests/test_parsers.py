from pipeline.models import RemoteFile
from pipeline.parsers.casa_rosada import parse_casa_pages
from pipeline.parsers.historical_tables import (
    parse_casa_historical_list_pages,
    parse_casa_historical_visitors,
    parse_casa_table,
    parse_olivos_table,
)
from pipeline.parsers.olivos import parse_olivos_pages


def remote(location: str, path: str) -> RemoteFile:
    return RemoteFile(
        url=f"https://example.org/{path}",
        path=path,
        location=location,  # type: ignore[arg-type]
        year=2023,
        month=1,
    )


def test_casa_rosada_keeps_person_across_pages() -> None:
    pages = [
        """ALVARADO MARCELO RODRIGO CUIL: 20-31248860-5 CR_B24_MOLINETE_2.BIO_Entrada 18/04/2023 7:08 a.m. Acceso Autorizado
CR_B24_MOLINETE_2.BIO_Salida 18/04/2023 3:31 p.m. Acceso Autorizado""",
        "CR_B24_MOLINETE_3.BIO_Entrada 19/04/2023 6:56 a.m. Movimiento off-line",
    ]
    result = parse_casa_pages(
        pages, remote("casa-rosada", "casa-rosada/2023/04/movimientos.pdf"), "src_test"
    )
    assert result.parser == "casa-rosada-movimientos-v1"
    assert len(result.records) == 3
    assert result.records[0].direction == "entrada"
    assert result.records[2].source_page == 2
    assert result.records[0].document_number == "20312488605"


def test_olivos_extracts_person_vehicle_and_times() -> None:
    pages = [
        """PLANILLA DE CONTROL DE MOVIMIENTOS DE PERSONAL A PIE - TURNO DEL DÍA 1 DE ENERO DE 2023
1 CORONEL CRISTINA 39.207.656 LIMPIEZA RPO TIAN ADMINISTRACIÓN 1-1-23 6:34 AM 1-1-23 7:35 PM""",
        """PLANILLA DE CONTROL DE MOVIMIENTOS DE PERSONAL EN VEHÍCULOS - TURNO DEL DÍA 1 DE ENERO DE 2023
1 LACATTIVA ALFREDO 13.064.415 RPO CHOFER ADMINISTRACIÓN 1-1-23 7:00 AM 1-1-23 9:20 AM""",
    ]
    result = parse_olivos_pages(pages, remote("olivos", "olivos/2023/01/01.pdf"), "src_test")
    assert [record.record_type for record in result.records] == ["person", "vehicle"]
    assert result.records[0].entered_at.hour == 6
    assert result.records[0].exited_at.hour == 19


def test_olivos_allows_sin_novedad() -> None:
    result = parse_olivos_pages(
        ["SIN NOVEDAD"], remote("olivos", "olivos/2023/01/02.pdf"), "src_test"
    )
    assert result.records == []


def test_historical_olivos_table_extracts_all_three_layouts() -> None:
    rows = [
        ["NRO", "APELLIDO Y NOMBRE", "DOCUMENTO", "CONCURRE PARA:", "ACTIVIDAD:", None, "AUTORIZADO POR:", "HORA ENTRADA", "HORA SALIDA"],
        [None, None, None, None, "FUNCIONARIO", "OTRO", None, None, None],
        ["1", "CERRUTI, GABRIELA", "17,875,702", "SP", "PORTAVOZ PRES", "", "ADMINISTRACIÓN", "3-1-22 1:32 PM", "3-1-22 3:34 PM"],
    ]
    records = parse_olivos_table(rows, remote("olivos", "olivos/2022/01/03.pdf"), "src_test", 1)
    assert len(records) == 1
    assert records[0].canonical_name == "CERRUTI GABRIELA"
    assert records[0].document_number == "17875702"
    assert records[0].entered_at.hour == 13
    assert records[0].destination == "SP"


def test_historical_olivos_table_discards_sentinel_dates_per_column() -> None:
    rows = [
        ["NRO", "APELLIDO Y NOMBRE", "DOCUMENTO", "CONCURRE PARA:", "ACTIVIDAD:", None, None, None, "AUTORIZADO POR:", "HORA ENTRADA", "HORA SALIDA"],
        [None, None, None, None, "FUNCIONARIO", "OTRO", None, None, None, None, None],
        ["8", "QUIROGA ROBERTO", "36,665,312", "OTROS", "CISTERNA", "AYSA", "", "", "ADMINISTRACIÓN", "3-1-00 5:00 AM", "29-1-22 5:00 PM"],
    ]
    records = parse_olivos_table(
        rows, remote("olivos", "olivos/2022/01/29.pdf"), "src_test", 3
    )
    assert len(records) == 1
    assert records[0].entered_at is None
    assert records[0].exited_at.isoformat() == "2022-01-29T17:00:00"


def test_historical_casa_table_accepts_continuation_pages() -> None:
    rows = [["CARO, PABLO EZEQUIEL (27257531)", "EMPRESA FACTORY", "", "OLMEDO", "S/A", "1/5/2021 11:18", "1/5/2021 12:30"]]
    records = parse_casa_table(rows, remote("casa-rosada", "casa-rosada/2021/05/listado.pdf"), "src_test", 2)
    assert len(records) == 1
    assert records[0].canonical_name == "CARO PABLO EZEQUIEL"
    assert records[0].document_number == "27257531"
    assert records[0].source_page == 2


def test_historical_casa_visitors_uses_page_date_and_handles_overnight_exit() -> None:
    pages = [
        "jueves, 11julio, 2019\n"
        "COMAS MARTA NDoc: 18142199 LIMPIA 2001 OLMEDO FEDERICO 23:04 1:10 CR-YRI-219"
    ]
    result = parse_casa_historical_visitors(
        pages,
        remote("casa-rosada", "casa-rosada/2021/07/visitantes.pdf"),
        "src_test",
    )
    assert len(result.records) == 1
    assert result.records[0].entered_at.isoformat() == "2019-07-11T23:04:00"
    assert result.records[0].exited_at.isoformat() == "2019-07-12T01:10:00"


def test_historical_casa_list_parses_spreadsheet_export_line() -> None:
    pages = [
        "MARCO, MARIA VICTORIA (20257085) SUBSECRETARIA TECNICA "
        "12/7/2019 11:20 12/7/2019 15:05"
    ]
    result = parse_casa_historical_list_pages(
        pages,
        remote("casa-rosada", "casa-rosada/2021/04/E_Listado.pdf"),
        "src_test",
    )
    assert len(result.records) == 1
    assert result.records[0].canonical_name == "MARCO MARIA VICTORIA"
    assert result.records[0].document_number == "20257085"
