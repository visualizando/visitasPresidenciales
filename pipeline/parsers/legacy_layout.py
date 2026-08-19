#!/usr/bin/env python3
import calendar
import csv
import re
import subprocess
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_ROOT = ROOT_DIR / "ACCESOS MILEI OLIVOS - ROSADA 2023-2025"
OUTPUT_DIR = ROOT_DIR / "normalized_tsv"

MONTHS = {
    "ENERO": 1,
    "FEBRERO": 2,
    "MARZO": 3,
    "ABRIL": 4,
    "MAYO": 5,
    "JUNIO": 6,
    "JULIO": 7,
    "AGOSTO": 8,
    "SEPTIEMBRE": 9,
    "SETIEMBRE": 9,
    "OCTUBRE": 10,
    "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}

OLIVOS_STANDARD_COLUMNS = [
    ("number_and_name", -1, 280),
    ("concurre_para", 280, 430),
    ("actividad_funcionario", 430, 540),
    ("actividad_otro", 540, 650),
    ("autorizado_por", 650, 760),
    ("audiencia", 760, 860),
    ("modo", 860, 930),
    ("entry_time_raw", 930, 1045),
    ("exit_time_raw", 1045, 99999),
]

OLIVOS_VEHICLE_COLUMNS = [
    ("row_number", 150, 195),
    ("visitor_raw", 195, 435),
    ("concurre_a", 435, 545),
    ("actividad_trabajo", 545, 675),
    ("actividad_visita", 675, 805),
    ("actividad_otro", 805, 930),
    ("autorizado_por", 930, 1070),
    ("entry_raw", 1070, 1210),
    ("exit_raw", 1210, 99999),
]

OLIVOS_ON_FOOT_COLUMNS = [
    ("row_number", 126, 160),
    ("visitor_raw", 160, 392),
    ("cargo_o_funcion", 392, 508),
    ("concurre_a", 508, 635),
    ("motivo", 635, 986),
    ("autorizado_por", 986, 1127),
    ("entry_raw", 1127, 1266),
    ("exit_raw", 1266, 99999),
]


def normalize_whitespace(value: str) -> str:
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def norm(value: str) -> str:
    return strip_accents(normalize_whitespace(value)).upper()


def month_number(value: str):
    return MONTHS.get(norm(value))


def iso_or_blank(dt):
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


def date_iso_or_blank(d):
    return d.isoformat() if d else ""


def join_text_items(items):
    if not items:
        return ""
    items = sorted(items, key=lambda item: (item["top"], item["left"]))
    lines = []
    current_top = None
    current_parts = []
    for item in items:
        if current_top is None or abs(item["top"] - current_top) <= 1:
            current_parts.append(item["text"])
            if current_top is None:
                current_top = item["top"]
        else:
            lines.append(" ".join(current_parts))
            current_parts = [item["text"]]
            current_top = item["top"]
    if current_parts:
        lines.append(" ".join(current_parts))
    return normalize_whitespace(" ".join(lines))


def parse_xml_texts(pdf_path: Path):
    with tempfile.TemporaryDirectory() as tmpdir:
        out_base = Path(tmpdir) / "out"
        subprocess.run(
            ["pdftohtml", "-xml", str(pdf_path), str(out_base)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        root = ET.fromstring(out_base.with_suffix(".xml").read_text(encoding="utf-8"))

    pages = []
    for page in root.findall("page"):
        texts = []
        for node in page.findall("text"):
            text = normalize_whitespace("".join(node.itertext()))
            if not text:
                continue
            left = int(node.attrib["left"])
            width = int(node.attrib.get("width", "0"))
            texts.append(
                {
                    "top": int(node.attrib["top"]),
                    "left": left,
                    "width": width,
                    "right": left + width,
                    "text": text,
                    "norm": norm(text),
                }
            )
        texts.sort(key=lambda item: (item["top"], item["left"]))
        pages.append({"page_number": int(page.attrib["number"]), "texts": texts})
    return pages


def find_header_item(texts, predicate):
    matches = [item for item in texts if predicate(item["norm"])]
    if not matches:
        return None
    return min(matches, key=lambda item: (item["top"], item["left"]))


def find_header_left(texts, predicate):
    item = find_header_item(texts, predicate)
    return item["left"] if item else None


def nearest_anchor_rows(texts, anchor_predicate, threshold):
    anchors = sorted({item["top"] for item in texts if anchor_predicate(item)})
    rows = []
    if not anchors:
        return rows
    for anchor in anchors:
        assigned = []
        for item in texts:
            nearest = min(anchors, key=lambda value: abs(item["top"] - value))
            if nearest == anchor and abs(item["top"] - anchor) <= threshold:
                assigned.append(item)
        rows.append((anchor, assigned))
    return rows


def split_by_columns(items, columns):
    output = {name: [] for name, _, _ in columns}
    for item in items:
        for name, start, end in columns:
            if (start == -1 and item["left"] < end) or (start != -1 and start <= item["left"] < end):
                output[name].append(item)
                break
    return {name: join_text_items(values) for name, values in output.items()}


def split_by_starts(items, ordered_starts):
    columns = []
    for idx, (name, start) in enumerate(ordered_starts):
        end = ordered_starts[idx + 1][1] if idx + 1 < len(ordered_starts) else 99999
        columns.append((name, start, end))
    return split_by_columns(items, columns)


def midpoint(a, b):
    return (a + b) // 2


def build_casa_layout(texts):
    headers = {
        "visit": find_header_item(texts, lambda v: v == "VISITA"),
        "function": find_header_item(texts, lambda v: v == "FUNCION"),
        "observations": find_header_item(texts, lambda v: v == "OBSERVACIONES"),
        "authorized_by": find_header_item(texts, lambda v: v == "AUTORIZA"),
        "accompanies": find_header_item(texts, lambda v: v == "ACOMPANA"),
        "dependency": find_header_item(texts, lambda v: v == "DEPENDENCIA"),
        "access_point": find_header_item(texts, lambda v: v == "ACCESO"),
        "entry_raw": find_header_item(texts, lambda v: v == "FECHA DE ENTRADA"),
        "exit_raw": find_header_item(texts, lambda v: v == "FECHA DE SALIDA"),
    }
    if any(value is None for value in headers.values()):
        return None
    b1 = midpoint(headers["visit"]["right"], headers["function"]["left"])
    b2 = midpoint(headers["function"]["right"], headers["observations"]["left"])
    b3 = midpoint(headers["observations"]["right"], headers["authorized_by"]["left"])
    b4 = midpoint(headers["authorized_by"]["right"], headers["accompanies"]["left"])
    b5 = midpoint(headers["accompanies"]["right"], headers["dependency"]["left"])
    b6 = midpoint(headers["dependency"]["right"], headers["access_point"]["left"])
    b7 = midpoint(headers["access_point"]["right"], headers["entry_raw"]["left"])
    b8 = midpoint(headers["entry_raw"]["right"], headers["exit_raw"]["left"])
    columns = [
        ("visitor_raw", -1, b1),
        ("function", b1, b2),
        ("observations", b2, b3),
        ("authorized_by", b3, b4),
        ("accompanies", b4, b5),
        ("dependency", b5, b6),
        ("access_point", b6, b7),
        ("entry_raw", b7, b8),
        ("exit_raw", b8, 99999),
    ]
    return columns, b7, b8


def build_olivos_standard_layout(texts):
    name = find_header_item(texts, lambda v: "APELLIDO Y NOMBRE" in v)
    concurre = find_header_item(texts, lambda v: v.startswith("CONCURRE PARA"))
    funcionario = find_header_item(texts, lambda v: v == "FUNCIONARIO")
    otro = find_header_item(texts, lambda v: v == "OTRO")
    combined_activity = find_header_item(texts, lambda v: v == "FUNCIONARIO OTRO")
    used_combined_activity = False
    if funcionario is None and combined_activity is not None:
        funcionario = {"left": combined_activity["left"], "right": combined_activity["left"] + combined_activity["width"] // 2}
        used_combined_activity = True
    if otro is None and combined_activity is not None:
        otro = {"left": combined_activity["left"] + combined_activity["width"] // 2, "right": combined_activity["right"]}
        used_combined_activity = True
    autorizado = find_header_item(texts, lambda v: v.startswith("AUTORIZADO"))
    audiencia = find_header_item(texts, lambda v: v == "AUDIENCIA")
    modo = find_header_item(texts, lambda v: v == "MODO")
    entrada = find_header_item(texts, lambda v: v == "HORA ENTRADA")
    salida = find_header_item(texts, lambda v: v == "HORA SALIDA")
    combined_hours = find_header_item(texts, lambda v: v == "HORA ENTRADA HORA SALIDA")
    if entrada is None and combined_hours is not None:
        entrada = combined_hours
    if salida is None and combined_hours is not None:
        salida = {"left": combined_hours["left"] + 74, "right": combined_hours["right"]}
    if any(item is None for item in [name, concurre, funcionario, otro, autorizado, audiencia, modo, entrada, salida]):
        return None
    b2 = midpoint(name["right"], concurre["left"])
    b3 = midpoint(concurre["left"], funcionario["left"])
    b4 = otro["left"] if used_combined_activity else midpoint(funcionario["left"], otro["left"])
    b5 = midpoint(otro["left"], autorizado["left"])
    b6 = midpoint(autorizado["left"], audiencia["left"])
    b7 = midpoint(audiencia["left"], modo["left"])
    b8 = midpoint(modo["left"], entrada["left"])
    b9 = midpoint(entrada["left"], salida["left"])
    return [
        ("number_and_name", -1, b2),
        ("concurre_para", b2, b3),
        ("actividad_funcionario", b3, b4),
        ("actividad_otro", b4, b5),
        ("autorizado_por", b5, b6),
        ("audiencia", b6, b7),
        ("modo", b7, b8),
        ("entry_time_raw", b8, b9),
        ("exit_time_raw", b9, 99999),
    ]


def build_olivos_control_layout(texts):
    nro = find_header_item(texts, lambda v: v == "N°" or v == "NRO")
    name = find_header_item(texts, lambda v: "APELLIDO Y NOMBRE" in v)
    concurre_a = find_header_item(texts, lambda v: v.startswith("CONCURRE A") or v.startswith("CONCURRE PARA"))
    funcionario = find_header_item(texts, lambda v: v == "FUNCIONARIO")
    otro = find_header_item(texts, lambda v: v == "OTRO")
    autorizado = find_header_item(texts, lambda v: v.startswith("AUTORIZADO"))
    audiencia = find_header_item(texts, lambda v: v == "AUDIENCIA" or v == "REUNION")
    entrada = find_header_item(texts, lambda v: v == "ENTRADA" or v == "HORA ENTRADA")
    salida = find_header_item(texts, lambda v: v == "SALIDA" or v == "HORA SALIDA")
    if any(item is None for item in [nro, name, concurre_a, funcionario, otro, autorizado, audiencia, entrada, salida]):
        return None
    b1 = midpoint(nro["right"], name["left"])
    b2 = midpoint(name["right"], concurre_a["left"])
    b3 = midpoint(concurre_a["left"], funcionario["left"])
    b4 = midpoint(funcionario["left"], otro["left"])
    b5 = midpoint(otro["left"], autorizado["left"])
    b6 = midpoint(autorizado["left"], audiencia["left"])
    b7 = midpoint(audiencia["left"], entrada["left"])
    b8 = midpoint(entrada["left"], salida["left"])
    return [
        ("row_number", -1, b1),
        ("visitor_raw", b1, b2),
        ("concurre_para", b2, b3),
        ("actividad_funcionario", b3, b4),
        ("actividad_otro", b4, b5),
        ("autorizado_por", b5, b6),
        ("audiencia", b6, b7),
        ("entry_time_raw", b7, b8),
        ("exit_time_raw", b8, 99999),
    ]


def build_monthly_layout(texts):
    name = find_header_item(texts, lambda v: v == "APELLIDO Y NOMBRE")
    concurre = find_header_item(texts, lambda v: v == "CONCURRE PARA")
    function = find_header_item(texts, lambda v: v == "FUNCION")
    autoriza_reunion = find_header_item(texts, lambda v: v == "AUTORIZA REUNION")
    if autoriza_reunion is None:
        autoriza = find_header_item(texts, lambda v: v == "AUTORIZA")
        reunion = find_header_item(texts, lambda v: v == "REUNION")
        if autoriza is not None and reunion is not None:
            autoriza_reunion = {
                "left": autoriza["left"],
                "right": reunion["right"],
                "width": reunion["right"] - autoriza["left"],
            }
    fecha = find_header_item(texts, lambda v: v == "FECHA")
    entry_header = find_header_item(texts, lambda v: v == "HORA ENTRADA")
    exit_header = find_header_item(texts, lambda v: v == "HORA SALIDA")
    combined_hours = find_header_item(texts, lambda v: v == "HORA ENTRADA HORA SALIDA")
    if entry_header is None and combined_hours is not None:
        entry_header = combined_hours
    if exit_header is None and combined_hours is not None:
        exit_header = {"left": combined_hours["left"] + 74, "right": combined_hours["right"], "width": combined_hours["width"] - 74}
    if any(item is None for item in [name, concurre, function, autoriza_reunion, fecha, entry_header, exit_header]):
        return None
    b1 = midpoint(name["right"], concurre["left"])
    b2 = midpoint(concurre["right"], function["left"])
    b3 = midpoint(function["right"], autoriza_reunion["left"])
    b4 = midpoint(autoriza_reunion["left"], fecha["left"])
    b5 = midpoint(autoriza_reunion["right"], fecha["left"])
    b6 = midpoint(fecha["left"], entry_header["left"])
    b7 = midpoint(entry_header["left"], exit_header["left"])
    return [
        ("visitor_raw", -1, b1),
        ("concurre_para", b1, b2),
        ("function", b2, b3),
        ("authorized_by", b3, b4),
        ("meeting", b4, b5),
        ("date_raw", b5, b6),
        ("entry_time_raw", b6, b7),
        ("exit_time_raw", b7, 99999),
    ]


def parse_casa_visitor(visitor_raw):
    visitor_raw = normalize_whitespace(visitor_raw)
    match = re.match(r"^(.*)\(([^()]*)\)\s*$", visitor_raw)
    if match:
        return normalize_whitespace(match.group(1)), normalize_whitespace(match.group(2))
    return visitor_raw, ""


def parse_casa_datetime(raw):
    raw = normalize_whitespace(raw)
    if not raw or norm(raw) == "SIN SALIDA":
        return None
    try:
        return datetime.strptime(raw, "%d/%m/%Y %H:%M")
    except ValueError:
        return None


def parse_exact_date(raw):
    raw = normalize_whitespace(raw)
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%d/%m/%Y").date()
    except ValueError:
        return None


def normalize_time_text(raw):
    raw = normalize_whitespace(raw)
    if not raw or raw in {"-", "–"}:
        return ""
    if re.fullmatch(r"\d{4}", raw):
        return f"{raw[:2]}:{raw[2:]}"
    if re.fullmatch(r"\d{1,2}:\d{2}", raw):
        hh, mm = raw.split(":")
        return f"{int(hh):02d}:{mm}"
    return raw


def combine_date_time(d, time_raw, entry_dt=None):
    normalized = normalize_time_text(time_raw)
    if not d or not normalized or not re.fullmatch(r"\d{2}:\d{2}", normalized):
        return None
    dt = datetime.strptime(f"{d.isoformat()} {normalized}", "%Y-%m-%d %H:%M")
    if entry_dt is not None and dt < entry_dt:
        dt += timedelta(days=1)
    return dt


def parse_olivos_page_date(texts):
    day = month = year = None
    for item in texts:
        if item["norm"].startswith("DIA:"):
            match = re.search(r"DIA:\s*(\d{1,2})", item["norm"])
            if match:
                day = int(match.group(1))
        elif item["norm"].startswith("MES:"):
            month = month_number(item["text"].split(":", 1)[1])
        elif item["norm"].startswith("ANO:"):
            match = re.search(r"ANO:\s*(\d{4})", item["norm"])
            if match:
                year = int(match.group(1))
    if day and month and year:
        return date(year, month, day)
    return None


def parse_title_single_date(texts):
    blob = norm(" ".join(item["text"] for item in texts))
    match = re.search(r"(?:DIA\s+)?(\d{1,2})(?:\s+DE)?\s+([A-Z]+)\s+DE\s+(\d{4})", blob)
    if not match:
        return None
    day = int(match.group(1))
    month = month_number(match.group(2))
    year = int(match.group(3))
    if day and month and year:
        return date(year, month, day)
    return None


def safe_date(year, month, day):
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def parse_title_date_range(texts):
    blob = norm(" ".join(item["text"] for item in texts))
    match = re.search(r"DIA\s+(\d{1,2})\s+AL\s+(\d{1,2})\s+DE\s+([A-Z]+)\s+DE\s+(\d{4})", blob)
    if match:
        start_day = int(match.group(1))
        end_day = int(match.group(2))
        month = month_number(match.group(3))
        year = int(match.group(4))
        if month:
            start_date = safe_date(year, month, start_day)
            if end_day >= start_day:
                end_date = safe_date(year, month, end_day)
            else:
                end_date = start_date + timedelta(days=1)
            return start_date, end_date
    single = parse_title_single_date(texts)
    if single:
        return single, single
    return None, None


def parse_vehicle_datetime(raw):
    raw = normalize_whitespace(raw)
    if not raw or raw in {"-", "–"}:
        return None
    for fmt in ("%d-%m-%y %I:%M %p", "%d-%m-%Y %I:%M %p"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def detect_olivos_page_type(texts):
    blob = norm(" ".join(item["text"] for item in texts))
    if "MOVIMIENTOS DE PERSONAL A PIE" in blob:
        return "on_foot_movements"
    if "MOVIMIENTOS DE PERSONAL EN VEHICULOS" in blob:
        return "vehicle_movements"
    if "AUTORIZA REUNION" in blob and "FECHA" in blob and "HORA ENTRADA HORA SALIDA" in blob:
        return "monthly_ledger"
    if "PLANILLA DE CONTROL DE INGRESO" in blob or "PLANILLA DE CONTROL DE INGRESOS" in blob:
        return "control_turno"
    if "REGISTRO DE INGRESOS" in blob:
        return "registro_ingresos"
    return "unknown"


def parse_casa_page(source_id, rel_path, page_number, texts, layout=None):
    layout = layout or build_casa_layout(texts)
    if not layout:
        return [], None, "missing_casa_headers"
    columns, entry_start, exit_start = layout
    header_norms = {
        "VISITA",
        "FUNCION",
        "OBSERVACIONES",
        "AUTORIZA",
        "ACOMPANA",
        "DEPENDENCIA",
        "ACCESO",
        "FECHA DE ENTRADA",
        "FECHA DE SALIDA",
    }
    filtered = [item for item in texts if item["norm"] not in header_norms]
    row_groups = nearest_anchor_rows(
        filtered,
        lambda item: entry_start <= item["left"] < exit_start and re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}\s+\d{2}:\d{2}", item["text"]),
        threshold=7,
    )
    rows = []
    for row_idx, (_, items) in enumerate(row_groups, start=1):
        cols = split_by_columns(items, columns)
        visitor_name, visitor_document = parse_casa_visitor(cols["visitor_raw"])
        entry_dt = parse_casa_datetime(cols["entry_raw"])
        exit_dt = parse_casa_datetime(cols["exit_raw"])
        rows.append(
            {
                "source_id": source_id,
                "relative_path": rel_path,
                "page_number": page_number,
                "row_number_on_page": row_idx,
                "visitor_raw": cols["visitor_raw"],
                "visitor_name": visitor_name,
                "visitor_document": visitor_document,
                "function": cols["function"],
                "observations": cols["observations"],
                "authorized_by": cols["authorized_by"],
                "accompanies": cols["accompanies"],
                "dependency": cols["dependency"],
                "access_point": cols["access_point"],
                "entry_raw": cols["entry_raw"],
                "entry_iso": iso_or_blank(entry_dt),
                "exit_raw": cols["exit_raw"],
                "exit_iso": iso_or_blank(exit_dt),
            }
        )
    return rows, layout, ""


def parse_olivos_standard_page(page_id, source_id, rel_path, page_number, texts):
    page_date = parse_olivos_page_date(texts)
    columns = build_olivos_standard_layout(texts) or OLIVOS_STANDARD_COLUMNS
    rows = []
    row_groups = nearest_anchor_rows(
        texts,
        lambda item: item["left"] < 120 and re.fullmatch(r"\d+", item["text"]),
        threshold=12,
    )
    for _, items in row_groups:
        cols = split_by_columns(items, columns)
        match = re.match(r"^(\d+)\s+(.*)$", cols["number_and_name"])
        record_number = match.group(1) if match else ""
        visitor_raw = normalize_whitespace(match.group(2) if match else cols["number_and_name"])
        entry_dt = combine_date_time(page_date, cols["entry_time_raw"])
        exit_dt = combine_date_time(page_date, cols["exit_time_raw"], entry_dt)
        rows.append(
            {
                "page_id": page_id,
                "source_id": source_id,
                "relative_path": rel_path,
                "page_number": page_number,
                "register_date": date_iso_or_blank(page_date),
                "record_number": record_number,
                "visitor_raw": visitor_raw,
                "concurre_para": cols["concurre_para"],
                "actividad_funcionario": cols["actividad_funcionario"],
                "actividad_otro": cols["actividad_otro"],
                "autorizado_por": cols["autorizado_por"],
                "audiencia": cols["audiencia"],
                "modo": cols["modo"],
                "entry_time_raw": cols["entry_time_raw"],
                "entry_iso": iso_or_blank(entry_dt),
                "exit_time_raw": cols["exit_time_raw"],
                "exit_iso": iso_or_blank(exit_dt),
            }
        )
    return page_date, rows


def parse_olivos_control_page(page_id, source_id, rel_path, page_number, texts, columns=None):
    columns = columns or build_olivos_control_layout(texts)
    date_start, date_end = parse_title_date_range(texts)
    rows = []
    if columns:
        row_groups = nearest_anchor_rows(
            texts,
            lambda item: item["left"] < 120 and re.fullmatch(r"\d+", item["text"]),
            threshold=12,
        )
        for _, items in row_groups:
            cols = split_by_columns(items, columns)
            rows.append(
                {
                    "page_id": page_id,
                    "source_id": source_id,
                    "relative_path": rel_path,
                    "page_number": page_number,
                    "register_date_start": date_iso_or_blank(date_start),
                    "register_date_end": date_iso_or_blank(date_end),
                    "record_number": cols["row_number"],
                    "visitor_raw": cols["visitor_raw"],
                    "concurre_para": cols["concurre_para"],
                    "actividad_funcionario": cols["actividad_funcionario"],
                    "actividad_otro": cols["actividad_otro"],
                    "autorizado_por": cols["autorizado_por"],
                    "audiencia": cols["audiencia"],
                    "entry_time_raw": cols["entry_time_raw"],
                    "exit_time_raw": cols["exit_time_raw"],
                }
            )
    return date_start, date_end, rows, columns, "" if columns else "missing_control_headers"


def parse_olivos_vehicle_page(page_id, source_id, rel_path, page_number, texts):
    page_date = parse_title_single_date(texts)
    rows = []
    row_groups = nearest_anchor_rows(
        texts,
        lambda item: 150 <= item["left"] < 195 and re.fullmatch(r"\d+", item["text"]),
        threshold=12,
    )
    for _, items in row_groups:
        cols = split_by_columns(items, OLIVOS_VEHICLE_COLUMNS)
        entry_dt = parse_vehicle_datetime(cols["entry_raw"])
        exit_dt = parse_vehicle_datetime(cols["exit_raw"])
        rows.append(
            {
                "page_id": page_id,
                "source_id": source_id,
                "relative_path": rel_path,
                "page_number": page_number,
                "register_date": date_iso_or_blank(page_date),
                "record_number": cols["row_number"],
                "visitor_raw": cols["visitor_raw"],
                "concurre_a": cols["concurre_a"],
                "actividad_trabajo": cols["actividad_trabajo"],
                "actividad_visita": cols["actividad_visita"],
                "actividad_otro": cols["actividad_otro"],
                "autorizado_por": cols["autorizado_por"],
                "entry_raw": cols["entry_raw"],
                "entry_iso": iso_or_blank(entry_dt),
                "exit_raw": cols["exit_raw"],
                "exit_iso": iso_or_blank(exit_dt),
            }
        )
    return page_date, rows


def parse_olivos_on_foot_page(page_id, source_id, rel_path, page_number, texts):
    page_date = parse_title_single_date(texts)
    rows = []
    row_groups = nearest_anchor_rows(
        texts,
        lambda item: 126 <= item["left"] < 181 and re.fullmatch(r"\d+", item["text"]),
        threshold=12,
    )
    for _, items in row_groups:
        cols = split_by_columns(items, OLIVOS_ON_FOOT_COLUMNS)
        if not cols["entry_raw"] and not cols["exit_raw"]:
            combined = cols["autorizado_por"]
            matches = re.findall(r"\d{1,2}-\d{1,2}-\d{2}\s+\d{1,2}:\d{2}\s+[AP]M", combined)
            if matches:
                cols["entry_raw"] = matches[0]
                if len(matches) > 1:
                    cols["exit_raw"] = matches[1]
                cols["autorizado_por"] = normalize_whitespace(re.sub(r"\d{1,2}-\d{1,2}-\d{2}\s+\d{1,2}:\d{2}\s+[AP]M", "", combined))
        entry_dt = parse_vehicle_datetime(cols["entry_raw"])
        exit_dt = parse_vehicle_datetime(cols["exit_raw"])
        rows.append(
            {
                "page_id": page_id,
                "source_id": source_id,
                "relative_path": rel_path,
                "page_number": page_number,
                "register_date": date_iso_or_blank(page_date),
                "record_number": cols["row_number"],
                "visitor_raw": cols["visitor_raw"],
                "cargo_o_funcion": cols["cargo_o_funcion"],
                "concurre_a": cols["concurre_a"],
                "motivo": cols["motivo"],
                "autorizado_por": cols["autorizado_por"],
                "entry_raw": cols["entry_raw"],
                "entry_iso": iso_or_blank(entry_dt),
                "exit_raw": cols["exit_raw"],
                "exit_iso": iso_or_blank(exit_dt),
            }
        )
    return page_date, rows


def parse_olivos_monthly_page(page_id, source_id, rel_path, page_number, texts, columns=None):
    columns = columns or build_monthly_layout(texts)
    if not columns:
        return [], [], None, None, None, "missing_monthly_headers"
    rows = []
    statuses = []
    dates = []
    row_groups = nearest_anchor_rows(
        texts,
        lambda item: 570 <= item["left"] < 656
        and re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", item["text"]),
        threshold=7,
    )
    for _, items in row_groups:
        cols = split_by_columns(items, columns)
        row_date = parse_exact_date(cols["date_raw"])
        if row_date:
            dates.append(row_date)
        note_parts = [cols["concurre_para"], cols["function"], cols["authorized_by"], cols["meeting"]]
        note_text = normalize_whitespace(" ".join(part for part in note_parts if part))
        if cols["visitor_raw"]:
            entry_dt = combine_date_time(row_date, cols["entry_time_raw"])
            exit_dt = combine_date_time(row_date, cols["exit_time_raw"], entry_dt)
            rows.append(
                {
                    "page_id": page_id,
                    "source_id": source_id,
                    "relative_path": rel_path,
                    "page_number": page_number,
                    "register_date": date_iso_or_blank(row_date),
                    "visitor_raw": cols["visitor_raw"],
                    "concurre_para": cols["concurre_para"],
                    "function": cols["function"],
                    "authorized_by": cols["authorized_by"],
                    "meeting": cols["meeting"],
                    "entry_time_raw": cols["entry_time_raw"],
                    "entry_iso": iso_or_blank(entry_dt),
                    "exit_time_raw": cols["exit_time_raw"],
                    "exit_iso": iso_or_blank(exit_dt),
                }
            )
        elif note_text:
            statuses.append(
                {
                    "page_id": page_id,
                    "source_id": source_id,
                    "relative_path": rel_path,
                    "page_number": page_number,
                    "register_date": date_iso_or_blank(row_date),
                    "status_text": note_text,
                }
            )
    start_date = min(dates) if dates else None
    end_date = max(dates) if dates else None
    return rows, statuses, start_date, end_date, columns, ""


def write_tsv(path: Path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    pdf_paths = sorted(INPUT_ROOT.rglob("*.pdf"))

    sources = []
    casa_accesses = []
    olivos_pages = []
    olivos_accesses = []
    olivos_control_turno_accesses = []
    olivos_vehicle_movements = []
    olivos_on_foot_movements = []
    olivos_monthly_accesses = []
    olivos_monthly_daily_status = []
    issues = []

    page_id = 1

    for source_id, pdf_path in enumerate(pdf_paths, start=1):
        rel_path = str(pdf_path.relative_to(ROOT_DIR))
        if "/Casa de Gobierno/" in rel_path:
            site = "Casa de Gobierno"
        elif "/Residencia Presidencial de Olivos/" in rel_path:
            site = "Residencia Presidencial de Olivos"
        else:
            site = "Unknown"

        pages = parse_xml_texts(pdf_path)
        sources.append(
            {
                "source_id": source_id,
                "relative_path": rel_path,
                "filename": pdf_path.name,
                "site": site,
                "page_count": len(pages),
            }
        )

        casa_layout = None
        last_olivos_type = None
        control_layout = None
        monthly_layout = None

        for page in pages:
            texts = page["texts"]
            page_number = page["page_number"]

            if site == "Casa de Gobierno":
                parsed_rows, casa_layout, problem = parse_casa_page(source_id, rel_path, page_number, texts, casa_layout)
                casa_accesses.extend(parsed_rows)
                if problem and texts:
                    issues.append(
                        {
                            "source_id": source_id,
                            "relative_path": rel_path,
                            "page_number": page_number,
                            "issue_type": problem,
                            "details": "Could not identify Casa de Gobierno column headers on this page or any earlier page in the same PDF.",
                        }
                    )
                continue

            detected_type = detect_olivos_page_type(texts)
            page_type = detected_type
            if page_type == "unknown" and last_olivos_type in {"control_turno", "monthly_ledger"}:
                page_type = last_olivos_type

            blob = norm(" ".join(item["text"] for item in texts))
            sin_novedad = "SIN NOVEDAD" in blob

            if page_type == "registro_ingresos":
                register_date, parsed_rows = parse_olivos_standard_page(page_id, source_id, rel_path, page_number, texts)
                olivos_pages.append(
                    {
                        "page_id": page_id,
                        "source_id": source_id,
                        "relative_path": rel_path,
                        "page_number": page_number,
                        "register_type": page_type,
                        "register_date_start": date_iso_or_blank(register_date),
                        "register_date_end": date_iso_or_blank(register_date),
                        "sin_novedad": "1" if sin_novedad else "0",
                        "row_count": len(parsed_rows),
                    }
                )
                olivos_accesses.extend(parsed_rows)
                last_olivos_type = "registro_ingresos"
                if register_date is None:
                    issues.append(
                        {
                            "source_id": source_id,
                            "relative_path": rel_path,
                            "page_number": page_number,
                            "issue_type": "missing_olivos_page_date",
                            "details": "Could not parse DÍA/MES/AÑO header for standard Olivos page.",
                        }
                    )
                page_id += 1
            elif page_type == "control_turno":
                date_start, date_end, parsed_rows, control_layout, problem = parse_olivos_control_page(
                    page_id, source_id, rel_path, page_number, texts, control_layout
                )
                olivos_pages.append(
                    {
                        "page_id": page_id,
                        "source_id": source_id,
                        "relative_path": rel_path,
                        "page_number": page_number,
                        "register_type": page_type,
                        "register_date_start": date_iso_or_blank(date_start),
                        "register_date_end": date_iso_or_blank(date_end),
                        "sin_novedad": "1" if sin_novedad else "0",
                        "row_count": len(parsed_rows),
                    }
                )
                olivos_control_turno_accesses.extend(parsed_rows)
                last_olivos_type = "control_turno"
                if problem and (parsed_rows or not sin_novedad):
                    issues.append(
                        {
                            "source_id": source_id,
                            "relative_path": rel_path,
                            "page_number": page_number,
                            "issue_type": problem,
                            "details": "Could not identify control-turno column headers on this page or any earlier page in the same PDF.",
                        }
                    )
                if date_start is None:
                    issues.append(
                        {
                            "source_id": source_id,
                            "relative_path": rel_path,
                            "page_number": page_number,
                            "issue_type": "missing_control_turno_date",
                            "details": "Could not parse title date or date range for control-turno page.",
                        }
                    )
                page_id += 1
            elif page_type == "vehicle_movements":
                register_date, parsed_rows = parse_olivos_vehicle_page(page_id, source_id, rel_path, page_number, texts)
                olivos_pages.append(
                    {
                        "page_id": page_id,
                        "source_id": source_id,
                        "relative_path": rel_path,
                        "page_number": page_number,
                        "register_type": page_type,
                        "register_date_start": date_iso_or_blank(register_date),
                        "register_date_end": date_iso_or_blank(register_date),
                        "sin_novedad": "1" if sin_novedad else "0",
                        "row_count": len(parsed_rows),
                    }
                )
                olivos_vehicle_movements.extend(parsed_rows)
                last_olivos_type = "vehicle_movements"
                if register_date is None:
                    issues.append(
                        {
                            "source_id": source_id,
                            "relative_path": rel_path,
                            "page_number": page_number,
                            "issue_type": "missing_vehicle_page_date",
                            "details": "Could not parse title date for Olivos vehicle-movement page.",
                        }
                    )
                page_id += 1
            elif page_type == "on_foot_movements":
                register_date, parsed_rows = parse_olivos_on_foot_page(page_id, source_id, rel_path, page_number, texts)
                olivos_pages.append(
                    {
                        "page_id": page_id,
                        "source_id": source_id,
                        "relative_path": rel_path,
                        "page_number": page_number,
                        "register_type": page_type,
                        "register_date_start": date_iso_or_blank(register_date),
                        "register_date_end": date_iso_or_blank(register_date),
                        "sin_novedad": "1" if sin_novedad else "0",
                        "row_count": len(parsed_rows),
                    }
                )
                olivos_on_foot_movements.extend(parsed_rows)
                last_olivos_type = "on_foot_movements"
                if register_date is None:
                    issues.append(
                        {
                            "source_id": source_id,
                            "relative_path": rel_path,
                            "page_number": page_number,
                            "issue_type": "missing_on_foot_page_date",
                            "details": "Could not parse title date for Olivos on-foot movement page.",
                        }
                    )
                page_id += 1
            elif page_type == "monthly_ledger":
                parsed_rows, parsed_statuses, date_start, date_end, monthly_layout, problem = parse_olivos_monthly_page(
                    page_id, source_id, rel_path, page_number, texts, monthly_layout
                )
                olivos_pages.append(
                    {
                        "page_id": page_id,
                        "source_id": source_id,
                        "relative_path": rel_path,
                        "page_number": page_number,
                        "register_type": page_type,
                        "register_date_start": date_iso_or_blank(date_start),
                        "register_date_end": date_iso_or_blank(date_end),
                        "sin_novedad": "1" if sin_novedad else "0",
                        "row_count": len(parsed_rows) + len(parsed_statuses),
                    }
                )
                olivos_monthly_accesses.extend(parsed_rows)
                olivos_monthly_daily_status.extend(parsed_statuses)
                last_olivos_type = "monthly_ledger"
                if problem:
                    issues.append(
                        {
                            "source_id": source_id,
                            "relative_path": rel_path,
                            "page_number": page_number,
                            "issue_type": problem,
                            "details": "Could not identify monthly-ledger headers on this page or any earlier page in the same PDF.",
                        }
                    )
                page_id += 1
            else:
                if len(texts) > 5:
                    issues.append(
                        {
                            "source_id": source_id,
                            "relative_path": rel_path,
                            "page_number": page_number,
                            "issue_type": "unknown_olivos_page_type",
                            "details": "Olivos page did not match any known schema.",
                        }
                    )

    write_tsv(
        OUTPUT_DIR / "pdf_sources.tsv",
        ["source_id", "relative_path", "filename", "site", "page_count"],
        sources,
    )
    write_tsv(
        OUTPUT_DIR / "casa_gobierno_accesses.tsv",
        [
            "source_id",
            "relative_path",
            "page_number",
            "row_number_on_page",
            "visitor_raw",
            "visitor_name",
            "visitor_document",
            "function",
            "observations",
            "authorized_by",
            "accompanies",
            "dependency",
            "access_point",
            "entry_raw",
            "entry_iso",
            "exit_raw",
            "exit_iso",
        ],
        casa_accesses,
    )
    write_tsv(
        OUTPUT_DIR / "olivos_register_pages.tsv",
        [
            "page_id",
            "source_id",
            "relative_path",
            "page_number",
            "register_type",
            "register_date_start",
            "register_date_end",
            "sin_novedad",
            "row_count",
        ],
        olivos_pages,
    )
    write_tsv(
        OUTPUT_DIR / "olivos_accesses.tsv",
        [
            "page_id",
            "source_id",
            "relative_path",
            "page_number",
            "register_date",
            "record_number",
            "visitor_raw",
            "concurre_para",
            "actividad_funcionario",
            "actividad_otro",
            "autorizado_por",
            "audiencia",
            "modo",
            "entry_time_raw",
            "entry_iso",
            "exit_time_raw",
            "exit_iso",
        ],
        olivos_accesses,
    )
    write_tsv(
        OUTPUT_DIR / "olivos_control_turno_accesses.tsv",
        [
            "page_id",
            "source_id",
            "relative_path",
            "page_number",
            "register_date_start",
            "register_date_end",
            "record_number",
            "visitor_raw",
            "concurre_para",
            "actividad_funcionario",
            "actividad_otro",
            "autorizado_por",
            "audiencia",
            "entry_time_raw",
            "exit_time_raw",
        ],
        olivos_control_turno_accesses,
    )
    write_tsv(
        OUTPUT_DIR / "olivos_vehicle_movements.tsv",
        [
            "page_id",
            "source_id",
            "relative_path",
            "page_number",
            "register_date",
            "record_number",
            "visitor_raw",
            "concurre_a",
            "actividad_trabajo",
            "actividad_visita",
            "actividad_otro",
            "autorizado_por",
            "entry_raw",
            "entry_iso",
            "exit_raw",
            "exit_iso",
        ],
        olivos_vehicle_movements,
    )
    write_tsv(
        OUTPUT_DIR / "olivos_on_foot_movements.tsv",
        [
            "page_id",
            "source_id",
            "relative_path",
            "page_number",
            "register_date",
            "record_number",
            "visitor_raw",
            "cargo_o_funcion",
            "concurre_a",
            "motivo",
            "autorizado_por",
            "entry_raw",
            "entry_iso",
            "exit_raw",
            "exit_iso",
        ],
        olivos_on_foot_movements,
    )
    write_tsv(
        OUTPUT_DIR / "olivos_monthly_accesses.tsv",
        [
            "page_id",
            "source_id",
            "relative_path",
            "page_number",
            "register_date",
            "visitor_raw",
            "concurre_para",
            "function",
            "authorized_by",
            "meeting",
            "entry_time_raw",
            "entry_iso",
            "exit_time_raw",
            "exit_iso",
        ],
        olivos_monthly_accesses,
    )
    write_tsv(
        OUTPUT_DIR / "olivos_monthly_daily_status.tsv",
        [
            "page_id",
            "source_id",
            "relative_path",
            "page_number",
            "register_date",
            "status_text",
        ],
        olivos_monthly_daily_status,
    )
    write_tsv(
        OUTPUT_DIR / "parse_issues.tsv",
        ["source_id", "relative_path", "page_number", "issue_type", "details"],
        issues,
    )

    summary = [
        "# Normalized TSV export",
        "",
        f"- Source PDFs: {len(sources)}",
        f"- Casa de Gobierno access rows: {len(casa_accesses)}",
        f"- Olivos pages cataloged: {len(olivos_pages)}",
        f"- Olivos standard daily access rows: {len(olivos_accesses)}",
        f"- Olivos control-turno access rows: {len(olivos_control_turno_accesses)}",
        f"- Olivos monthly-ledger access rows: {len(olivos_monthly_accesses)}",
        f"- Olivos monthly-ledger status rows: {len(olivos_monthly_daily_status)}",
        f"- Olivos vehicle-movement rows: {len(olivos_vehicle_movements)}",
        f"- Olivos on-foot movement rows: {len(olivos_on_foot_movements)}",
        f"- Parse issues logged: {len(issues)}",
        "",
        "## Tables",
        "",
        "- `pdf_sources.tsv`: one row per source PDF.",
        "- `casa_gobierno_accesses.tsv`: Casa de Gobierno / Casa Rosada access rows.",
        "- `olivos_register_pages.tsv`: one row per Olivos page across all detected schemas.",
        "- `olivos_accesses.tsv`: rows from the daily `REGISTRO DE INGRESOS` format.",
        "- `olivos_control_turno_accesses.tsv`: rows from `PLANILLA DE CONTROL DE INGRESO(S)` turno pages.",
        "- `olivos_monthly_accesses.tsv`: rows from the later monthly Olivos ledger format (`AUTORIZA REUNIÓN`, `FECHA`, etc.).",
        "- `olivos_monthly_daily_status.tsv`: daily status markers such as `SIN NOVEDAD` from the monthly ledger PDFs.",
        "- `olivos_vehicle_movements.tsv`: vehicle-movement rows from the special 2023-12-10 page.",
        "- `olivos_on_foot_movements.tsv`: on-foot personnel-movement rows from the special 2023-12-10 page.",
        "- `parse_issues.tsv`: pages that could not be classified or had missing metadata/headers.",
        "",
        "## Relationships",
        "",
        "- `pdf_sources.source_id` joins to all other tables on `source_id`.",
        "- `olivos_register_pages.page_id` joins to the Olivos row tables on `page_id`.",
        "",
        "## Notes",
        "",
        "- ISO timestamps were normalized when the source row carried an exact date or unambiguous full datetime.",
        "- `Sin salida` / `-` values remain blank in normalized ISO columns.",
        "- Some PDFs preserve noisy source spelling/capitalization; raw text columns keep the original extracted text.",
        "- The control-turno Olivos pages only expose time-of-day plus a page-level date range, so that table preserves raw times and the page date window rather than forcing exact datetimes.",
    ]
    (OUTPUT_DIR / "README.md").write_text("\n".join(summary) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
