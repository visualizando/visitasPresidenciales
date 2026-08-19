from __future__ import annotations

from pathlib import Path

import pymupdf

from pipeline.models import ParseResult, RemoteFile
from pipeline.parsers.casa_rosada import parse_casa_pages
from pipeline.parsers.historical_tables import (
    parse_casa_historical_list_pages,
    parse_casa_historical_visitors,
    parse_historical_tables,
)
from pipeline.parsers.olivos import parse_olivos_pages
from pipeline.parsers.positioned import parse_positioned_pdf


class ParseFailure(RuntimeError):
    pass


def parse_pdf(path: Path, remote: RemoteFile, source_id: str) -> ParseResult:
    try:
        document = pymupdf.open(path)
    except Exception as error:  # PyMuPDF exposes several format-specific exceptions
        raise ParseFailure(f"No se pudo abrir {remote.path}: {error}") from error
    try:
        if document.page_count == 0:
            raise ParseFailure(f"El PDF {remote.path} no contiene páginas")
        sample_pages = [
            document[index].get_text("text", sort=True)
            for index in range(min(5, document.page_count))
        ]
    finally:
        document.close()
    sample = "".join(sample_pages)
    if len(sample.strip()) < 80:
        raise ParseFailure(f"{remote.path} parece escaneado o no contiene texto extraíble")
    filename = remote.path.lower()
    if remote.location == "casa-rosada" and "movimientos_generales" in filename:
        document = pymupdf.open(path)
        try:
            result = parse_casa_pages(
                (page.get_text("text", sort=True) for page in document),
                remote,
                source_id,
                family="movement",
            )
        finally:
            document.close()
        if result.records:
            return result
    if remote.location == "casa-rosada" and "registro de ingreso de visitantes" in sample.lower():
        document = pymupdf.open(path)
        try:
            result = parse_casa_historical_visitors(
                (page.get_text("text", sort=True) for page in document), remote, source_id
            )
        finally:
            document.close()
        if result.records:
            return result
    if remote.location == "casa-rosada" and "listado" in filename:
        document = pymupdf.open(path)
        try:
            result = parse_casa_historical_list_pages(
                (page.get_text("text", sort=True) for page in document), remote, source_id
            )
        finally:
            document.close()
        if result.records:
            return result
    if remote.location == "olivos" and remote.year < 2023:
        historical = parse_historical_tables(path, remote, source_id)
        if historical.records:
            return historical
    positioned = parse_positioned_pdf(path, remote, source_id)
    if positioned.records:
        return positioned
    historical = parse_historical_tables(path, remote, source_id)
    if historical.records:
        return historical
    document = pymupdf.open(path)
    try:
        pages = [page.get_text("text", sort=True) for page in document]
    finally:
        document.close()
    if remote.location == "olivos":
        result = parse_olivos_pages(pages, remote, source_id)
    elif any(word in filename for word in ("visitante", "listado")):
        result = parse_casa_pages(pages, remote, source_id, family="visitor")
    else:
        result = parse_casa_pages(pages, remote, source_id, family="movement")
    no_activity = "SIN NOVEDAD" in sample.upper()
    if not result.records and not no_activity:
        raise ParseFailure(f"El parser {result.parser} no encontró registros en {remote.path}")
    return result
