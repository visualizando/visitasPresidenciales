from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from pipeline.build_web import build_web_data
from pipeline.discovery import discover, download
from pipeline.models import ManifestEntry, RemoteFile
from pipeline.normalize import stable_id
from pipeline.parsers import ParseFailure, parse_pdf
from pipeline.storage import load_json, utc_now, write_json_atomic, write_partition


def update_dataset(
    *,
    source_base_url: str,
    data_dir: Path,
    web_data_dir: Path,
    min_year: int = 2023,
    quarantine_failures: bool = False,
    mark_missing: bool = True,
    force_locations: set[str] | None = None,
) -> dict[str, int]:
    data_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = data_dir / "manifest.json"
    manifest = load_json(manifest_path, {"version": 1, "generated_at": None, "files": {}})
    previous: dict[str, dict[str, object]] = manifest.setdefault("files", {})
    known_hashes = {
        str(entry.get("sha256"))
        for entry in previous.values()
        if entry.get("sha256") and entry.get("status") != "quarantined"
    }
    manifest_before = json.dumps(manifest, sort_keys=True)
    remote_files = discover(source_base_url, min_year=min_year)
    seen_paths = {item.path for item in remote_files}
    forced = force_locations or set()
    changed = [
        item
        for item in remote_files
        if item.location in forced or _needs_download(item, previous.get(item.path))
    ]
    staging_root = Path(tempfile.mkdtemp(prefix="accesos-update-", dir=data_dir))
    staged_entries: list[tuple[RemoteFile, ManifestEntry, Path]] = []
    quarantined_entries: list[tuple[RemoteFile, ManifestEntry]] = []
    try:
        for remote in changed:
            local_pdf = staging_root / "downloads" / Path(remote.path).name
            sha256 = download(remote, local_pdf)
            old = previous.get(remote.path)
            if not old and remote.location not in forced and sha256 in known_hashes:
                continue
            if (
                old
                and remote.location not in forced
                and old.get("sha256") == sha256
                and old.get("status") != "quarantined"
            ):
                old.update(
                    {
                        "etag": remote.etag,
                        "last_modified": remote.last_modified,
                        "size": remote.size,
                        "status": "active",
                    }
                )
                continue
            source_id = stable_id("src_", remote.path)
            try:
                result = parse_pdf(local_pdf, remote, source_id)
            except ParseFailure as error:
                if not quarantine_failures:
                    raise
                if local_pdf.stat().st_size == 0:
                    failure_parser = "archivo-vacio-v1"
                elif "escaneado" in str(error).lower() or "texto extraíble" in str(error).lower():
                    failure_parser = "pdf-sin-texto-extraible-v1"
                else:
                    failure_parser = "no-legible-o-formato-desconocido-v1"
                quarantined_entries.append(
                    (
                        remote,
                        ManifestEntry(
                            source_id=source_id,
                            url=remote.url,
                            path=remote.path,
                            location=remote.location,
                            year=remote.year,
                            month=remote.month,
                            size=remote.size,
                            etag=remote.etag,
                            last_modified=remote.last_modified,
                            sha256=sha256,
                            parser=failure_parser,
                            record_count=0,
                            status="quarantined",
                            processed_at=utc_now(),
                        ),
                    )
                )
                continue
            partition_relative = (
                Path(remote.location)
                / str(remote.year)
                / f"{remote.month:02d}"
                / f"{source_id}.parquet"
            )
            staged_partition = staging_root / "partitions" / partition_relative
            write_partition(staged_partition, result.records)
            entry = ManifestEntry(
                source_id=source_id,
                url=remote.url,
                path=remote.path,
                location=remote.location,
                year=remote.year,
                month=remote.month,
                size=remote.size,
                etag=remote.etag,
                last_modified=remote.last_modified,
                sha256=sha256,
                parser=result.parser,
                record_count=len(result.records),
                partition=str(partition_relative).replace("\\", "/"),
                processed_at=utc_now(),
            )
            staged_entries.append((remote, entry, staged_partition))
            known_hashes.add(sha256)

        if mark_missing:
            for path, entry in previous.items():
                if path not in seen_paths:
                    entry["status"] = "missing"
        for remote in remote_files:
            if (
                remote.path in previous
                and remote.path in seen_paths
                and previous[remote.path].get("status") != "quarantined"
            ):
                previous[remote.path]["status"] = "active"

        if (
            not staged_entries
            and not quarantined_entries
            and json.dumps(manifest, sort_keys=True) == manifest_before
        ):
            return {"discovered": len(remote_files), "changed": 0}

        for remote, entry, staged_partition in staged_entries:
            final_partition = data_dir / "partitions" / (entry.partition or "")
            final_partition.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged_partition, final_partition)
            old = previous.get(remote.path)
            old_partitions = []
            if old:
                old_partitions = list(old.get("partitions") or [])
                if old.get("partition"):
                    old_partitions.append(old["partition"])
            for old_partition in old_partitions:
                if old_partition == entry.partition:
                    continue
                obsolete = data_dir / "partitions" / str(old_partition)
                if obsolete.exists() and obsolete.resolve().is_relative_to(
                    (data_dir / "partitions").resolve()
                ):
                    obsolete.unlink()
            previous[remote.path] = entry.to_dict()

        for remote, entry in quarantined_entries:
            old = previous.get(remote.path)
            if not old or old.get("status") == "quarantined":
                previous[remote.path] = entry.to_dict()

        manifest["generated_at"] = utc_now()
        write_json_atomic(manifest_path, manifest)
        web_stats = build_web_data(data_dir, web_data_dir)
        return {
            "discovered": len(remote_files),
            "changed": len(staged_entries),
            "quarantined": len(quarantined_entries),
            **web_stats,
        }
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


def _needs_download(remote: RemoteFile, old: dict[str, object] | None) -> bool:
    if not old:
        return True
    if remote.sha256 and remote.sha256 != old.get("sha256"):
        return True
    comparable = (
        ("etag", remote.etag),
        ("last_modified", remote.last_modified),
        ("size", remote.size),
    )
    known = [(key, value) for key, value in comparable if value is not None]
    if not known:
        return True
    return any(old.get(key) != value for key, value in known)
