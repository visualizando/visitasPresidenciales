from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from pipeline.build_web import build_web_data
from pipeline.discovery import discover
from pipeline.legacy_import import import_legacy_tsv
from pipeline.update import update_dataset


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="accesos", description="Procesa registros públicos de acceso"
    )
    subcommands = root.add_subparsers(dest="command", required=True)
    update = subcommands.add_parser("update", help="Descubre, descarga y procesa cambios")
    update.add_argument("--source", default=os.getenv("SOURCE_BASE_URL"))
    update.add_argument("--data-dir", type=Path, default=Path(os.getenv("DATA_DIR", "data")))
    update.add_argument(
        "--output", type=Path, default=Path(os.getenv("WEB_DATA_DIR", "web/public/data"))
    )
    update.add_argument("--min-year", type=int, default=int(os.getenv("MIN_YEAR", "2023")))
    build = subcommands.add_parser("build-web", help="Regenera índices, analytics y exportaciones")
    build.add_argument("--data-dir", type=Path, default=Path(os.getenv("DATA_DIR", "data")))
    build.add_argument(
        "--output", type=Path, default=Path(os.getenv("WEB_DATA_DIR", "web/public/data"))
    )
    scan = subcommands.add_parser("discover", help="Lista los PDF visibles sin descargarlos")
    scan.add_argument("--source", default=os.getenv("SOURCE_BASE_URL"))
    scan.add_argument("--min-year", type=int, default=int(os.getenv("MIN_YEAR", "2023")))
    legacy = subcommands.add_parser(
        "import-legacy", help="Importa las tablas TSV normalizadas existentes"
    )
    legacy.add_argument("legacy_dir", type=Path)
    legacy.add_argument("--data-dir", type=Path, default=Path(os.getenv("DATA_DIR", "data")))
    legacy.add_argument(
        "--output", type=Path, default=Path(os.getenv("WEB_DATA_DIR", "web/public/data"))
    )
    legacy.add_argument("--public-base", default=os.getenv("SOURCE_PUBLIC_BASE_URL"))
    return root


def main() -> None:
    arguments = parser().parse_args()
    if arguments.command in {"update", "discover"} and not arguments.source:
        raise SystemExit("Falta SOURCE_BASE_URL o --source")
    if arguments.command == "update":
        result = update_dataset(
            source_base_url=arguments.source,
            data_dir=arguments.data_dir,
            web_data_dir=arguments.output,
            min_year=arguments.min_year,
        )
    elif arguments.command == "build-web":
        result = build_web_data(arguments.data_dir, arguments.output)
    elif arguments.command == "import-legacy":
        result = import_legacy_tsv(
            arguments.legacy_dir, arguments.data_dir, arguments.output, arguments.public_base
        )
    else:
        result = [asdict(item) for item in discover(arguments.source, arguments.min_year)]
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
