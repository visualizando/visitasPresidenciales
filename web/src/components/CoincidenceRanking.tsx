import {ChevronDown} from "lucide-react";
import {useMemo} from "react";
import type {AccessEvent, CoincidenceResult, Location, PersonSummary} from "../types";
import {locationLabel, titleCase} from "./SearchResults";

type Props = {results: CoincidenceResult[]; people: PersonSummary[]; events: AccessEvent[]};

type SelectedOverlap = {
  key: string;
  location: Location;
  people: string[];
  start: string;
  end: string;
  minutes: number;
};

const MAX_RENDERED_OVERLAPS = 100;
const MAX_INTERVAL_MS = 36 * 60 * 60 * 1_000;
const DATE_FORMATTER = new Intl.DateTimeFormat("es-AR", {day: "2-digit", month: "short", year: "numeric", timeZone: "UTC"});
const TIME_FORMATTER = new Intl.DateTimeFormat("es-AR", {hour: "2-digit", minute: "2-digit"});

export function CoincidenceRanking({results, people, events}: Props) {
  const overlaps = useMemo(() => selectedPeopleOverlaps(people, events), [people, events]);
  const showSelected = people.length > 1;
  if (!showSelected && !results.length) return null;
  const total = overlaps.length + results.length;

  return <section className="coincidences" aria-labelledby="coincidences-title">
    <details className="coincidence-disclosure">
      <summary><span><strong id="coincidences-title" role="heading" aria-level={3}>Coincidencias precisas: {total}</strong><small>{coincidenceSummary(overlaps.length, results.length, showSelected)}</small></span><ChevronDown aria-hidden="true" /></summary>
      <div className="coincidence-content"><div className="coincidence-groups">
        {showSelected && <section className="coincidence-group" aria-labelledby="selected-overlaps-title">
          <div className="coincidence-group-heading"><h4 id="selected-overlaps-title">Entre las personas seleccionadas</h4><p>Horarios completos que se superponen en la misma sede. Indican presencia simultánea registrada, no necesariamente un encuentro.</p></div>
          {overlaps.length ? <><div className="coincidence-table-wrap"><table className="coincidence-table coincidence-table--selected"><caption className="sr-only">Superposiciones horarias entre las personas seleccionadas</caption><thead><tr><th scope="col">Fecha</th><th scope="col">Sede</th><th scope="col">Personas</th><th scope="col">Horario en común</th></tr></thead><tbody>{overlaps.slice(0, MAX_RENDERED_OVERLAPS).map((overlap) => <tr key={overlap.key}><td><time dateTime={overlap.start}>{formatTimestampDate(overlap.start)}</time></td><td>{locationLabel(overlap.location)}</td><td>{overlap.people.map(titleCase).join(" y ")}</td><td><time dateTime={overlap.start}>{formatTime(overlap.start)}</time>–<time dateTime={overlap.end}>{formatTime(overlap.end)}</time> · {overlap.minutes} min</td></tr>)}</tbody></table></div>{overlaps.length > MAX_RENDERED_OVERLAPS && <p className="coincidence-limit">Se muestran las {MAX_RENDERED_OVERLAPS} superposiciones más recientes de {overlaps.length.toLocaleString("es-AR")}.</p>}</> : <p className="coincidence-empty">No hay horarios completos que se superpongan entre las personas seleccionadas.</p>}
        </section>}

        <section className="coincidence-group" aria-labelledby="automatic-coincidences-title">
          <div className="coincidence-group-heading"><h4 id="automatic-coincidences-title">Por destino y horario</h4><p><strong>Cálculo automático:</strong> cruza destinos y horarios de ingreso y egreso. Sirve como señal para revisar; no demuestra que las personas se hayan encontrado.</p></div>
          {results.length ? <div className="coincidence-table-wrap"><table className="coincidence-table"><caption className="sr-only">Coincidencias calculadas automáticamente por destino y horario</caption><thead><tr><th scope="col">Persona</th><th scope="col">Días</th><th scope="col">Última</th><th scope="col">Detalle</th></tr></thead><tbody>{results.slice(0, 5).map((result) => <tr key={result.entityId}><td><strong>{coincidencePairLabel(result)}</strong>{result.documentType && result.documentNumber && <small>{result.documentType} {result.documentNumber}</small>}</td><td>{result.days}</td><td><time dateTime={result.latestDate}>{formatDate(result.latestDate)}</time></td><td><details><summary>Ver {result.evidence.length} <ChevronDown aria-hidden="true" /></summary><ul>{result.evidence.slice(0, 10).map((item, evidenceIndex) => <li key={`${item.date}-${item.destination}-${evidenceIndex}`}><span><time dateTime={item.date}>{formatDate(item.date)}</time> · {locationLabel(item.location)}</span><strong>{item.destination}</strong><small>{item.ownerName ? <>{titleCase(item.ownerName)} · </> : null}{item.overlapStart}–{item.overlapEnd} · {item.overlapMinutes} min de superposición</small></li>)}</ul></details></td></tr>)}</tbody></table></div> : <p className="coincidence-empty">No se detectaron coincidencias precisas por destino y horario.</p>}
        </section>
      </div></div>
    </details>
  </section>;
}

function selectedPeopleOverlaps(people: PersonSummary[], events: AccessEvent[]) {
  if (people.length < 2) return [];
  const selectedIds = new Set(people.map((person) => person.entity_id));
  const names = new Map(people.map((person) => [person.entity_id, person.canonical_name]));
  const intervalsByDay = new Map<string, {entityId: string; location: Location; start: number; end: number}[]>();
  const seenIntervals = new Set<string>();

  for (const event of events) {
    if (!selectedIds.has(event.entity_id) || !event.entered_at || !event.exited_at) continue;
    const start = Date.parse(event.entered_at);
    const end = Date.parse(event.exited_at);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start || end - start > MAX_INTERVAL_MS) continue;
    const day = event.entered_at.slice(0, 10);
    if (event.exited_at.slice(0, 10) !== day) continue;
    const intervalKey = `${event.entity_id}|${event.location}|${start}|${end}`;
    if (seenIntervals.has(intervalKey)) continue;
    seenIntervals.add(intervalKey);
    const groupKey = `${day}|${event.location}`;
    const group = intervalsByDay.get(groupKey) ?? [];
    group.push({entityId: event.entity_id, location: event.location, start, end});
    intervalsByDay.set(groupKey, group);
  }

  const overlaps = new Map<string, SelectedOverlap>();
  for (const intervals of intervalsByDay.values()) for (let leftIndex = 0; leftIndex < intervals.length; leftIndex += 1) {
    const left = intervals[leftIndex];
    for (let rightIndex = leftIndex + 1; rightIndex < intervals.length; rightIndex += 1) {
      const right = intervals[rightIndex];
      if (left.entityId === right.entityId) continue;
      const start = Math.max(left.start, right.start);
      const end = Math.min(left.end, right.end);
      if (end <= start) continue;
      const entityIds = [left.entityId, right.entityId].sort();
      const key = `${entityIds.join("|")}|${left.location}|${start}|${end}`;
      if (overlaps.has(key)) continue;
      overlaps.set(key, {key, location: left.location, people: entityIds.map((entityId) => names.get(entityId) ?? "Persona"), start: new Date(start).toISOString(), end: new Date(end).toISOString(), minutes: Math.max(1, Math.round((end - start) / 60_000))});
    }
  }
  return [...overlaps.values()].sort((left, right) => right.start.localeCompare(left.start));
}

function coincidencePairLabel(result: CoincidenceResult) {
  const owners = [...new Set(result.evidence.map((item) => item.ownerName).filter(Boolean))].map(titleCase);
  return owners.length ? `${owners.join(", ")} ↔ ${titleCase(result.canonicalName)}` : titleCase(result.canonicalName);
}

function coincidenceSummary(overlaps: number, automatic: number, showSelected: boolean) {  const automaticLabel = `${automatic.toLocaleString("es-AR")} ${automatic === 1 ? "coincidencia automática" : "coincidencias automáticas"}`;
  if (!showSelected) return automaticLabel;
  return `${overlaps.toLocaleString("es-AR")} ${overlaps === 1 ? "superposición entre seleccionados" : "superposiciones entre seleccionados"} · ${automaticLabel}`;
}

function formatDate(value: string) { return DATE_FORMATTER.format(new Date(`${value}T00:00:00Z`)); }
function formatTimestampDate(value: string) { return DATE_FORMATTER.format(new Date(value)); }
function formatTime(value: string) { return TIME_FORMATTER.format(new Date(value)); }
