import {ArrowDown, ArrowUp, ClipboardList, Download, Eraser, ExternalLink, FileText, House, X} from "lucide-react";
import {useEffect, useMemo, useRef, useState} from "react";
import type {AccessEvent, AudienciaDetail, CoincidenceResult, PersonSummary} from "../types";
import {CoincidenceRanking} from "./CoincidenceRanking";
import {locationLabel, titleCase} from "./SearchResults";
import {comparisonSeries} from "../utils/personColors";
import {buildSelectedEventsCsv, selectedEventsFilename} from "../utils/selectedEventsCsv";
import {RecordDetailDialog} from "./RecordDetailDialog";
import {buildTimelineRows} from "../utils/mergeAudiencias";

type SortKey = "date" | "entry" | "exit" | "person" | "location" | "type" | "detail";
type SortDirection = "asc" | "desc";

const DATE_FORMATTER = new Intl.DateTimeFormat("es-AR", {day: "2-digit", month: "short", year: "numeric", timeZone: "UTC"});
const TIME_FORMATTER = new Intl.DateTimeFormat("es-AR", {hour: "2-digit", minute: "2-digit"});
const SORT_COLLATOR = new Intl.Collator("es", {numeric: true});
const EVENT_PAGE_SIZE = 100;

type PersonProfileProps = {
  people: PersonSummary[];
  events: AccessEvent[];
  audiencias?: Map<string, AudienciaDetail[]>;
  loading: boolean;
  error: string | null;
  coincidences: CoincidenceResult[];
  onRemove: (entityId: string) => void;
  onClear: () => void;
};

export function PersonProfile({people, events, audiencias, loading, error, coincidences, onRemove, onClear}: PersonProfileProps) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const detailTriggerRef = useRef<HTMLButtonElement | null>(null);
  const [detailEvent, setDetailEvent] = useState<AccessEvent | null>(null);
  const [sort, setSort] = useState<{key: SortKey; direction: SortDirection}>({key: "date", direction: "desc"});
  const peopleKey = people.map((person) => person.entity_id).sort().join(",");
  const [eventWindow, setEventWindow] = useState({peopleKey, count: EVENT_PAGE_SIZE});
  const visibleEventCount = eventWindow.peopleKey === peopleKey ? eventWindow.count : EVENT_PAGE_SIZE;
  const series = useMemo(() => comparisonSeries(people), [people]);
  const colors = useMemo(() => new Map(series.map((person) => [person.entityId, person.color])), [series]);
  const rows = useMemo(() => buildTimelineRows(events, audiencias ?? new Map(), people), [events, audiencias, people]);
  useEffect(() => { headingRef.current?.focus(); }, [people.length]);

  const sortedEvents = useMemo(() => [...rows].sort((a, b) => {
    const difference = SORT_COLLATOR.compare(sortValue(a, sort.key), sortValue(b, sort.key));
    return sort.direction === "asc" ? difference : -difference;
  }), [rows, sort]);
  const visibleEvents = sortedEvents.slice(0, visibleEventCount);

  const locations = [...new Set(people.flatMap((person) => person.locations))];
  const latest = rows.reduce<string | null>((value, event) => {
    const date = primaryDate(event);
    return date && (!value || date > value) ? date : value;
  }, null);

  function changeSort(key: SortKey) {
    setSort((current) => current.key === key ? {key, direction: current.direction === "asc" ? "desc" : "asc"} : {key, direction: key === "date" ? "desc" : "asc"});
  }

  function downloadSelection() {
    const blobUrl = URL.createObjectURL(new Blob([buildSelectedEventsCsv(rows)], {type: "text/csv;charset=utf-8"}));
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
    </div>

    <div className="selected-people" aria-label="Personas seleccionadas">{people.map((person) => <div className="person-chip" key={person.entity_id} style={{borderColor: colors.get(person.entity_id)}}><i className="person-color" style={{backgroundColor: colors.get(person.entity_id)}} aria-hidden="true" /><span><strong>{titleCase(person.canonical_name)}</strong><small>{person.document_type ?? "Documento"} <bdi>{person.document_number ?? "no informado"}</bdi></small></span><button type="button" onClick={() => onRemove(person.entity_id)} aria-label={`Quitar ${titleCase(person.canonical_name)}`}><X aria-hidden="true" /></button></div>)}</div>

    <div className="profile-stats"><span><strong>{rows.length.toLocaleString("es-AR")}</strong> registros</span><span>{locations.length === 1 ? "Sede" : "Sedes"}: <strong>{locations.map(locationLabel).join(" y ")}</strong></span><span>Última aparición: <strong>{formatDate(latest)}</strong></span></div>
    {loading && <p role="status">Cargando registros…</p>}
    {error && <div className="notice notice--error" role="alert"><strong>No se pudieron cargar los registros.</strong><span>{error}</span></div>}
    {!loading && !error && <div className="records-section"><div className="records-heading"><h3>Visitas: a Casa Rosada / Quinta de Olivos según registro - Audiencias: según registro de audiencias</h3><div className="records-heading-actions"><span>{visibleEvents.length.toLocaleString("es-AR")} de {rows.length.toLocaleString("es-AR")} filas</span><button className="selection-download" type="button" onClick={onClear}><Eraser aria-hidden="true" />Limpiar selección</button>{rows.length > 0 && <button className="selection-download" type="button" onClick={downloadSelection} aria-label={`Descargar ${rows.length.toLocaleString("es-AR")} ${rows.length === 1 ? "registro" : "registros"} de la selección en CSV`}><Download aria-hidden="true" />Descargar CSV</button>}</div></div>{rows.length ? <><div className="records-table-wrap"><table className="records-table"><caption className="sr-only">Visitas y audiencias de las personas seleccionadas</caption><thead><tr>
      <SortableHeader label="Fecha" column="date" sort={sort} onSort={changeSort} />
      <SortableHeader label="Ingreso" column="entry" sort={sort} onSort={changeSort} />
      <SortableHeader label="Egreso" column="exit" sort={sort} onSort={changeSort} />
      <SortableHeader label="Persona" column="person" sort={sort} onSort={changeSort} />
      <SortableHeader label="Sede" column="location" sort={sort} onSort={changeSort} />
      <SortableHeader label="Tipo" column="type" sort={sort} onSort={changeSort} />
      <SortableHeader label="Detalle" column="detail" sort={sort} onSort={changeSort} />
      <th scope="col">Fuente</th>
      <th scope="col"><span className="sr-only">Acciones</span></th>
    </tr></thead><tbody>{visibleEvents.map((event) => <TimelineRow key={event.record_id} event={event} colors={colors} onOpenDetail={openEventDetail} />)}</tbody></table></div>{visibleEvents.length < sortedEvents.length && <button className="text-button records-more" type="button" onClick={() => setEventWindow({peopleKey, count: visibleEventCount + EVENT_PAGE_SIZE})}>Mostrar {Math.min(EVENT_PAGE_SIZE, sortedEvents.length - visibleEvents.length).toLocaleString("es-AR")} más</button>}</> : <p className="selection-empty">No hay eventos publicados para esta selección.</p>}</div>}
    <CoincidenceRanking results={coincidences} people={people} events={rows} />
    {detailEvent && <RecordDetailDialog event={detailEvent} onClose={closeEventDetail} />}
  </section>;
}

function SortableHeader({label, column, sort, onSort}: {label: string; column: SortKey; sort: {key: SortKey; direction: SortDirection}; onSort: (key: SortKey) => void}) {
  const active = sort.key === column;
  return <th scope="col" aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}><button type="button" onClick={() => onSort(column)}>{label}{active ? sort.direction === "asc" ? <ArrowUp aria-hidden="true" /> : <ArrowDown aria-hidden="true" /> : null}</button></th>;
}

function TimelineRow({event, colors, onOpenDetail}: {event: AccessEvent; colors: Map<string, string>; onOpenDetail: (event: AccessEvent, trigger: HTMLButtonElement) => void}) {
  const isAudiencia = Boolean(event.audiencia);
  return <tr>
    <td><time dateTime={primaryDate(event) ?? undefined}>{formatDate(primaryDate(event))}</time></td>
    <td><time dateTime={entryDate(event) ?? undefined}>{formatTime(entryDate(event))}</time></td>
    <td><time dateTime={exitDate(event) ?? undefined}>{formatTime(exitDate(event))}</time></td>
    <td><span className="record-person"><i className="person-color" style={{backgroundColor: colors.get(event.entity_id)}} aria-hidden="true" /><strong>{titleCase(event.canonical_name)}</strong></span></td>
    <td>{isAudiencia ? "Casa Rosada" : locationLabel(event.location)}</td>
    <td><TypeCell event={event} /></td>
    <td className="detail-cell"><AudienciaDetailCell event={event} /></td>
    <td><SourceCell event={event} /></td>
    <td><button className="record-detail-trigger" type="button" onClick={(browserEvent) => onOpenDetail(event, browserEvent.currentTarget)} aria-label={`Abrir detalle del registro de ${titleCase(event.canonical_name)} del ${formatDate(primaryDate(event))}`}><FileText aria-hidden="true" /></button></td>
  </tr>;
}

function TypeCell({event}: {event: AccessEvent}) {
  const audiencia = event.audiencia;
  const fused = event.fused_audiencias?.length;
  if (audiencia) {
    return <span className="record-type"><ClipboardList className="type-icon" aria-hidden="true" />Audiencia</span>;
  }
  if (fused) {
    return <span className="record-type"><House className="type-icon" aria-hidden="true" />{recordLabel(event)} + <ClipboardList className="type-icon" aria-hidden="true" />Audiencia</span>;
  }
  return <span className="record-type"><House className="type-icon" aria-hidden="true" />{recordLabel(event)}</span>;
}

function AudienciaDetailCell({event}: {event: AccessEvent}) {
  const audiencia = event.audiencia;
  const base = audiencia ? audienciaDetail(audiencia) : eventDetail(event);
  const fused = event.fused_audiencias;
  if (audiencia) {
    return <span className="audiencia-inline" title={base}><b>{titleCase(audiencia.official_name)}</b>{(audiencia.official_cargo || audiencia.lugar) && <><span className="audiencia-sep" aria-hidden="true">–</span><span>{audiencia.official_cargo || audiencia.lugar}</span></>}</span>;
  }
  return <><span title={base}>{base}</span>{fused?.map((item) => <span className="fused-audiencia" key={item.audiencia_id}><b>{titleCase(item.official_name)}</b><span>{item.official_cargo || item.lugar}</span></span>)}</>;
}

function SourceCell({event}: {event: AccessEvent}) {
  const audiencia = event.audiencia;
  const fused = event.fused_audiencias;
  if (audiencia && !fused?.length) {
    return <span className="source-audiencia"><ClipboardList className="type-icon" aria-hidden="true" />Registro de Audiencias</span>;
  }
  if (fused?.length) {
    return <span className="source-stack"><SourceLink event={event} /><span className="source-audiencia"><ClipboardList className="type-icon" aria-hidden="true" />Registro de Audiencias</span></span>;
  }
  return <SourceLink event={event} />;
}

function SourceLink({event}: {event: AccessEvent}) {
  const source = event.sources?.[0];
  if (!source) return <span>—</span>;
  const filename = sourceFileName(source.path || source.url);
  const label = <><House className="type-icon" aria-hidden="true" /><span className="source-file-name">{filename}</span><span>· p. {source.page}</span></>;
  return isPublicUrl(source.url) ? <a className="source-link" href={`${source.url}#page=${source.page}`} target="_blank" rel="noreferrer" title={`Abrir ${filename}, página ${source.page}`}>{label}<ExternalLink aria-hidden="true" /></a> : <span className="source-local" title={`${filename} · enlace público no disponible`}>{label}</span>;
}

function primaryDate(event: AccessEvent) { return event.occurred_at ?? event.entered_at ?? event.exited_at; }
function entryDate(event: AccessEvent) { return event.entered_at ?? (event.direction?.toLowerCase() === "entrada" ? event.occurred_at : null); }
function exitDate(event: AccessEvent) { return event.exited_at ?? (event.direction?.toLowerCase() === "salida" ? event.occurred_at : null); }
function eventDetail(event: AccessEvent) { return [event.destination, event.purpose, event.activity, event.device, event.access_status].filter(Boolean).join(" · ") || "Sin detalle"; }
function audienciaDetail(audiencia: {official_name: string; official_cargo: string; lugar: string}) { return [audiencia.official_name, audiencia.official_cargo, audiencia.lugar].filter(Boolean).join(" · ") || "Sin detalle"; }
function formatDate(value: string | null) { return value ? DATE_FORMATTER.format(new Date(value)) : "Sin fecha"; }
function formatTime(value: string | null) { return value ? TIME_FORMATTER.format(new Date(value)) : "—"; }
function recordLabel(event: AccessEvent) { if (event.record_type === "movement") return event.direction ? `Movimiento · ${event.direction}` : "Movimiento"; if (event.record_type === "vehicle") return "Vehículo"; if (event.record_type === "visitor") return "Visita"; return "Persona"; }
function sortValue(event: AccessEvent, key: SortKey) { if (key === "date") return primaryDate(event) ?? ""; if (key === "entry") return entryDate(event) ?? ""; if (key === "exit") return exitDate(event) ?? ""; if (key === "person") return event.canonical_name; if (key === "location") return event.audiencia ? "Casa Rosada" : locationLabel(event.location); if (key === "type") return event.audiencia ? "Audiencia" : recordLabel(event); return event.audiencia ? audienciaDetail(event.audiencia) : eventDetail(event); }
function isPublicUrl(value: string) { return /^https?:\/\//i.test(value); }
function sourceFileName(value: string) { return value.split(/[\\/]/).pop() || "PDF de origen"; }
