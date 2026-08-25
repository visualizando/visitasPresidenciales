import type {AccessEvent, PersonSummary} from "../types";

const COLUMNS = [
  "record_id",
  "entity_id",
  "canonical_name",
  "document_type",
  "document_number",
  "location",
  "record_type",
  "primary_at",
  "occurred_at",
  "entered_at",
  "exited_at",
  "direction",
  "device",
  "destination",
  "purpose",
  "activity",
  "authorized_by",
  "access_status",
  "quality",
  "raw_text",
  "source_urls",
  "source_paths",
  "source_pages",
] as const;

export function buildSelectedEventsCsv(events: AccessEvent[]) {
  const rows = [...events].sort(compareEvents).map((event) => [
    event.record_id,
    event.entity_id,
    event.canonical_name,
    event.document_type,
    event.document_number,
    event.location,
    event.record_type,
    primaryDate(event),
    event.occurred_at,
    event.entered_at,
    event.exited_at,
    event.direction,
    event.device,
    event.destination,
    event.purpose,
    event.activity,
    event.authorized_by,
    event.access_status,
    event.quality,
    event.raw_text,
    event.sources.map((source) => source.url).join(" | "),
    event.sources.map((source) => source.path).join(" | "),
    event.sources.map((source) => source.page).join(" | "),
  ]);
  return `\uFEFF${[COLUMNS, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n")}\r\n`;
}

export function selectedEventsFilename(people: PersonSummary[]) {
  if (people.length === 1) {
    const name = slug(people[0].canonical_name) || people[0].entity_id;
    return `accesos-${name}.csv`;
  }
  return `accesos-seleccion-${people.length}-personas.csv`;
}

function compareEvents(left: AccessEvent, right: AccessEvent) {
  const leftDate = primaryDate(left);
  const rightDate = primaryDate(right);
  if (leftDate && rightDate && leftDate !== rightDate) return leftDate.localeCompare(rightDate);
  if (leftDate && !rightDate) return -1;
  if (!leftDate && rightDate) return 1;
  return left.canonical_name.localeCompare(right.canonical_name, "es") || left.record_id.localeCompare(right.record_id);
}

function primaryDate(event: AccessEvent) {
  return event.occurred_at ?? event.entered_at ?? event.exited_at;
}

function csvCell(value: unknown) {
  let text = value == null ? "" : String(value);
  if (/^[\t ]*[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

function slug(value: string) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 64);
}
