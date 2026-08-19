from __future__ import annotations

import ftplib
import hashlib
import os
import posixpath
import re
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from pipeline.models import Location, RemoteFile

PDF_SUFFIX = ".pdf"
MONTH_NAMES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


class DiscoveryError(RuntimeError):
    pass


def _classify(path: str, min_year: int) -> tuple[Location, int, int] | None:
    normalized = path.lower().replace("_", "-").replace(" ", "-")
    location: Location
    if "casa-rosada" in normalized or "casa-de-gobierno" in normalized or "/rosada/" in normalized:
        location = "casa-rosada"
    elif "olivos" in normalized:
        location = "olivos"
    else:
        return None
    parts = [part for part in re.split(r"[/\\]+", normalized) if part]
    year_index = next((i for i, part in enumerate(parts) if re.search(r"20\d{2}", part)), None)
    filename_years = [int(value) for value in re.findall(r"20\d{2}", parts[-1])]
    if year_index is None and not filename_years:
        return None
    path_years = (
        [int(value) for value in re.findall(r"20\d{2}", parts[year_index])]
        if year_index is not None
        else []
    )
    year = filename_years[-1] if filename_years else path_years[-1]
    if year < min_year:
        return None
    filename = parts[-1]
    month = next((number for name, number in MONTH_NAMES.items() if name in filename), 0)
    if not month and year_index is not None and year_index + 1 < len(parts):
        match = re.match(r"(0?[1-9]|1[0-2])(?:\D|$)", parts[year_index + 1])
        if match:
            month = int(match.group(1))
    if not month:
        match = re.match(r"(0?[1-9]|1[0-2])(?:\D|$)", filename)
        if match:
            month = int(match.group(1))
    if not month:
        filename = parts[-1]
        match = re.search(r"(?:^|\D)(0?[1-9]|1[0-2])(?:\D)(?:20)?\d{2}(?:\D|$)", filename)
        if match:
            month = int(match.group(1))
    if not month:
        raise DiscoveryError(f"No se pudo inferir el mes de {path}")
    return location, year, month


def _remote_from_item(base_url: str, item: dict[str, object], min_year: int) -> RemoteFile | None:
    path = str(item.get("path") or item.get("name") or "").lstrip("/")
    if not path.lower().endswith(PDF_SUFFIX):
        return None
    classification = _classify(path, min_year)
    if not classification:
        return None
    location, year, month = classification
    size = item.get("size")
    return RemoteFile(
        url=str(item.get("url") or urljoin(base_url.rstrip("/") + "/", path)),
        path=path,
        location=location,
        year=year,
        month=month,
        size=int(size) if size not in (None, "") else None,
        etag=_optional_str(item.get("etag")),
        last_modified=_optional_str(item.get("last_modified") or item.get("modified")),
        sha256=_optional_str(item.get("sha256")),
    )


def _optional_str(value: object) -> str | None:
    return str(value) if value not in (None, "") else None


def discover(base_url: str, min_year: int = 2023) -> list[RemoteFile]:
    if Path(base_url).exists():
        files = list(_discover_local(base_url, min_year))
        unique = {item.path: item for item in files}
        return sorted(unique.values(), key=lambda item: item.path)
    scheme = urlparse(base_url).scheme.lower()
    if scheme in {"ftp", "ftps"}:
        files = list(_discover_ftp(base_url, min_year))
    elif scheme in {"http", "https"}:
        files = list(_discover_http(base_url, min_year))
    elif scheme == "file":
        files = list(_discover_local(base_url, min_year))
    else:
        raise DiscoveryError("SOURCE_BASE_URL debe usar HTTPS, HTTP, FTP, FTPS o una carpeta local")
    unique = {item.path: item for item in files}
    return sorted(unique.values(), key=lambda item: item.path)


def _client() -> httpx.Client:
    transport = httpx.HTTPTransport(retries=3)
    return httpx.Client(
        transport=transport,
        follow_redirects=True,
        timeout=httpx.Timeout(60, connect=20),
        headers={"User-Agent": "accesos-publicos/0.1 (+GitHub Actions)"},
    )


def _discover_http(base_url: str, min_year: int) -> Iterator[RemoteFile]:
    base = base_url.rstrip("/") + "/"
    with _client() as client:
        manifest_response = client.get(urljoin(base, "index.json"))
        if manifest_response.status_code == 200:
            payload = manifest_response.json()
            items = payload if isinstance(payload, list) else payload.get("files", [])
            for item in items:
                if isinstance(item, dict) and (remote := _remote_from_item(base, item, min_year)):
                    yield remote
            return
        if manifest_response.status_code not in {403, 404}:
            manifest_response.raise_for_status()

        root = urlparse(base)
        queue = [base]
        seen: set[str] = set()
        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            response = client.get(current)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            found_link = False
            for anchor in soup.find_all("a", href=True):
                href = str(anchor["href"])
                if href.startswith(("?", "#")) or href in {"../", "./", "/"}:
                    continue
                candidate = urljoin(current, href)
                parsed = urlparse(candidate)
                if (parsed.scheme, parsed.netloc) != (root.scheme, root.netloc):
                    continue
                if not unquote(parsed.path).startswith(unquote(root.path)):
                    continue
                candidate = urlunparse(parsed._replace(query="", fragment=""))
                found_link = True
                if parsed.path.lower().endswith(PDF_SUFFIX):
                    relative = unquote(parsed.path[len(root.path) :]).lstrip("/")
                    classification = _classify(relative, min_year)
                    if not classification:
                        continue
                    location, year, month = classification
                    metadata = _head_metadata(client, candidate)
                    yield RemoteFile(candidate, relative, location, year, month, **metadata)
                elif href.endswith("/"):
                    queue.append(candidate.rstrip("/") + "/")
            if not found_link:
                raise DiscoveryError(f"El servidor no expone un listado navegable en {current}")


def _head_metadata(client: httpx.Client, url: str) -> dict[str, object]:
    try:
        response = client.head(url)
        if response.status_code in {405, 501}:
            return {}
        response.raise_for_status()
        size = response.headers.get("content-length")
        return {
            "size": int(size) if size and size.isdigit() else None,
            "etag": response.headers.get("etag"),
            "last_modified": response.headers.get("last-modified"),
        }
    except httpx.HTTPError:
        return {}


def _discover_ftp(base_url: str, min_year: int) -> Iterator[RemoteFile]:
    parsed = urlparse(base_url)
    ftp_class = ftplib.FTP_TLS if parsed.scheme == "ftps" else ftplib.FTP
    ftp = ftp_class()
    ftp.connect(parsed.hostname or "", parsed.port or 21, timeout=60)
    ftp.login("anonymous", "anonymous@")
    if isinstance(ftp, ftplib.FTP_TLS):
        ftp.prot_p()
    root = parsed.path or "/"
    try:
        yield from _walk_ftp(ftp, parsed, root, root, min_year)
    finally:
        ftp.quit()


def _discover_local(base_url: str, min_year: int) -> Iterator[RemoteFile]:
    parsed = urlparse(base_url)
    root = Path(
        unquote(parsed.path.lstrip("/"))
        if parsed.scheme == "file" and os.name == "nt"
        else unquote(parsed.path)
        if parsed.scheme == "file"
        else base_url
    ).resolve()
    if not root.is_dir():
        raise DiscoveryError(f"No existe la carpeta local {root}")
    for path in sorted(root.rglob("*.pdf")):
        relative = path.relative_to(root).as_posix()
        classification = _classify(relative, min_year)
        if not classification:
            continue
        location, year, month = classification
        info = path.stat()
        yield RemoteFile(
            url=path.as_uri(),
            path=relative,
            location=location,
            year=year,
            month=month,
            size=info.st_size,
            last_modified=str(info.st_mtime_ns),
        )


def _walk_ftp(
    ftp: ftplib.FTP, parsed: object, root: str, directory: str, min_year: int
) -> Iterator[RemoteFile]:
    try:
        entries = list(ftp.mlsd(directory))
    except ftplib.error_perm as error:
        raise DiscoveryError(
            "El FTP público debe soportar MLSD para un listado confiable"
        ) from error
    for name, facts in entries:
        if name in {".", ".."}:
            continue
        full_path = posixpath.join(directory, name)
        if facts.get("type") == "dir":
            yield from _walk_ftp(ftp, parsed, root, full_path, min_year)
            continue
        if not name.lower().endswith(PDF_SUFFIX):
            continue
        relative = str(PurePosixPath(full_path).relative_to(PurePosixPath(root))).lstrip("/")
        classification = _classify(relative, min_year)
        if not classification:
            continue
        location, year, month = classification
        netloc = parsed.netloc
        scheme = parsed.scheme
        yield RemoteFile(
            url=f"{scheme}://{netloc}{full_path}",
            path=relative,
            location=location,
            year=year,
            month=month,
            size=int(facts["size"]) if facts.get("size", "").isdigit() else None,
            last_modified=facts.get("modify"),
        )


def download(remote: RemoteFile, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    parsed = urlparse(remote.url)
    if parsed.scheme in {"http", "https"}:
        with _client() as client, client.stream("GET", remote.url) as response:
            response.raise_for_status()
            with target.open("wb") as handle:
                for chunk in response.iter_bytes(1024 * 1024):
                    handle.write(chunk)
                    digest.update(chunk)
    elif parsed.scheme == "file":
        source = Path(unquote(parsed.path.lstrip("/")) if os.name == "nt" else unquote(parsed.path))
        with source.open("rb") as reader, target.open("wb") as handle:
            while chunk := reader.read(1024 * 1024):
                handle.write(chunk)
                digest.update(chunk)
    else:
        ftp_class = ftplib.FTP_TLS if parsed.scheme == "ftps" else ftplib.FTP
        ftp = ftp_class()
        ftp.connect(parsed.hostname or "", parsed.port or 21, timeout=60)
        ftp.login("anonymous", "anonymous@")
        if isinstance(ftp, ftplib.FTP_TLS):
            ftp.prot_p()
        with target.open("wb") as handle:

            def write(chunk: bytes) -> None:
                handle.write(chunk)
                digest.update(chunk)

            ftp.retrbinary(f"RETR {unquote(parsed.path)}", write, blocksize=1024 * 1024)
        ftp.quit()
    return digest.hexdigest()
