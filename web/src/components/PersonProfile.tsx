import {ArrowDown, ArrowUp, ExternalLink, FileText, X} from "lucide-react";
import {useEffect, useMemo, useRef, useState} from "react";
import type {AccessEvent, CoincidenceResult, PersonSummary} from "../types";
import {CoincidenceRanking} from "./CoincidenceRanking";
import {locationLabel, titleCase} from "./SearchResults";
import {comparisonSeries} from "../utils/personColors";

type SortKey = "date" | "person" | "location" | "type" | "detail" | "exit" | "quality";
type SortDirection = "asc" | "desc";

type PersonProfileProps = {
  people: PersonSummary[];
  events: AccessEvent[];
  loading: boolean;
  error: string | null;
  coincidences: CoincidenceResult[];
  coincidencesLoading: boolean;
  coincidencesError: string | null;
  onRemove: (entityId: string) => void;
  onClear: () => void;
};

export function PersonProfile({people, events, loading, error, coincidences, coincidencesLoading, coincidencesError, onRemove, onClear}: PersonProfileProps) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [sort, setSort] = useState<{key: SortKey; direction: SortDirection}>({key: "date", direction: "desc"});
  const series = useMemo(() => comparisonSeries(people), [people]);
  const colors = useMemo(() => new Map(series.map((person) => [person.entityId, person.color])), [series]);
  useEffect(() => { headingRef.current?.focus(); }, [people.length]);

  const sortedEvents = useMemo(() => [...events].sort((a, b) => {
    const difference = sortValue(a, sort.key).localeCompare(sortValue(b, sort.key), "es", {numeric: true});
    return sort.direction === "asc" ? difference : -difference;
  }), [events, sort]);

  const locations = [...new Set(people.flatMap((person) => person.locations))];
  const latest = events.reduce<string | null>((value, event) => {
    const date = primaryDate(event);
    return date && (!value || date > value) ? date : value;
  }, null);

  function changeSort(key: SortKey) {
    setSort((current) => current.key === key ? {key, direction: current.direction === "asc" ? "desc" : "asc"} : {key, direction: key === "date" ? "desc" : "asc"});
  }

  return <section className="profile" aria-labelledby="profile-title">
    <div className="profile-header">
      <div><p className="eyebrow">Selección comparada</p><h2 id="profile-title" ref={headingRef} tabIndex={-1}>{people.length === 1 ? titleCase(people[0].canonical_name) : `${people.length} personas o variantes seleccionadas`}</h2><p className="profile-description">Cada selección conserva su color en la tabla y los gráficos. Las identidades originales no se modifican.</p></div>
      <button className="text-button" type="button" onClick={onClear}>Limpiar selección</button>
    </div>

    <div className="selected-people" aria-label="Personas seleccionadas">{people.map((person) => <div className="person-chip" key={person.entity_id} style={{borderColor: colors.get(person.entity_id)}}><i className="person-color" style={{backgroundColor: colors.get(person.entity_id)}} aria-hidden="true" /><span><strong>{titleCase(person.canonical_name)}</strong><small>{person.document_type ?? "Documento"} <bdi>{person.document_number ?? "no informado"}</bdi></small></span><button type="button" onClick={() => onRemove(person.entity_id)} aria-label={`Quitar ${titleCase(person.canonical_name)}`}><X aria-hidden="true" /></button></div>)}</div>

    <div className="profile-stats"><span><strong>{events.length.toLocaleString("es-AR")}</strong> registros cargados</span><span><strong>{locations.map(locationLabel).join(" y ")}</strong> sedes</span><span><strong>{formatDate(latest)}</strong> última aparición</span></div>
    <p className="privacy-note"><strong>Dato publicado por la fuente.</strong> Verificá el PDF indicado antes de reutilizarlo.</p>

    <CoincidenceRanking results={coincidences} loading={coincidencesLoading} error={coincidencesError} />

    {loading && <p role="status">Cargando registros…</p>}
    {error && <div className="notice notice--error" role="alert"><strong>No se pudieron cargar los registros.</strong><span>{error}</span></div>}
    {!loading && !error && <div className="records-section"><div className="records-heading"><h3>Entradas y movimientos</h3><span>{events.length.toLocaleString("es-AR")} filas</span></div>{events.length ? <div className="records-table-wrap"><table className="records-table"><caption className="sr-only">Entradas y movimientos de las personas seleccionadas</caption><thead><tr>
      <SortableHeader label="Fecha y hora" column="date" sort={sort} onSort={changeSort} />
      <SortableHeader label="Persona" column="person" sort={sort} onSort={changeSort} />
      <SortableHeader label="Sede" column="location" sort={sort} onSort={changeSort} />
      <SortableHeader label="Tipo" column="type" sort={sort} onSort={changeSort} />
      <SortableHeader label="Detalle" column="detail" sort={sort} onSort={changeSort} />
      <SortableHeader label="Salida" column="exit" sort={sort} onSort={changeSort} />
      <SortableHeader label="Calidad" column="quality" sort={sort} onSort={changeSort} />
      <th scope="col">Fuente</th>
    </tr></thead><tbody>{sortedEvents.map((event) => <tr key={event.record_id}><td><time dateTime={primaryDate(event) ?? undefined}>{formatDateTime(primaryDate(event))}</time></td><td><span className="record-person"><i className="person-color" style={{backgroundColor: colors.get(event.entity_id)}} aria-hidden="true" /><strong>{titleCase(event.canonical_name)}</strong></span></td><td>{locationLabel(event.location)}</td><td>{recordLabel(event)}</td><td className="detail-cell" title={eventDetail(event)}>{eventDetail(event)}</td><td>{formatTime(event.exited_at)}</td><td><span className={`quality quality--${event.quality}`}>{qualityLabel(event.quality)}</span></td><td><SourceCell event={event} /></td></tr>)}</tbody></table></div> : <p className="selection-empty">No hay eventos publicados para esta selección.</p>}</div>}
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
function formatDate(value: string | null) { return value ? new Intl.DateTimeFormat("es-AR", {day: "2-digit", month: "short", year: "numeric", timeZone: "UTC"}).format(new Date(value)) : "Sin fecha"; }
function formatDateTime(value: string | null) { return value ? new Intl.DateTimeFormat("es-AR", {day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit"}).format(new Date(value)) : "Sin fecha"; }
function formatTime(value: string | null) { return value ? new Intl.DateTimeFormat("es-AR", {hour: "2-digit", minute: "2-digit"}).format(new Date(value)) : "—"; }
function qualityLabel(value: string) { return value === "high" ? "Alta" : value === "medium" ? "Media" : "Baja"; }
function recordLabel(event: AccessEvent) { if (event.record_type === "movement") return event.direction ? `Movimiento · ${event.direction}` : "Movimiento"; if (event.record_type === "vehicle") return "Vehículo"; if (event.record_type === "visitor") return "Visita"; return "Persona"; }
function sortValue(event: AccessEvent, key: SortKey) { if (key === "date") return primaryDate(event) ?? ""; if (key === "person") return event.canonical_name; if (key === "location") return locationLabel(event.location); if (key === "type") return recordLabel(event); if (key === "detail") return eventDetail(event); if (key === "exit") return event.exited_at ?? ""; return event.quality; }
function isPublicUrl(value: string) { return /^https?:\/\//i.test(value); }
