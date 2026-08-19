from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import shutil
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
from rapidfuzz.fuzz import token_set_ratio

from pipeline.normalize import fold_text
from pipeline.storage import load_json, utc_now


def build_web_data(data_dir: Path, output_dir: Path) -> dict[str, int]:
    partitions = sorted((data_dir / "partitions").rglob("*.parquet"))
    output_parent = output_dir.parent
    output_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="web-data-", dir=output_parent))
    try:
        stats = _build_into(data_dir, partitions, staging)
        _replace_directory(staging, output_dir)
        return stats
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _build_into(data_dir: Path, partitions: list[Path], output: Path) -> dict[str, int]:
    for directory in ("search/name", "search/document", "events", "analytics", "exports"):
        (output / directory).mkdir(parents=True, exist_ok=True)
    generated_at = utc_now()
    if not partitions:
        _write_empty(output, generated_at)
        return {"records": 0, "people": 0, "exports": 0}

    connection = duckdb.connect(":memory:")
    parquet_files = ",".join(f"'{_sql_path(path)}'" for path in partitions)
    connection.execute(
        f"CREATE VIEW raw_records AS SELECT * FROM read_parquet([{parquet_files}], union_by_name=true)"
    )
    connection.execute("CREATE TEMP TABLE identity_merges(old_id VARCHAR, canonical_id VARCHAR)")
    curation = load_json(data_dir / "curation" / "entity_merges.json", {"merges": []})
    merge_rows = [
        (item["from"], item["into"])
        for item in curation.get("merges", [])
        if isinstance(item, dict) and item.get("from") and item.get("into")
    ]
    if merge_rows:
        connection.executemany("INSERT INTO identity_merges VALUES (?, ?)", merge_rows)
    connection.execute(
        """
        CREATE VIEW merged_records AS
        SELECT r.* EXCLUDE(entity_id), coalesce(m.canonical_id, r.entity_id) AS entity_id
        FROM raw_records r LEFT JOIN identity_merges m ON r.entity_id = m.old_id
        """
    )
    connection.execute(
        """
        CREATE TABLE records AS
        SELECT * EXCLUDE(row_number) FROM (
          SELECT *, row_number() OVER (
            PARTITION BY record_id ORDER BY source_path, source_page
          ) AS row_number
          FROM merged_records
        ) WHERE row_number = 1
        """
    )

    people_rows = _rows(
        connection,
        """
        SELECT
          entity_id,
          arg_max(canonical_name, coalesce(occurred_at, entered_at, exited_at)) AS canonical_name,
          arg_max(document_type, coalesce(occurred_at, entered_at, exited_at)) AS document_type,
          arg_max(document_number, coalesce(occurred_at, entered_at, exited_at)) AS document_number,
          count(*)::INTEGER AS record_count,
          min(coalesce(occurred_at, entered_at, exited_at)) AS first_seen,
          max(coalesce(occurred_at, entered_at, exited_at)) AS last_seen,
          list_sort(list_distinct(list(location))) AS locations,
          list_sort(list_distinct(list(record_type))) AS record_types
        FROM records GROUP BY entity_id ORDER BY canonical_name
        """,
    )
    people: list[dict[str, Any]] = []
    for row in people_rows:
        row["first_seen"] = _json_datetime(row["first_seen"])
        row["last_seen"] = _json_datetime(row["last_seen"])
        row["event_shard"] = _entity_shard(row["entity_id"])
        row["normalized_name"] = fold_text(row["canonical_name"])
        row["search_tokens"] = sorted(set(row["normalized_name"].split()))
        people.append(row)

    name_shards: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    document_shards: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for person in people:
        summary = {key: value for key, value in person.items() if key != "search_tokens"}
        keys = {token[0].lower() for token in person["search_tokens"] if token}
        for key in keys or {"_"}:
            name_shards[_safe_shard(key)][person["entity_id"]] = summary
        document = person.get("document_number") or ""
        if document:
            document_shards[(document[:2] or "_")][person["entity_id"]] = summary

    for key, values in name_shards.items():
        _write_compact(output / "search" / "name" / f"{key}.json", list(values.values()))
    for key, values in document_shards.items():
        _write_compact(output / "search" / "document" / f"{key}.json", list(values.values()))

    event_counts: dict[str, int] = {}
    for prefix in sorted({_entity_shard(person["entity_id"]) for person in people}):
        rows = _rows(
            connection,
            """
            SELECT
              r.*,
              (SELECT list(struct_pack(url := s.source_url, path := s.source_path, page := s.source_page))
               FROM merged_records s WHERE s.record_id = r.record_id) AS sources
            FROM records r WHERE substr(md5(entity_id), 1, 2) = ?
            ORDER BY coalesce(occurred_at, entered_at, exited_at) DESC NULLS LAST
            """,
            [prefix],
        )
        for row in rows:
            for key in ("occurred_at", "entered_at", "exited_at"):
                row[key] = _json_datetime(row[key])
        _write_compact(output / "events" / f"{prefix}.json", rows)
        event_counts[prefix] = len(rows)

    analytics = _build_analytics(connection)
    _write_compact(output / "analytics" / "overview.json", analytics)
    exports = _write_exports(connection, output / "exports")
    _write_compact(output / "exports" / "index.json", exports)

    search_meta = {
        "version": 1,
        "generated_at": generated_at,
        "people_count": len(people),
        "name_shards": sorted(name_shards),
        "document_shards": sorted(document_shards),
        "event_shards": event_counts,
    }
    _write_compact(output / "search" / "meta.json", search_meta)
    record_count = connection.execute("SELECT count(*) FROM records").fetchone()[0]
    source_manifest = load_json(data_dir / "manifest.json", {"files": {}})
    active_sources = [
        item for item in source_manifest.get("files", {}).values() if item.get("status") == "active"
    ]
    meta = {
        "version": 1,
        "generated_at": generated_at,
        "record_count": record_count,
        "people_count": len(people),
        "source_count": len(active_sources),
        "first_date": analytics["coverage"].get("first_date"),
        "last_date": analytics["coverage"].get("last_date"),
        "locations": ["casa-rosada", "olivos"],
        "is_demo": False,
    }
    _write_compact(output / "meta.json", meta)
    _write_candidates(data_dir / "curation" / "candidates.csv", people)
    connection.close()
    return {"records": record_count, "people": len(people), "exports": len(exports)}


def _build_analytics(connection: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    date_expr = "coalesce(occurred_at, entered_at, exited_at)"
    daily = _rows(
        connection,
        f"""
        SELECT strftime({date_expr}, '%Y-%m-%d') AS date, location, record_type,
               count(*)::INTEGER AS records, count(DISTINCT entity_id)::INTEGER AS people
        FROM records WHERE {date_expr} IS NOT NULL GROUP BY ALL ORDER BY date
        """,
    )
    monthly = _rows(
        connection,
        f"""
        SELECT strftime({date_expr}, '%Y-%m') AS month, location,
               count(*)::INTEGER AS records, count(DISTINCT entity_id)::INTEGER AS people
        FROM records WHERE {date_expr} IS NOT NULL GROUP BY ALL ORDER BY month
        """,
    )
    heatmap = _rows(
        connection,
        f"""
        SELECT location, dayofweek({date_expr})::INTEGER AS weekday,
               hour({date_expr})::INTEGER AS hour, count(*)::INTEGER AS records
        FROM records WHERE {date_expr} IS NOT NULL GROUP BY ALL ORDER BY location, weekday, hour
        """,
    )
    purposes = _rows(
        connection,
        """
        SELECT location, coalesce(nullif(purpose, ''), nullif(destination, '')) AS label,
               count(*)::INTEGER AS records
        FROM records WHERE coalesce(nullif(purpose, ''), nullif(destination, '')) IS NOT NULL
        GROUP BY ALL ORDER BY records DESC LIMIT 30
        """,
    )
    coverage = connection.execute(
        f"SELECT min({date_expr}), max({date_expr}) FROM records"
    ).fetchone()
    return {
        "daily": daily,
        "monthly": monthly,
        "heatmap": heatmap,
        "purposes": purposes,
        "coverage": {
            "first_date": _json_datetime(coverage[0]),
            "last_date": _json_datetime(coverage[1]),
        },
    }


def _write_exports(connection: duckdb.DuckDBPyConnection, directory: Path) -> list[dict[str, Any]]:
    groups = connection.execute(
        """
        SELECT location,
               year(coalesce(occurred_at, entered_at, exited_at))::INTEGER AS year,
               month(coalesce(occurred_at, entered_at, exited_at))::INTEGER AS month,
               count(*)::INTEGER AS records
        FROM records WHERE coalesce(occurred_at, entered_at, exited_at) IS NOT NULL
        GROUP BY ALL ORDER BY location, year, month
        """
    ).fetchall()
    exports: list[dict[str, Any]] = []
    for location, year, month, count in groups:
        relative = Path(location) / str(year) / f"{month:02d}.csv.gz"
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        query = (
            "SELECT * FROM records WHERE location = ? AND "
            "year(coalesce(occurred_at, entered_at, exited_at)) = ? AND "
            "month(coalesce(occurred_at, entered_at, exited_at)) = ? "
            "ORDER BY coalesce(occurred_at, entered_at, exited_at)"
        )
        columns = [
            item[0]
            for item in connection.execute(query + " LIMIT 0", [location, year, month]).description
        ]
        cursor = connection.execute(query, [location, year, month])
        with gzip.open(target, "wt", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            while batch := cursor.fetchmany(10_000):
                writer.writerows(batch)
        exports.append(
            {
                "location": location,
                "year": year,
                "month": month,
                "records": count,
                "path": str(relative).replace("\\", "/"),
            }
        )
    return exports


def _write_candidates(path: Path, people: list[dict[str, Any]]) -> None:
    blocks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for person in people:
        tokens = person["normalized_name"].split()
        if tokens:
            blocks[tokens[-1][:2]].append(person)
    rows: list[tuple[str, str, int, str, str]] = []
    for block in blocks.values():
        for index, left in enumerate(block):
            for right in block[index + 1 :]:
                if left.get("document_number") and right.get("document_number"):
                    continue
                score = int(token_set_ratio(left["normalized_name"], right["normalized_name"]))
                if score >= 88:
                    rows.append(
                        (
                            left["entity_id"],
                            right["entity_id"],
                            score,
                            left["canonical_name"],
                            right["canonical_name"],
                        )
                    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["left_entity_id", "right_entity_id", "score", "left_name", "right_name"])
        writer.writerows(sorted(rows, key=lambda row: (-row[2], row[3], row[4])))


def _write_empty(output: Path, generated_at: str) -> None:
    _write_compact(
        output / "meta.json",
        {
            "version": 1,
            "generated_at": generated_at,
            "record_count": 0,
            "people_count": 0,
            "source_count": 0,
            "first_date": None,
            "last_date": None,
            "locations": ["casa-rosada", "olivos"],
            "is_demo": False,
        },
    )
    _write_compact(
        output / "search" / "meta.json",
        {
            "version": 1,
            "generated_at": generated_at,
            "people_count": 0,
            "name_shards": [],
            "document_shards": [],
            "event_shards": {},
        },
    )
    _write_compact(
        output / "analytics" / "overview.json",
        {
            "daily": [],
            "monthly": [],
            "heatmap": [],
            "purposes": [],
            "coverage": {"first_date": None, "last_date": None},
        },
    )
    _write_compact(output / "exports" / "index.json", [])


def _rows(
    connection: duckdb.DuckDBPyConnection, query: str, params: list[Any] | None = None
) -> list[dict[str, Any]]:
    cursor = connection.execute(query, params or [])
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _write_compact(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str), encoding="utf-8"
    )


def _replace_directory(staging: Path, target: Path) -> None:
    backup = target.with_name(target.name + ".previous")
    if backup.exists():
        shutil.rmtree(backup)
    if target.exists():
        os.replace(target, backup)
    try:
        os.replace(staging, target)
    except Exception:
        if backup.exists():
            os.replace(backup, target)
        raise
    shutil.rmtree(backup, ignore_errors=True)


def _entity_shard(entity_id: str) -> str:
    return hashlib.md5(entity_id.encode(), usedforsecurity=False).hexdigest()[:2]


def _safe_shard(value: str) -> str:
    return value if value.isascii() and value.isalnum() else "_"


def _sql_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "''")


def _json_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat().replace("+00:00", "Z")
    return str(value)
