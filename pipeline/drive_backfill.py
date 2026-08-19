from __future__ import annotations

import re
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

FOLDER_URL = "https://drive.google.com/drive/folders/{folder_id}"
DOWNLOAD_URL = "https://drive.usercontent.google.com/download"


def download_public_folder(folder_id: str, output: Path) -> dict[str, int]:
    """Download every public PDF in a Google Drive folder tree."""
    output.mkdir(parents=True, exist_ok=True)
    stats = {"folders": 0, "pdfs": 0, "existing": 0, "failed": 0}
    visited: set[str] = set()
    with httpx.Client(follow_redirects=True, timeout=120) as client:
        _download_folder(client, folder_id, output, visited, stats)
    return stats


def _download_folder(
    client: httpx.Client,
    folder_id: str,
    output: Path,
    visited: set[str],
    stats: dict[str, int],
) -> None:
    if folder_id in visited:
        return
    visited.add(folder_id)
    output.mkdir(parents=True, exist_ok=True)
    stats["folders"] += 1

    response = client.get(FOLDER_URL.format(folder_id=folder_id))
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    entries: dict[str, str] = {}
    for element in soup.select("[data-id][data-tooltip]"):
        item_id = str(element.get("data-id", ""))
        tooltip = str(element.get("data-tooltip", ""))
        if item_id and tooltip:
            entries[item_id] = tooltip

    for item_id, tooltip in entries.items():
        if tooltip.endswith(" Shared folder"):
            name = tooltip.removesuffix(" Shared folder")
            _download_folder(client, item_id, output / _safe_name(name), visited, stats)
        elif tooltip.lower().endswith(".pdf pdf"):
            name = tooltip[:-4]
            target = output / _safe_name(name)
            if target.exists() and target.stat().st_size > 4:
                stats["existing"] += 1
                continue
            try:
                with client.stream(
                    "GET",
                    DOWNLOAD_URL,
                    params={"id": item_id, "export": "download", "confirm": "t"},
                ) as download:
                    download.raise_for_status()
                    with target.open("wb") as destination:
                        for chunk in download.iter_bytes():
                            destination.write(chunk)
            except httpx.HTTPError:
                target.unlink(missing_ok=True)
                stats["failed"] += 1
                continue
            if target.read_bytes()[:4] != b"%PDF":
                target.unlink(missing_ok=True)
                stats["failed"] += 1
                continue
            stats["pdfs"] += 1


def _safe_name(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", value).strip().rstrip(".")
    return cleaned or "sin-nombre"
