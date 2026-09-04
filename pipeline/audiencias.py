"""Descubrimiento, descarga y actualización de Audiencias de Gestión de Intereses.

Este módulo integra los CSV anuales del Registro Único de Audiencias de Gestión
de Intereses (https://datos.gob.ar/dataset/registro-unico-de-audiencias-de-gestion-de-intereses)
al flujo de actualización de datos.

Los archivos se conservan en `data/raw/` y se normalizan a un único CSV unificado
en `data/audiencias_unificado.csv.gz`. El estado de cada fuente (URL, sha256, tamaño,
formato) se guarda en `data/audiencias_state.json` para detectar cambios de forma
incremental: solo se re-descarga un archivo si cambió su hash o su tamaño.

La unificación y normalización de esquemas viven en `pipeline/unify_audiencias.py`.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup

from pipeline.storage import utc_now
from pipeline.unify_audiencias import detect_format, unify

DATASET_URL = "https://datos.gob.ar/dataset/registro-unico-de-audiencias-de-gestion-de-intereses"
STATE_FILE = Path("data/audiencias_state.json")
DEFAULT_RAW_DIR = Path("data/raw")
DEFAULT_OUTPUT = Path("data/audiencias_unificado.csv.gz")

_USER_AGENT = "accesos-publicos/0.1 (+GitHub Actions)"


def _client() -> httpx.Client:
    transport = httpx.HTTPTransport(retries=3)
    return httpx.Client(
        transport=transport,
        follow_redirects=True,
        timeout=httpx.Timeout(120, connect=30),
        headers={"User-Agent": _USER_AGENT},
    )


def _audiencia_name(year: int, is_bis: bool = False) -> str:
    suffix = "-bis" if is_bis else ""
    return f"audiencias-{year}{suffix}.csv"


def _parse_download_url(href: str) -> dict[str, Any] | None:
    """Extrae año, nombre y flag 'bis' desde la URL de descarga de un CSV."""
    filename = href.rstrip("/").rsplit("/", 1)[-1]
    if not filename.lower().endswith(".csv"):
        return None
    years = [int(m.group()) for m in re.finditer(r"20\d{2}", filename)]
    if not years:
        return None
    year = years[-1]
    is_bis = "bis" in filename.lower()
    name = _audiencia_name(year, is_bis)
    if year == 2004:
        name = "audiencias-2004.csv"
    return {"year": year, "name": name, "url": href, "is_bis": is_bis}


def discover_audiencias() -> list[dict[str, Any]]:
    """Descubre los CSV anuales disponibles en la página del dataset.

    El año y el flag 'bis' se derivan del nombre del archivo en la URL de
    descarga (por ejemplo audiencias-2004b.csv, 2017.csv,
    audiencias-2016-bis-sistema-nuevo.csv), lo cual es más confiable que el
    texto del recurso.
    """
    with _client() as client:
        response = client.get(DATASET_URL)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

    resources: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "")
        if not href.lower().endswith(".csv"):
            continue
        parsed = _parse_download_url(href)
        if parsed is None or href in seen_urls:
            continue
        seen_urls.add(href)
        resources.append(parsed)

    resources.sort(key=lambda item: (item["year"], item["is_bis"]))
    return resources


def download_audiencia(url: str, target: Path) -> str:
    """Descarga un CSV de audiencias (latin-1) a UTF-8 y devuelve su sha256.

    Los archivos del portal vienen en latin-1; se re-encodean a UTF-8 al guardar.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with _client() as client, client.stream("GET", url) as response:
        response.raise_for_status()
        with target.open("wb") as handle:
            for chunk in response.iter_bytes(1024 * 1024):
                handle.write(chunk)
                digest.update(chunk)
    return digest.hexdigest()


def load_state(path: Path = STATE_FILE) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "last_updated": None, "files": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(state: dict[str, Any], path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def update_audiencias(
    data_dir: Path,
    raw_dir: Path | None = None,
    output: Path | None = None,
    force: bool = False,
    state_path: Path | None = None,
) -> dict[str, int | str | None]:
    """Descubre, descarga (si cambió) y unifica los CSV anuales de audiencias.

    Devuelve un dict con los conteos y el estado tras la actualización.
    """
    data_dir = Path(data_dir)
    raw_dir = Path(raw_dir) if raw_dir is not None else data_dir / "raw"
    output = Path(output) if output is not None else data_dir / "audiencias_unificado.csv.gz"
    state_path = Path(state_path) if state_path is not None else data_dir / "audiencias_state.json"

    raw_dir.mkdir(parents=True, exist_ok=True)
    state = load_state(state_path)
    previous_files: dict[str, dict[str, Any]] = state.setdefault("files", {})

    discovered = discover_audiencias()
    downloaded = 0
    changed = 0
    skipped = 0
    for resource in discovered:
        name: str = resource["name"]
        url: str = resource["url"]
        old = previous_files.get(name)
        local = raw_dir / name

        if not force and _audiencia_is_current(local, old):
            skipped += 1
            continue

        sha256 = download_audiencia(url, local)
        size = local.stat().st_size
        fmt = detect_format(local)
        downloaded += 1
        changed += 1
        previous_files[name] = {
            "url": url,
            "year": resource["year"],
            "name": name,
            "is_bis": resource["is_bis"],
            "format": fmt,
            "sha256": sha256,
            "size": size,
            "last_checked": utc_now(),
        }

    # Si algo cambió (o se forzó), re-unificamos todos los CSVs presentes.
    unified = False
    counts: dict[str, int | str | None] = {}
    if changed > 0 or force:
        counts = unify(raw_dir, output)
        unified = True

    state["last_updated"] = utc_now()
    write_state(state, state_path)

    return {
        "discovered": len(discovered),
        "downloaded": downloaded,
        "changed": changed,
        "skipped": skipped,
        "unified": unified,
        "total_filas": counts.get("total"),
        "columnas": counts.get("columnas"),
        "filas_viejo": counts.get("viejo"),
        "filas_nuevo": counts.get("nuevo"),
        "last_updated": state["last_updated"],
    }


def _audiencia_is_current(local: Path, old: dict[str, Any] | None) -> bool:
    """True si el CSV local ya existe y su tamaño coincide con el del estado."""
    if not local.exists() or not old:
        return False
    return local.stat().st_size == old.get("size")
