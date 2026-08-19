from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from pipeline.models import AccessRecord


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def write_partition(path: Path, records: list[AccessRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Arrow accepts Python datetime values directly. The JSON-facing serializer
    # intentionally emits ISO strings, so storage uses the dataclass values.
    rows = [asdict(record) for record in records]
    schema = access_schema()
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, path, compression="zstd", compression_level=10)


def access_schema() -> pa.Schema:
    return pa.schema(
        [
            ("record_id", pa.string()),
            ("entity_id", pa.string()),
            ("canonical_name", pa.string()),
            ("document_type", pa.string()),
            ("document_number", pa.string()),
            ("location", pa.string()),
            ("record_type", pa.string()),
            ("source_id", pa.string()),
            ("source_url", pa.string()),
            ("source_path", pa.string()),
            ("source_page", pa.int32()),
            ("occurred_at", pa.timestamp("us")),
            ("entered_at", pa.timestamp("us")),
            ("exited_at", pa.timestamp("us")),
            ("direction", pa.string()),
            ("device", pa.string()),
            ("destination", pa.string()),
            ("purpose", pa.string()),
            ("activity", pa.string()),
            ("authorized_by", pa.string()),
            ("access_status", pa.string()),
            ("quality", pa.string()),
            ("raw_text", pa.string()),
        ]
    )


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
