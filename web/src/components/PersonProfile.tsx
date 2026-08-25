import {ArrowDown, ArrowUp, Download, ExternalLink, FileText, Search, X} from "lucide-react";
import {useEffect, useMemo, useRef, useState} from "react";
import type {AccessEvent, CoincidenceResult, PersonSummary} from "../types";
import {CoincidenceRanking} from "./CoincidenceRanking";
import {locationLabel, titleCase} from "./SearchResults";
import {comparisonSeries} from "../utils/personColors";
import {buildSelectedEventsCsv, selectedEventsFilename} from "../utils/selectedEventsCsv";
import {RecordDetailDialog} from "./RecordDetailDialog";

type SortKey = "date" | "person" | "location" | "type" | "detail" | "exit" | "quality";
type SortDirection = "asc" | "desc";

const DATE_FORMATTER = new Intl.DateTimeFormat("es-AR", {day: "2-digit", month: "short", year: "numeric", timeZone: "UTC"});
const DATE_TIME_FORMATTER = new Intl.DateTimeFormat("es-AR", {day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit"});
const TIME_FORMATTER = new Intl.DateTimeFormat("es-AR", {hour: "2-digit", minute: "2-digit"});
const SORT_COLLATOR = new Intl.Collator("es", {numeric: true});
const EVENT_PAGE_SIZE = 100;

type PersonProfileProps = {
  people: PersonSummary[];
  events: AccessEvent[];
  loading: boolean;
  error: string | null;
  coincidences: CoincidenceResult[];
  onRemove: (entityId: string) => void;
  onClear: () => void;
};

export function PersonProfile({people, events, loading, error, coincidences, onRemove, onClear}: PersonProfileProps) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const detailTriggerRef = useRef<HTMLButtonElement | null>(null);
  const [detailEvent, setDetailEvent] = useState<AccessEvent | null>(null);
  const [sort, setSort] = useState<{key: SortKey; direction: SortDirection}>({key: "date", direction: "desc"});
  const peopleKey = people.map((person) => person.entity_id).sort().join(",");
  const [eventWindow, setEventWindow] = useState({peopleKey, count: EVENT_PAGE_SIZE});
  const visibleEventCount = eventWindow.peopleKey === peopleKey ? eventWindow.count : EVENT_PAGE_SIZE;
  const series = useMemo(() => comparisonSeries(people), [people]);
  const colors = useMemo(() => new Map(series.map((person) => [person.entityId, person.color])), [series]);
  useEffect(() => { headingRef.current?.focus(); }, [people.length]);

  const sortedEvents = useMemo(() => [...events].sort((a, b) => {
    const difference = SORT_COLLATOR.compare(sortValue(a, sort.key), sortValue(b, sort.key));
    return sort.direction === "asc" ? difference : -difference;
  }), [events, sort]);
  const visibleEvents = sortedEvents.slice(0, visibleEventCount);

  const locations = [...new Set(people.flatMap((person) => person.locations))];
  const latest = events.reduce<string | null>((value, event) => {
    const date = primaryDate(event);
    return date && (!value || date > value) ? date : value;
  }, null);

  function changeSort(key: SortKey) {
    setSort((current) => current.key === key ? {key, direction: current.direction === "asc" ? "desc" : "asc"} : {key, direction: key === "date" ? "desc" : "asc"});
  }

  function downloadSelection() {
    const blobUrl = URL.createObjectURL(new Blob([buildSelectedEventsCsv(events)], {type: "text/csv;charset=utf-8"}));
    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = selectedEventsFilename(people);
    link.hidden = true;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(blobUrl), 1_000);
  }

  function openEventDetail(event: AccessEvent, trigger: HTMLButtonElement) {
    detailTriggerRef.current = trigger;
    setDetailEvent(event);
  }

  function closeEventDetail() {
    setDetailEvent(null);
    window.requestAnimationFrame(() => detailTriggerRef.current?.focus());
  }

  return <section className="profile" aria-labelledby="profile-title">
    <div className="profile-header">
      <h2 id="profile-title" ref={headingRef} tabIndex={-1}>Detalle de movimientos</h2>
      <button className="text-button" type="button" onClick={onClear}>Limpiar selección</button>
    </div>

    <div className="selected-people" aria-label="Personas seleccionadas">{people.map((person) => <div className="person-chip" key={person.entity_id} style={{borderColor: colors.get(person.entity_id)}}><i className="person-color" style={{backgroundColor: colors.get(person.entity_id)}} aria-hidden="true" /><span><strong>{titleCase(person.canonical_name)}</strong><small>{person.document_type ?? "Documento"} <bdi>{person.document_number ?? "no informado"}</bdi></small></span><button type="button" onClick={() => onRemove(person.entity_id)} aria-label={`Quitar ${titleCase(person.canonical_name)}`}><X aria-hidden="true" /></button></div>)}</div>

    <dl className="profile-stats"><div><dd>{events.length.toLocaleString("es-AR")}</dd><dt>registros</dt></div><div><dd>{locations.map(locationLabel).join(" y ")}</dd><dt>{locations.length === 1 ? "sede" : "sedes"}</dt></div><div><dd>{formatDate(latest)}</dd><dt>última aparición</dt></div></dl>
    {loading && <p role="status">Cargando registros…</p>}
    {error && <div className="notice notice--error" role="alert"><strong>No se pudieron cargar los registros.</strong><span>{error}</span></div>}
    {!loading && !error && <div className="records-section"><div className="records-heading"><h3>Entradas y movimientos</h3><div className="records-heading-actions"><span>{visibleEvents.length.toLocaleString("es-AR")} de {events.length.toLocaleString("es-AR")} filas</span>{events.length > 0 && <button className="selection-download" type="button" onClick={downloadSelection} aria-label={`Descargar ${events.length.toLocaleString("es-AR")} ${events.length === 1 ? "registro" : "registros"} de la selección en CSV`}><Download aria-hidden="true" />Descargar CSV</button>}</div></div>{events.length ? <><div className="records-table-wrap"><table className="records-table"><caption className="sr-only">Entradas y movimientos de las personas seleccionadas</caption><thead><tr>
      <SortableHeader label="Fecha y hora" column="date" sort={sort} onSort={changeSort} />
      <SortableHeader label="Persona" column="person" sort={sort} onSort={changeSort} />
      <SortableHeader label="Sede" column="location" sort={sort} onSort={changeSort} />
      <SortableHeader label="Tipo" column="type" sort={sort} onSort={changeSort} />
      <SortableHeader label="Detalle" column="detail" sort={sort} onSort={changeSort} />
      <SortableHeader label="Salida" column="exit" sort={sort} onSort={changeSort} />
      <SortableHeader label="Calidad" column="quality" sort={sort} onSort={changeSort} />
      <th scope="col">Fuente</th>
      <th scope="col"><span className="sr-only">Acciones</span></th>
    </tr></thead><tbody>{visibleEvents.map((event) => <tr key={event.record_id}><td><time dateTime={primaryDate(event) ?? undefined}>{formatDateTime(primaryDate(event))}</time></td><td><span className="record-person"><i className="person-color" style={{backgroundColor: colors.get(event.entity_id)}} aria-hidden="true" /><strong>{titleCase(event.canonical_name)}</strong></span></td><td>{locationLabel(event.location)}</td><td>{recordLabel(event)}</td><td className="detail-cell" title={eventDetail(event)}>{eventDetail(event)}</td><td>{formatTime(event.exited_at)}</td><td><span className={`quality quality--${event.quality}`}>{qualityLabel(event.quality)}</span></td><td><SourceCell event={event} /></td><td><button className="record-detail-trigger" type="button" onClick={(browserEvent) => openEventDetail(event, browserEvent.currentTarget)} aria-label={`Ver detalle del registro de ${titleCase(event.canonical_name)} del ${formatDate(primaryDate(event))}`}><Search aria-hidden="true" /></button></td></tr>)}</tbody></table></div>{visibleEvents.length < sortedEvents.length && <button className="text-button records-more" type="button" onClick={() => setEventWindow({peopleKey, count: visibleEventCount + EVENT_PAGE_SIZE})}>Mostrar {Math.min(EVENT_PAGE_SIZE, sortedEvents.length - visibleEvents.length).toLocaleString("es-AR")} más</button>}</> : <p className="selection-empty">No hay eventos publicados para esta selección.</p>}</div>}
    <CoincidenceRanking results={coincidences} />
    {detailEvent && <RecordDetailDialog event={detailEvent} onClose={closeEventDetail} />}
  </section>;
}

function SortableHeader({label, column, sort, onSort}: {label: string; column: SortKey; sort: {key: SortKey; direction: SortDirection}; onSort: (key: SortKey) => void}) {
  const active = sort.key === column;
  return <th scope="col" aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}><button type="button" onClick={() => onSort(column)}>{label}{active ? sort.direction === "asc" ? <ArrowUp aria-hidden="true" /> : <ArrowDown aria-hidden="true" /> : null}</button></th>;
}

function SourceCell({event}: {event: AccessEvent}) {
  const source = event.sources?.[0];
  if (!source) return <span>—</span>;
  return isPublicUrl(source.url) ? <a className="source-link" href={`${source.url}#page=${source.page}`} target="_blank" rel="noreferrer"><FileText aria-hidden="true" />PDF p. {source.page}<ExternalLink aria-hidden="true" /></a> : <span className="source-local" title="El enlace público todavía no está disponible"><FileText aria-hidden="true" />Local p. {source.page}</span>;
}

function primaryDate(event: AccessEvent) { return event.occurred_at ?? event.entered_at ?? event.exited_at; }
function eventDetail(event: AccessEvent) { return [event.destination, event.purpose, event.activity, event.device, event.access_status].filter(Boolean).join(" · ") || "Sin detalle"; }
function formatDate(value: string | null) { return value ? DATE_FORMATTER.format(new Date(value)) : "Sin fecha"; }
function formatDateTime(value: string | null) { return value ? DATE_TIME_FORMATTER.format(new Date(value)) : "Sin fecha"; }
function formatTime(value: string | null) { return value ? TIME_FORMATTER.format(new Date(value)) : "—"; }
function qualityLabel(value: string) { return value === "high" ? "Alta" : value === "medium" ? "Media" : "Baja"; }
function recordLabel(event: AccessEvent) { if (event.record_type === "movement") return event.direction ? `Movimiento · ${event.direction}` : "Movimiento"; if (event.record_type === "vehicle") return "Vehículo"; if (event.record_type === "visitor") return "Visita"; return "Persona"; }
function sortValue(event: AccessEvent, key: SortKey) { if (key === "date") return primaryDate(event) ?? ""; if (key === "person") return event.canonical_name; if (key === "location") return locationLabel(event.location); if (key === "type") return recordLabel(event); if (key === "detail") return eventDetail(event); if (key === "exit") return event.exited_at ?? ""; return event.quality; }
function isPublicUrl(value: string) { return /^https?:\/\//i.test(value); }
