import {ExternalLink, FileText, X} from "lucide-react";
import {useEffect, useRef} from "react";
import type {AccessEvent, PersonSummary} from "../types";
import {locationLabel, titleCase} from "./SearchResults";

type PersonProfileProps = {
  person: PersonSummary;
  events: AccessEvent[];
  loading: boolean;
  error: string | null;
  onClose: () => void;
};

export function PersonProfile({person, events, loading, error, onClose}: PersonProfileProps) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    headingRef.current?.focus();
  }, [person.entity_id]);

  return (
    <section className="profile" aria-labelledby="profile-title">
      <div className="profile-header">
        <div>
          <p className="eyebrow">Ficha individual</p>
          <h2 id="profile-title" ref={headingRef} tabIndex={-1}>
            {titleCase(person.canonical_name)}
          </h2>
          <p className="profile-document">
            {person.document_type ?? "Documento"}{" "}
            <bdi>{person.document_number ?? "no informado"}</bdi>
          </p>
        </div>
        <button className="icon-button" type="button" onClick={onClose} aria-label="Cerrar ficha">
          <X aria-hidden="true" />
        </button>
      </div>
      <div className="profile-stats">
        <span><strong>{person.record_count.toLocaleString("es-AR")}</strong> registros</span>
        <span><strong>{person.locations.map(locationLabel).join(" y ")}</strong> sedes</span>
        <span><strong>{formatDate(person.last_seen)}</strong> última aparición</span>
      </div>
      <div className="privacy-note">
        <strong>Dato publicado por la fuente.</strong> Verificá la página indicada del PDF antes de reutilizarlo.
      </div>
      {loading && <p role="status">Cargando cronología…</p>}
      {error && (
        <div className="notice notice--error" role="alert">
          <strong>No se pudo cargar la cronología.</strong><span>{error}</span>
        </div>
      )}
      {!loading && !error && (
        <div className="timeline">
          <h3>Cronología</h3>
          {events.length ? events.map((event) => (
            <article className="event-card" key={event.record_id}>
              <div className="event-date">
                <time dateTime={primaryDate(event) ?? undefined}>{formatDateTime(primaryDate(event))}</time>
                <span className={`quality quality--${event.quality}`}>{qualityLabel(event.quality)}</span>
              </div>
              <div className="event-body">
                <strong>{recordLabel(event)}</strong>
                <p>{[event.destination, event.purpose, event.activity, event.device].filter(Boolean).join(" · ") || "Sin contexto adicional en la fuente"}</p>
                <dl>
                  <div><dt>Sede</dt><dd>{locationLabel(event.location)}</dd></div>
                  {event.exited_at && <div><dt>Salida</dt><dd>{formatDateTime(event.exited_at)}</dd></div>}
                  {event.access_status && <div><dt>Estado</dt><dd>{event.access_status}</dd></div>}
                </dl>
                <div className="source-links">
                  {event.sources?.map((source, index) => isPublicUrl(source.url) ? (
                    <a key={`${source.url}-${source.page}-${index}`} href={`${source.url}#page=${source.page}`} target="_blank" rel="noreferrer">
                      <FileText aria-hidden="true" />Ver PDF, página {source.page}<ExternalLink aria-hidden="true" />
                    </a>
                  ) : (
                    <span key={`${source.url}-${source.page}-${index}`}>
                      <FileText aria-hidden="true" />Fuente local, página {source.page}; enlace público pendiente
                    </span>
                  ))}
                </div>
              </div>
            </article>
          )) : <p className="empty-state">No hay eventos publicados para esta ficha.</p>}
        </div>
      )}
    </section>
  );
}

function primaryDate(event: AccessEvent) {
  return event.occurred_at ?? event.entered_at ?? event.exited_at;
}

function formatDate(value: string | null) {
  return value ? new Intl.DateTimeFormat("es-AR", {day: "2-digit", month: "short", year: "numeric", timeZone: "UTC"}).format(new Date(value)) : "Sin fecha";
}

function formatDateTime(value: string | null) {
  return value ? new Intl.DateTimeFormat("es-AR", {dateStyle: "medium", timeStyle: "short"}).format(new Date(value)) : "Sin fecha";
}

function qualityLabel(value: string) {
  return value === "high" ? "Extracción alta" : value === "medium" ? "Revisar contexto" : "Calidad baja";
}

function recordLabel(event: AccessEvent) {
  if (event.record_type === "movement") return event.direction ? `Movimiento: ${event.direction}` : "Movimiento";
  if (event.record_type === "vehicle") return "Ingreso en vehículo";
  if (event.record_type === "visitor") return "Visita";
  return "Ingreso de persona";
}

function isPublicUrl(value: string) {
  return /^https?:\/\//i.test(value);
}
