from pipeline.models import RemoteFile
from pipeline.parsers.casa_rosada import parse_casa_pages
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
