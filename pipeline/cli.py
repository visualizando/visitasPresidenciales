from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from pipeline.build_web import build_web_data
from pipeline.curation_server import serve_curation
from pipeline.discovery import discover
from pipeline.drive_backfill import download_public_folder
from pipeline.historical_csv_import import import_olivos_historical_csv
from pipeline.historical_office_import import import_historical_office
from pipeline.identity_candidates import build_identity_candidates_from_search
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
    historical_csv = subcommands.add_parser(
        "import-olivos-csv", help="Importa el CSV histórico unificado de Olivos"
    )
    historical_csv.add_argument("source", type=Path)
    historical_csv.add_argument("--first-year", type=int, default=2020)
    historical_csv.add_argument("--last-year", type=int, default=2021)
    historical_csv.add_argument("--data-dir", type=Path, default=Path(os.getenv("DATA_DIR", "data")))
    historical_csv.add_argument(
        "--output", type=Path, default=Path(os.getenv("WEB_DATA_DIR", "web/public/data"))
    )
    historical_office = subcommands.add_parser(
        "import-historical-office", help="Importa XLSX y DOCX históricos estructurados"
    )
    historical_office.add_argument("source", type=Path)
    historical_office.add_argument(
        "--data-dir", type=Path, default=Path(os.getenv("DATA_DIR", "data"))
    )
    historical_office.add_argument(
        "--output", type=Path, default=Path(os.getenv("WEB_DATA_DIR", "web/public/data"))
    )
    backfill = subcommands.add_parser(
        "backfill-local", help="Importa PDF históricos legibles y pone el resto en cuarentena"
    )
    backfill.add_argument("source")
    backfill.add_argument("--min-year", type=int, default=1900)
    backfill.add_argument("--data-dir", type=Path, default=Path(os.getenv("DATA_DIR", "data")))
    backfill.add_argument(
        "--output", type=Path, default=Path(os.getenv("WEB_DATA_DIR", "web/public/data"))
    )
    backfill.add_argument(
        "--force-location",
        action="append",
        choices=("casa-rosada", "olivos"),
        default=[],
        help="Reprocesa una sede aunque el PDF no haya cambiado",
    )
    drive = subcommands.add_parser(
        "download-drive", help="Descarga recursivamente los PDF de una carpeta pública de Drive"
    )
    drive.add_argument("folder_id")
    drive.add_argument("output", type=Path)
    identities = subcommands.add_parser(
        "identity-candidates",
        help="Regenera candidatos de identidad desde los índices públicos existentes",
    )
    identities.add_argument(
        "--data-dir", type=Path, default=Path(os.getenv("DATA_DIR", "data"))
    )
    identities.add_argument(
        "--web-data-dir",
        type=Path,
        default=Path(os.getenv("WEB_DATA_DIR", "web/public/data")),
    )
    curate = subcommands.add_parser(
        "curate-identities", help="Abre la interfaz local de curación de identidades"
    )
    curate.add_argument(
        "--candidates",
        type=Path,
        default=Path("data/curation/candidates.csv"),
    )
    curate.add_argument(
        "--decisions",
        type=Path,
        default=Path("data/curation/entity_merges.json"),
    )
    curate.add_argument("--port", type=int, default=8765)
    curate.add_argument("--no-open", action="store_true")
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
    elif arguments.command == "import-olivos-csv":
        result = import_olivos_historical_csv(
            arguments.source,
            arguments.data_dir,
            arguments.output,
            first_year=arguments.first_year,
            last_year=arguments.last_year,
        )
    elif arguments.command == "import-historical-office":
        result = import_historical_office(
            arguments.source, arguments.data_dir, arguments.output
        )
    elif arguments.command == "backfill-local":
        result = update_dataset(
            source_base_url=arguments.source,
            data_dir=arguments.data_dir,
            web_data_dir=arguments.output,
            min_year=arguments.min_year,
            quarantine_failures=True,
            mark_missing=False,
            force_locations=set(arguments.force_location),
        )
    elif arguments.command == "download-drive":
        result = download_public_folder(arguments.folder_id, arguments.output)
    elif arguments.command == "identity-candidates":
        result = build_identity_candidates_from_search(
            arguments.data_dir, arguments.web_data_dir
        )
    elif arguments.command == "curate-identities":
        serve_curation(
            arguments.candidates,
            arguments.decisions,
            port=arguments.port,
            open_browser=not arguments.no_open,
        )
        return
    else:
        result = [asdict(item) for item in discover(arguments.source, arguments.min_year)]
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
