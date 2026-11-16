"""Prepare a complete candidate generation; never mutate the input dataset.

GitHub Actions validates the candidate before promoting it and committing. Remote
deletions never delete history. Parser failures retain the last valid version.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import httpx

from pipeline.drive_sync import (
    DEFAULT_SOURCES,
    EXTENSIONS,
    DriveRequestError,
    drive_issue_counts,
    fetch_version,
    inventory,
    valid_id,
    verified_source_links,
)
from pipeline.historical_office_import import (
    _empty_source_reason,
    _parse_docx,
    _parse_xls,
    _parse_xlsx,
    _source_period,
)
from pipeline.models import RemoteFile
from pipeline.normalize import fold_text, stable_id
from pipeline.parsers import ParseFailure, parse_pdf
from pipeline.storage import load_json, utc_now, write_json_atomic, write_partition

REVISION = "drive-parsers-v1"
STATE = "drive/state.json"


def safe_parts(path: str) -> Path:
    parts = [re.sub(r'[<>:"\\|?*]', "_", part).rstrip(". ") for part in path.split("/")]
    if not parts or any(not part or part in {".", ".."} for part in parts):
        raise ValueError("Invalid source path")
    return Path(*parts)


def scan_sources(data_dir: Path, raw: Path, api_key: str | None) -> list[dict]:
    state = load_json(data_dir / STATE, {"files": {}})["files"]
    observations = []
    pending = []
    with httpx.Client(
        follow_redirects=True,
        timeout=180,
        headers={"Accept-Language": "en-US"},
    ) as client:
        for location, folder in DEFAULT_SOURCES.items():
            listing = inventory(client, folder, api_key)
            if not listing["files"]:
                raise ValueError(f"Empty/unreadable root: {location}")
            # HTML pagination cannot be certified: never silently truncate it.
            if any(w.get("visible_entries", 0) >= 50 for w in listing["warnings"]):
                raise ValueError("Incomplete listing")
            for item in listing["files"]:
                key = f"{folder}/{valid_id(item['id'])}"
                old = state.get(key, {})
                observed = {**item, "location": location, "folder_id": folder}
                # A persisted API checksum suffices for already processed content;
                # cache eviction must not force reparsing historical files.
                if (
                    item.get("md5Checksum")
                    and item["md5Checksum"] == old.get("md5Checksum")
                    and old.get("parser_revision") == REVISION
                ):
                    observed.update(sha256=old.get("sha256"), comparison="unchanged_remote")
                else:
                    pending.append(observed)
                    continue
                observations.append(observed)

        def fetch(item):
            item.update(fetch_version(client, item, raw, allow_invalid=True))
            if item.get("raw_path"):
                item["local_path"] = str(raw / item["raw_path"])
            return item

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(fetch, item) for item in pending]
            try:
                for future in as_completed(futures):
                    observations.append(future.result())
            finally:
                for future in futures:
                    future.cancel()
    return observations


def parse_source(item: dict, scratch: Path, source_id: str):
    logical = Path(item["location"]) / safe_parts(item["path"])
    local = scratch / valid_id(item["id"]) / logical
    local.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(item["local_path"], local)
    year, month = _source_period(logical)
    if not year:
        years = re.findall(r"20\d{2}", item["path"])
        year = int(years[-1]) if years else 0
    source_path = f"drive/{item['folder_id']}/{item['id']}/{logical.as_posix()}"
    suffix = local.suffix.lower()
    if suffix == ".pdf":
        if not year:
            raise ParseFailure("No se pudo identificar el año de la fuente")
        remote = RemoteFile(item["url"], source_path, item["location"], year, month)
        result = parse_pdf(local, remote, source_id)
        records, parser = result.records, result.parser
    else:
        diagnostics = defaultdict(int)
        if suffix == ".xlsx":
            records = _parse_xlsx(local, source_path, source_id, item["location"], diagnostics)
        elif item["location"] == "olivos" and suffix == ".xls":
            records = _parse_xls(local, source_path, source_id, diagnostics)
        elif item["location"] == "olivos" and suffix == ".docx":
            records = _parse_docx(local, source_path, source_id, diagnostics)
        else:
            raise ParseFailure("Formato/sede sin parser validado")
        parser = f"{item['location']}-{suffix[1:]}-{REVISION}"
        if not records and _empty_source_reason(local) != "sin_novedad":
            raise ParseFailure("Planilla sin registros extraíbles")
    for record in records:
        timestamps = [t for t in (record.occurred_at, record.entered_at, record.exited_at) if t]
        if not timestamps or any(
            not 2000 <= t.year <= datetime.now(UTC).year + 1 for t in timestamps
        ):
            raise ParseFailure("Registro sin fecha o con fecha fuera de rango")
        if not record.entity_id or record.location != item["location"]:
            raise ParseFailure("Identidad o sede inválida")
        record.source_url = item["url"]
        record.source_path = source_path
    return records, parser, year, month


def event_key(row: dict) -> tuple:
    logical = row.get("occurred_at") or row.get("entered_at") or row.get("exited_at")
    return (
        row["entity_id"],
        row["location"],
        row["record_type"],
        logical.isoformat() if logical else "",
        row["exited_at"].isoformat() if row.get("exited_at") else "",
        fold_text(row.get("direction") or ""),
        fold_text(row.get("device") or ""),
        fold_text(row.get("destination") or ""),
    )


class Reconciler:
    def __init__(self, partitions: Path):
        self.partitions = partitions
        self.maps = {}

    def reconcile(self, records) -> tuple[int, int]:
        matched = new = 0
        for record in records:
            date = record.occurred_at or record.entered_at or record.exited_at
            period = (record.location, date.year)
            if period not in self.maps:
                paths = sorted((self.partitions / period[0]).rglob("*.parquet"))
                mapping = {}
                if paths:
                    with duckdb.connect() as connection:
                        cursor = connection.execute(
                            "SELECT record_id, entity_id, location, record_type, occurred_at, entered_at, "
                            "exited_at, direction, device, destination FROM read_parquet(?) "
                            "WHERE year(coalesce(occurred_at, entered_at, exited_at)) = ? ORDER BY record_id",
                            [[str(p) for p in paths], period[1]],
                        )
                        names = [c[0] for c in cursor.description]
                        while rows := cursor.fetchmany(10000):
                            for values in rows:
                                row = dict(zip(names, values, strict=True))
                                mapping.setdefault(event_key(row), row["record_id"])
                self.maps[period] = mapping
            mapping = self.maps[period]
            key = event_key(asdict(record))
            if key in mapping:
                record.record_id = mapping[key]
                matched += 1
            else:
                record.record_id = stable_id("rec_", *key)
                mapping[key] = record.record_id
                new += 1
        return matched, new


def validate_partitions(data_dir: Path, manifest: dict) -> None:
    root = (data_dir / "partitions").resolve()
    for entry in manifest["files"].values():
        references = entry.get("partitions") or (
            [entry["partition"]] if entry.get("partition") else []
        )
        if entry.get("record_count", 0) and not references:
            raise ValueError("Source with records has no partition reference")
        for relative in references:
            path = (root / relative).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError("Missing or unsafe canonical partition")


def prepare_update(data_dir: Path, work: Path, observations: list[dict]) -> dict:
    data_dir, work = data_dir.resolve(), work.resolve()
    if work.exists() or work == data_dir or work.is_relative_to(data_dir):
        raise ValueError("Use a new work directory outside the input data directory")
    candidate = work / "data"
    manifest = load_json(data_dir / "manifest.json", {"version": 1, "files": {}})
    validate_partitions(data_dir, manifest)
    candidate.mkdir(parents=True)
    for name in ("partitions", "curation"):
        if (data_dir / name).exists():
            shutil.copytree(data_dir / name, candidate / name)
    for path in data_dir.glob("audiencias*"):
        if path.is_file():
            shutil.copy2(path, candidate / path.name)
    files = manifest["files"]
    state = load_json(data_dir / STATE, {"version": 1, "files": {}})
    previous_drive_issues = drive_issue_counts(state)
    previous_source_links = verified_source_links(state, files)
    known = defaultdict(list)
    for path, entry in files.items():
        if entry.get("sha256"):
            known[(entry["location"], entry["sha256"])].append(path)
    reconciler = Reconciler(data_dir / "partitions")
    counts = Counter()
    failures = []
    manifest_changed = False
    for item in sorted(
        observations, key=lambda value: (value["location"], value["path"], value["id"])
    ):
        valid_id(item["id"])
        valid_id(item["folder_id"])
        key = f"{item['folder_id']}/{item['id']}"
        old_state = state["files"].get(key, {})
        metadata = {
            k: item[k]
            for k in (
                "id",
                "folder_id",
                "location",
                "name",
                "path",
                "sha256",
                "md5Checksum",
                "modifiedTime",
            )
            if k in item
        }
        metadata["parser_revision"] = REVISION
        if item.get("comparison") == "unchanged_remote" or (
            item.get("sha256")
            and item["sha256"] == old_state.get("sha256")
            and old_state.get("parser_revision") == REVISION
        ):
            counts["unchanged"] += 1
            state["files"][key] = {**old_state, **metadata}
            continue
        if (
            item["name"].startswith(("~$", "_$"))
            or Path(item["name"]).suffix.lower() not in EXTENSIONS
        ):
            state["files"][key] = {**metadata, "status": "ignored"}
            counts["ignored"] += 1
            continue
        matches = (
            known.get((item["location"], item.get("sha256")), []) if item.get("size") != 0 else []
        )
        if matches and not old_state.get("manifest_path"):
            state["files"][key] = {**metadata, "status": "linked", "legacy_paths": matches}
            counts["linked"] += 1
            continue
        manifest_path = old_state.get("manifest_path") or f"drive/{key}"
        # Adopt a unique historical source on replacement, never guess among aliases.
        if old_state.get("status") == "linked" and old_state.get("sha256") != item.get("sha256"):
            paths = old_state.get("legacy_paths", [])
            if len(paths) == 1:
                manifest_path = paths[0]
            else:
                failures.append(
                    {
                        "id": item["id"],
                        "path": item["path"],
                        "reason": "ambiguous_legacy_replacement",
                    }
                )
                state["files"][key] = {
                    **old_state, **metadata, "status": "quarantined", "reason": "ambiguous_legacy_replacement"
                }
                counts["quarantined"] += 1
                continue
        previous = files.get(manifest_path)
        source_id = previous["source_id"] if previous else stable_id("src_", "drive", key)
        if item.get("local_path"):
            with Path(item["local_path"]).open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != item["sha256"]:
                    raise ValueError("Local checksum mismatch")
        try:
            if item.get("comparison") in {"empty_file", "invalid_file", "invalid_office_file"}:
                raise ParseFailure(item["comparison"])
            records, parser, year, month = parse_source(item, work / "sources", source_id)
        except Exception as error:
            reason = type(error).__name__ + ": " + str(error)[:300]
            failures.append({"id": item["id"], "path": item["path"], "reason": reason})
            state["files"][key] = {
                **old_state,
                **metadata,
                "status": "quarantined",
                "manifest_path": manifest_path,
                "reason": reason,
            }
            counts["quarantined"] += 1
            continue
        matched, new = reconciler.reconcile(records)
        counts.update(
            parsed_sources=1, parsed_records=len(records), matched_records=matched, new_records=new
        )
        grouped = defaultdict(list)
        for record in records:
            date = record.occurred_at or record.entered_at or record.exited_at
            grouped[(date.year, date.month)].append(record)
        partitions = []
        for (record_year, record_month), rows in sorted(grouped.items()):
            relative = f"{item['location']}/{record_year}/{record_month:02d}/{source_id}.parquet"
            write_partition(candidate / "partitions" / relative, rows)
            partitions.append(relative)
        if previous:
            obsolete = previous.get("partitions") or (
                [previous["partition"]] if previous.get("partition") else []
            )
            for relative in obsolete:
                path = (candidate / "partitions" / relative).resolve()
                if not path.is_relative_to((candidate / "partitions").resolve()):
                    raise ValueError("Unsafe partition reference")
                if relative not in partitions:
                    path.unlink(missing_ok=True)
        files[manifest_path] = {
            "source_id": source_id,
            "url": item["url"],
            "path": manifest_path,
            "location": item["location"],
            "year": year,
            "month": month,
            "sha256": item["sha256"],
            "size": item.get("size"),
            "parser": parser,
            "status": "active",
            "record_count": len(records),
            "partitions": partitions,
            "partition": None,
            "processed_at": utc_now(),
        }
        known[(item["location"], item["sha256"])].append(manifest_path)
        state["files"][key] = {**metadata, "status": "imported", "manifest_path": manifest_path}
        manifest_changed = True
    if manifest_changed:
        manifest["generated_at"] = utc_now()
    state["last_checked_at"] = utc_now()
    write_json_atomic(candidate / "manifest.json", manifest)
    write_json_atomic(candidate / STATE, state)
    validate_partitions(candidate, manifest)
    report = {
        "counts": dict(counts),
        "quarantine": failures,
        "data_changed": manifest_changed,
        "coverage_changed": previous_drive_issues != drive_issue_counts(state),
        "source_links_changed": previous_source_links != verified_source_links(state, files),
        "candidate": str(candidate),
        "observed_files": len(observations),
    }
    write_json_atomic(work / "report.json", report)
    return report


def promote_candidate(candidate: Path, data_dir: Path) -> None:
    """Roll back local promotion on failure; Actions commits only validated output."""
    candidate, data_dir = candidate.resolve(), data_dir.resolve()
    if candidate == data_dir or candidate.is_relative_to(data_dir):
        raise ValueError("Candidate must be outside the live data directory")
    report = load_json(candidate.parent / "report.json", {})
    if "data_changed" not in report:
        raise ValueError("Missing completed candidate report")
    names = [STATE]
    if report["data_changed"]:
        names += ["partitions", "manifest.json"]
    if any(not (candidate / name).exists() for name in names):
        raise ValueError("Incomplete candidate")
    backup = candidate.parent / "backup"
    backup.mkdir()
    moved = []
    try:
        for index, name in enumerate(names):
            source, target = candidate / name, data_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            old = backup / str(index)
            existed = target.exists()
            if existed:
                os.replace(target, old)
            try:
                os.replace(source, target)
            except Exception:
                if existed:
                    os.replace(old, target)
                raise
            moved.append((source, target, old, existed))
    except Exception:
        for source, target, old, existed in reversed(moved):
            os.replace(target, source)
            if existed:
                os.replace(old, target)
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Prepara novedades de Drive sin modificar la base de entrada"
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--work-dir", type=Path, default=Path(".drive-update"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/drive/raw"))
    parser.add_argument(
        "--audit-dir", type=Path, help="Reproducir la auditoría local descargada (sin red)"
    )
    parser.add_argument("--promote", type=Path, help="Promover un candidato ya validado")
    args = parser.parse_args()
    if args.promote:
        promote_candidate(args.promote, args.data_dir)
        return
    if args.work_dir.exists():
        raise SystemExit("La carpeta de trabajo ya existe; usar una nueva")
    if args.audit_dir:
        observations = []
        for location, folder in DEFAULT_SOURCES.items():
            for item in load_json(args.audit_dir / f"{location}-comparison.json", []):
                item.update(location=location, folder_id=folder)
                if item.get("raw_path"):
                    item["local_path"] = str(args.raw_dir / item["raw_path"])
                observations.append(item)
    else:
        try:
            observations = scan_sources(
                args.data_dir, args.raw_dir, os.getenv("GOOGLE_DRIVE_API_KEY")
            )
        except DriveRequestError as error:
            raise SystemExit(
                f"Falló la conexión con Drive ({error}); no se publicaron cambios"
            ) from None
    report = prepare_update(args.data_dir, args.work_dir, observations)
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "quarantine"}, ensure_ascii=False, indent=2
        )
    )


if __name__ == "__main__":
    main()
