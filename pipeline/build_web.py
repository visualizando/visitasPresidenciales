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
    for directory in (
        "search/name",
        "search/document",
        "events",
        "cooccurrences",
        "analytics",
        "exports",
    ):
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

    _write_cooccurrences(connection, output / "cooccurrences")
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


def _write_cooccurrences(connection: duckdb.DuckDBPyConnection, directory: Path) -> None:
    connection.execute(
        """
        CREATE TEMP TABLE valid_cooccurrence_intervals AS
        SELECT * FROM (
          SELECT
            entity_id,
            canonical_name,
            document_type,
            document_number,
            location,
            destination,
            trim(regexp_replace(
              upper(strip_accents(trim(destination))), '[^A-Z0-9]+', ' ', 'g'
            )) AS destination_key,
            entered_at,
            exited_at,
            cast(entered_at AS DATE) AS access_date
          FROM records
          WHERE entity_id IS NOT NULL
            AND destination IS NOT NULL
            AND entered_at IS NOT NULL
            AND exited_at IS NOT NULL
            AND datediff('minute', entered_at, exited_at) > 0
            AND datediff('minute', entered_at, exited_at) <= 1440
        ) WHERE destination_key <> ''
        """
    )
    connection.execute(
        """
        CREATE TEMP TABLE coincidence_episodes AS
        WITH interval_matches AS (
          SELECT
            a.entity_id AS left_id,
            b.entity_id AS right_id,
            a.access_date,
            a.location,
            a.destination_key,
            CASE WHEN length(a.destination) >= length(b.destination)
              THEN a.destination ELSE b.destination END AS destination_label,
            greatest(a.entered_at, b.entered_at) AS overlap_start,
            least(a.exited_at, b.exited_at) AS overlap_end,
            datediff(
              'minute',
              greatest(a.entered_at, b.entered_at),
              least(a.exited_at, b.exited_at)
            )::INTEGER AS overlap_minutes
          FROM valid_cooccurrence_intervals a
          JOIN valid_cooccurrence_intervals b
            ON a.location = b.location
           AND a.access_date = b.access_date
           AND a.destination_key = b.destination_key
           AND a.entity_id < b.entity_id
           AND a.entered_at < b.exited_at
           AND b.entered_at < a.exited_at
          WHERE datediff(
            'minute',
            greatest(a.entered_at, b.entered_at),
            least(a.exited_at, b.exited_at)
          ) >= 10
        )
        SELECT
          left_id,
          right_id,
          access_date,
          location,
          destination_key,
          arg_max(destination_label, overlap_minutes) AS destination_label,
          max(overlap_minutes)::INTEGER AS overlap_minutes,
          arg_max(overlap_start, overlap_minutes) AS overlap_start,
          arg_max(overlap_end, overlap_minutes) AS overlap_end,
          (
            destination_key NOT IN (
              'BALCARCE 24', 'RIVADAVIA 250', 'YRIGOYEN 219', 'SP',
              'S P', 'CASA ROSADA', 'QUINTA DE OLIVOS'
            ) AND length(destination_key) > 3
          ) AS specific_destination
        FROM interval_matches
        GROUP BY left_id, right_id, access_date, location, destination_key
        """
    )
    connection.execute(
        """
        CREATE TEMP TABLE coincidence_people AS
        SELECT
          entity_id,
          arg_max(canonical_name, coalesce(occurred_at, entered_at, exited_at)) AS canonical_name,
          arg_max(document_type, coalesce(occurred_at, entered_at, exited_at)) AS document_type,
          arg_max(document_number, coalesce(occurred_at, entered_at, exited_at)) AS document_number
        FROM records GROUP BY entity_id
        """
    )
    connection.execute(
        """
        CREATE TEMP TABLE directional_coincidences AS
        SELECT
          left_id AS person_id,
          right_id AS other_id,
          access_date,
          location,
          destination_label,
          overlap_minutes,
          overlap_start,
          overlap_end,
          specific_destination,
          substr(md5(left_id), 1, 2) AS shard
        FROM coincidence_episodes
        UNION ALL
        SELECT
          right_id,
          left_id,
          access_date,
          location,
          destination_label,
          overlap_minutes,
          overlap_start,
          overlap_end,
          specific_destination,
          substr(md5(right_id), 1, 2) AS shard
        FROM coincidence_episodes
        """
    )

    shard_counts: dict[str, int] = {}
    prefixes = [
        row[0]
        for row in connection.execute(
            "SELECT DISTINCT shard FROM directional_coincidences ORDER BY shard"
        ).fetchall()
    ]
    for prefix in prefixes:
        rows = _rows(
            connection,
            """
            SELECT
              d.person_id,
              d.other_id,
              p.canonical_name,
              p.document_type,
              p.document_number,
              d.access_date,
              d.location,
              d.destination_label,
              d.overlap_minutes,
              d.specific_destination,
              strftime(d.overlap_start, '%H:%M') AS overlap_start,
              strftime(d.overlap_end, '%H:%M') AS overlap_end
            FROM directional_coincidences d
            JOIN coincidence_people p ON p.entity_id = d.other_id
            WHERE d.shard = ?
            ORDER BY d.person_id, d.access_date DESC, d.overlap_minutes DESC
            """,
            [prefix],
        )
        payload: dict[str, dict[str, Any]] = {}
        destination_indexes: dict[str, dict[str, int]] = defaultdict(dict)
        for row in rows:
            person_id = row["person_id"]
            owner = payload.setdefault(person_id, {"d": [], "p": {}, "e": []})
            other_id = row["other_id"]
            owner["p"].setdefault(
                other_id,
                [row["canonical_name"], row["document_type"], row["document_number"]],
            )
            destinations = destination_indexes[person_id]
            destination = row["destination_label"]
            destination_index = destinations.get(destination)
            if destination_index is None:
                destination_index = len(owner["d"])
                destinations[destination] = destination_index
                owner["d"].append(destination)
            owner["e"].append(
                [
                    other_id,
                    str(row["access_date"]),
                    0 if row["location"] == "casa-rosada" else 1,
                    destination_index,
                    row["overlap_minutes"],
                    1 if row["specific_destination"] else 0,
                    row["overlap_start"],
                    row["overlap_end"],
                ]
            )
        _write_compact(directory / f"{prefix}.json", payload)
        shard_counts[prefix] = len(rows)

    episode_count = connection.execute("SELECT count(*) FROM coincidence_episodes").fetchone()[0]
    people_count = connection.execute(
        "SELECT count(DISTINCT person_id) FROM directional_coincidences"
    ).fetchone()[0]
    _write_compact(
        directory / "meta.json",
        {
            "version": 1,
            "episode_count": episode_count,
            "people_count": people_count,
            "minimum_overlap_minutes": 10,
            "maximum_interval_minutes": 1440,
            "shards": shard_counts,
        },
    )


def _write_exports(connection: duckdb.DuckDBPyConnection, directory: Path) -> list[dict[str, Any]]:
    groups = connection.execute(
        """
        SELECT year(coalesce(occurred_at, entered_at, exited_at))::INTEGER AS year,
               count(*)::INTEGER AS records
        FROM records WHERE coalesce(occurred_at, entered_at, exited_at) IS NOT NULL
        GROUP BY ALL ORDER BY year
        """
    ).fetchall()
    exports: list[dict[str, Any]] = []
    for year, count in groups:
        relative = Path(f"{year}.csv.gz")
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        query = (
            "SELECT * FROM records WHERE "
            "year(coalesce(occurred_at, entered_at, exited_at)) = ? "
            "ORDER BY coalesce(occurred_at, entered_at, exited_at)"
        )
        columns = [
            item[0]
            for item in connection.execute(query + " LIMIT 0", [year]).description
        ]
        cursor = connection.execute(query, [year])
        with gzip.open(target, "wt", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            while batch := cursor.fetchmany(10_000):
                writer.writerows(batch)
        exports.append(
            {
                "year": year,
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
    _write_compact(
        output / "cooccurrences" / "meta.json",
        {
            "version": 1,
            "episode_count": 0,
            "people_count": 0,
            "minimum_overlap_minutes": 10,
            "maximum_interval_minutes": 1440,
            "shards": {},
        },
    )


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
