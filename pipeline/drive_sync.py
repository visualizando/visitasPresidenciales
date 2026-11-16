"""Inventory, version and reconcile public NGO files without changing canonical records.

The HTML fallback cannot certify completeness. Set GOOGLE_DRIVE_API_KEY to use
paginated Drive v3 listing. Raw versions are immutable and keyed by ID + SHA256.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from random import uniform

import httpx
from bs4 import BeautifulSoup

from pipeline.storage import load_json, utc_now, write_json_atomic

DEFAULT_FOLDER = "1ZgFqfWYnsGQh5gRdwrbP5cmUjb-BqL-0"
DEFAULT_SOURCES = {
    "casa-rosada": DEFAULT_FOLDER,
    "olivos": "1hFUlnyYj1MmGiKsvnWrChIZHpbwmX_xh",
}
API = "https://www.googleapis.com/drive/v3/files"
EXTENSIONS = {".pdf", ".xls", ".xlsx", ".docx"}


class DriveRequestError(RuntimeError):
    """An HTTP failure with context safe to emit in public workflow logs."""


def _retry_request[T](operation: Callable[[], T], context: str) -> T:
    for attempt in range(4):
        try:
            return operation()
        except httpx.HTTPError as error:
            status = type(error).__name__
            delay = 2 ** (attempt + 1) + uniform(0, 1)
            retryable = isinstance(error, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError))
            if isinstance(error, httpx.HTTPStatusError):
                response = error.response
                code = response.status_code
                status = f"HTTP {code}"
                retry_after = response.headers.get("Retry-After", "")
                retryable = code in {408, 429, 500, 502, 503, 504} or (code == 403 and bool(retry_after))
                if code == 403 and not retryable and response.is_closed:
                    try:
                        errors = response.json()["error"]["errors"]
                        retryable = any(item.get("reason") in {"rateLimitExceeded", "userRateLimitExceeded"} for item in errors)
                    except (ValueError, KeyError, TypeError, AttributeError, httpx.ResponseNotRead):
                        pass
                if retry_after.isascii() and retry_after.isdecimal():
                    delay = max(delay, int(retry_after))
            if attempt == 3 or not retryable or delay > 60:
                raise DriveRequestError(f"{context}: {status} ({attempt + 1} intento(s))") from None
            time.sleep(delay)
    raise AssertionError("Unreachable retry state")


def _get(client: httpx.Client, url: str, params: dict, context: str) -> httpx.Response:
    return _retry_request(lambda: client.get(url, params=params).raise_for_status(), context)


def valid_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Invalid Drive ID")
    return value


def list_children(client: httpx.Client, folder: str, api_key: str | None) -> list[dict]:
    valid_id(folder)
    if api_key:
        items, token, seen = [], None, set()
        while True:
            params = {
                "key": api_key,
                "q": f"'{folder}' in parents and trashed = false",
                "pageSize": 1000,
                "fields": "nextPageToken,incompleteSearch,files(id,name,mimeType,modifiedTime,size,md5Checksum)",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            if token:
                params["pageToken"] = token
            response = _get(client, API, params, f"listar carpeta {folder} por API")
            payload = response.json()
            if payload.get("incompleteSearch"):
                raise ValueError("Drive returned an incomplete search")
            items.extend(payload.get("files", []))
            token = payload.get("nextPageToken")
            if not token:
                return items
            if token in seen:
                raise ValueError("Repeated Drive pagination token")
            seen.add(token)
    response = _get(client, f"https://drive.google.com/drive/folders/{folder}", {"hl": "en"}, f"listar carpeta publica {folder}")
    if "accounts.google.com" in str(response.url):
        raise ValueError("Drive requires authentication")
    soup = BeautifulSoup(response.text, "html.parser")
    entries = {
        str(e["data-id"]): str(e["data-tooltip"]) for e in soup.select("[data-id][data-tooltip]")
    }
    # An empty HTML document is never interpreted as deletion of sources.
    items = []
    for item_id, label in entries.items():
        folder_label = label.endswith((" Shared folder", " Folder"))
        match = re.match(r"(.+\.(?:pdf|xlsx|xls|docx))(?:\s|$)", label, re.I)
        name = (
            label.removesuffix(" Shared folder").removesuffix(" Folder")
            if folder_label
            else match.group(1)
            if match
            else label
        )
        items.append(
            {
                "id": valid_id(item_id),
                "name": name,
                "mimeType": "application/vnd.google-apps.folder" if folder_label else "",
            }
        )
    return items


def inventory(client: httpx.Client, folder: str, api_key: str | None) -> dict:
    queue, visited, files, warnings = [(valid_id(folder), "")], set(), [], []
    while queue:
        folder_id, parent_path = queue.pop(0)
        if folder_id in visited:
            continue
        visited.add(folder_id)
        children = list_children(client, folder_id, api_key)
        if not api_key and (not children or len(children) >= 50):
            warnings.append(
                {
                    "folder_id": folder_id,
                    "path": parent_path,
                    "reason": "empty_or_possibly_paginated_html",
                    "visible_entries": len(children),
                }
            )
        for item in children:
            valid_id(item["id"])
            path = f"{parent_path}/{item['name']}".lstrip("/")
            if item["mimeType"] == "application/vnd.google-apps.folder":
                queue.append((item["id"], path))
            else:
                files.append(
                    {
                        **item,
                        "path": path,
                        "url": f"https://drive.google.com/file/d/{item['id']}/view",
                    }
                )
    return {
        "folder_id": folder,
        "files": files,
        "folders": len(visited),
        "warnings": warnings,
        "listing_complete": bool(api_key),
        "method": "drive-v3" if api_key else "public-html-unverified",
    }


def fetch_version(client: httpx.Client, item: dict, raw: Path, *, allow_invalid: bool = False) -> dict:
    if item["name"].startswith(("~$", "_$")):
        return {"comparison": "temporary_office_file"}
    suffix = Path(item["name"]).suffix.lower()
    if suffix not in EXTENSIONS:
        return {"comparison": "unsupported_format"}
    file_id = valid_id(item["id"])
    return _retry_request(
        lambda: _download_version(client, item, raw, suffix, allow_invalid), f"descargar archivo {file_id}"
    )


def _download_version(client: httpx.Client, item: dict, raw: Path, suffix: str, allow_invalid: bool) -> dict:
    directory = raw / item["id"]
    directory.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=directory, suffix=".part")
    partial = Path(temporary)
    try:
        with (
            os.fdopen(fd, "wb") as stream,
            client.stream(
                "GET",
                "https://drive.usercontent.google.com/download",
                params={"id": item["id"], "export": "download", "confirm": "t"},
            ) as response,
        ):
            response.raise_for_status()
            for chunk in response.iter_bytes():
                stream.write(chunk)
        with partial.open("rb") as stream:
            magic = stream.read(8)
            stream.seek(0)
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
            stream.seek(0)
            md5 = hashlib.file_digest(stream, "md5").hexdigest()
        expected = (
            b"%PDF" if suffix == ".pdf" else b"\xd0\xcf\x11\xe0" if suffix == ".xls" else b"PK"
        )
        invalid = bool(magic and not magic.startswith(expected))
        if invalid and (not allow_invalid or "text/html" in response.headers.get("content-type", "") or magic.lstrip().startswith(b"<")):
            raise ValueError("Unexpected signature (possibly HTML instead of a document)")
        if item.get("md5Checksum") and md5 != item["md5Checksum"]:
            raise ValueError("Drive checksum mismatch")
        if item.get("size") is not None and partial.stat().st_size != int(item["size"]):
            raise ValueError("Drive size mismatch")
        target = directory / f"{checksum}{suffix}"
        os.replace(partial, target)
        result = {
            "sha256": checksum,
            "size": target.stat().st_size,
            "raw_path": target.relative_to(raw).as_posix(),
        }
        if not magic:
            result["comparison"] = "empty_file"
        elif invalid:
            result["comparison"] = "invalid_file"
        return result
    finally:
        partial.unlink(missing_ok=True)


def cached_version(item: dict, previous: dict | None, raw: Path) -> dict | None:
    """Reuse bytes only when Drive's content checksum and the local hash agree."""
    if (
        not previous
        or not item.get("md5Checksum")
        or item["md5Checksum"] != previous.get("md5Checksum")
    ):
        return None
    if not previous.get("raw_path") or not previous.get("sha256"):
        return None
    path = (raw / previous["raw_path"]).resolve()
    if not path.is_relative_to(raw.resolve()) or not path.is_file():
        return None
    with path.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    if checksum != previous["sha256"]:
        return None
    result = {"sha256": checksum, "size": path.stat().st_size, "raw_path": previous["raw_path"]}
    if path.stat().st_size == 0:
        result["comparison"] = "empty_file"
    return result


def sync_drive(
    folder: str, data_dir: Path, *, download: bool = False, api_key: str | None = None
) -> dict:
    manifest = load_json(data_dir / "manifest.json", {"files": {}})
    prior = load_json(data_dir / "drive" / folder / "inventory.json", {"files": []})
    previous = {item["id"]: item for item in prior["files"]}
    hashes: dict[str, list[dict]] = {}
    for key, entry in manifest["files"].items():
        if entry.get("sha256"):
            hashes.setdefault(entry["sha256"], []).append(
                {
                    "path": key,
                    "source_id": entry["source_id"],
                    "status": entry["status"],
                    "location": entry["location"],
                }
            )
    with httpx.Client(
        follow_redirects=True, timeout=180, headers={"Accept-Language": "en-US"}
    ) as client:
        result = inventory(client, folder, api_key)
        for item in result["files"]:
            item["comparison"] = "not_downloaded"
            if download:
                try:
                    raw = data_dir / "drive" / "raw"
                    cached = cached_version(item, previous.get(item["id"]), raw)
                    item.update(cached or fetch_version(client, item, raw))
                    if item.get("sha256"):
                        item["content_matches"] = hashes.get(item["sha256"], [])
                        if item.get("comparison") != "empty_file":
                            item["comparison"] = (
                                "identical_content"
                                if item["content_matches"]
                                else "requires_review"
                            )
                except (DriveRequestError, ValueError, OSError) as error:
                    # Avoid serializing request URLs that might include credentials.
                    item.update(comparison="download_failed", error_type=type(error).__name__)
    result["generated_at"] = utc_now()
    result["summary"] = dict(Counter(item["comparison"] for item in result["files"]))
    # A read-only listing must not discard the last downloaded checksums/cache.
    report_name = "inventory.json" if download else "listing.json"
    write_json_atomic(data_dir / "drive" / folder / report_name, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inventaría Drive y compara archivos sin modificar la base"
    )
    parser.add_argument(
        "--folder-id",
        default=os.getenv("GOOGLE_DRIVE_FOLDER_ID"),
        help="Una carpeta específica; por defecto consulta ambas sedes",
    )
    parser.add_argument("--data-dir", type=Path, default=Path(os.getenv("DATA_DIR", "data")))
    parser.add_argument(
        "--download",
        action="store_true",
        help="Descarga y compara por SHA256; conserva versiones anteriores",
    )
    args = parser.parse_args()
    failed = False
    sources = {"custom": args.folder_id} if args.folder_id else DEFAULT_SOURCES
    for location, folder in sources.items():
        try:
            result = sync_drive(
                folder,
                args.data_dir,
                download=args.download,
                api_key=os.getenv("GOOGLE_DRIVE_API_KEY"),
            )
        except (httpx.HTTPError, ValueError) as error:
            raise SystemExit(
                f"Drive {location}: {type(error).__name__}; inventario no actualizado"
            ) from None
        print(
            json.dumps(
                {"location": location, **{k: v for k, v in result.items() if k != "files"}},
                ensure_ascii=False,
                indent=2,
            )
        )
        failed = failed or bool(result["summary"].get("download_failed"))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()


def drive_issue_counts(state: dict) -> dict[str, int]:
    issues = [item for item in state.get("files", {}).values() if item.get("status") == "quarantined"]
    empty = sum(item.get("reason") == "ParseFailure: empty_file" for item in issues)
    return {"empty_files": empty, "other_files": len(issues) - empty}


def verified_source_links(state: dict, manifest_files: dict) -> dict[str, str]:
    """Map active source IDs to byte-identical documents observed in Drive."""
    links = {}
    for _, item in sorted(state.get("files", {}).items()):
        status = item.get("status")
        if status == "linked":
            paths = item.get("legacy_paths", [])
        elif status == "imported":
            paths = [item.get("manifest_path")]
        else:
            continue
        checksum = item.get("sha256")
        if not checksum:
            continue
        for path in paths:
            entry = manifest_files.get(path, {})
            if (entry.get("status") == "active" and entry.get("location") == item.get("location")
                    and entry.get("sha256") == checksum):
                links.setdefault(entry["source_id"], f"https://drive.google.com/file/d/{valid_id(item['id'])}/view")
    return links
