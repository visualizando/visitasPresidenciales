from __future__ import annotations

from pathlib import Path

import pymupdf

from pipeline.models import ParseResult, RemoteFile
from pipeline.parsers.casa_rosada import parse_casa_pages
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
        pages = [page.get_text("text", sort=True) for page in document]
    finally:
        document.close()
    sample = "".join(pages[: min(5, len(pages))])
    if len(sample.strip()) < 80:
        raise ParseFailure(f"{remote.path} parece escaneado o no contiene texto extraíble")
    positioned = parse_positioned_pdf(path, remote, source_id)
    if positioned.records:
        return positioned
    filename = remote.path.lower()
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
