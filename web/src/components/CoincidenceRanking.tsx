import {ChevronDown} from "lucide-react";
import type {CoincidenceResult} from "../types";
import {locationLabel, titleCase} from "./SearchResults";

type Props = {results: CoincidenceResult[]};

export function CoincidenceRanking({results}: Props) {
  if (!results.length) return null;
  return <section className="coincidences" aria-labelledby="coincidences-title">
    <div className="records-heading"><div><h3 id="coincidences-title">Coincidencias precisas</h3><p>Mismo destino, con horarios de entrada y salida similares.</p></div></div>
    <div className="coincidence-table-wrap"><table className="coincidence-table"><caption className="sr-only">Personas con coincidencias precisas</caption><thead><tr><th scope="col">Persona</th><th scope="col">Días</th><th scope="col">Última</th><th scope="col">Detalle</th></tr></thead><tbody>{results.slice(0, 5).map((result) => <tr key={result.entityId}><td><strong>{titleCase(result.canonicalName)}</strong>{result.documentType && result.documentNumber && <small>{result.documentType} {result.documentNumber}</small>}</td><td>{result.days}</td><td><time dateTime={result.latestDate}>{formatDate(result.latestDate)}</time></td><td><details><summary>Ver {result.evidence.length} <ChevronDown aria-hidden="true" /></summary><ul>{result.evidence.slice(0, 10).map((item, evidenceIndex) => <li key={`${item.date}-${item.destination}-${evidenceIndex}`}><span><time dateTime={item.date}>{formatDate(item.date)}</time> · {locationLabel(item.location)}</span><strong>{item.destination}</strong><small>{item.overlapStart}–{item.overlapEnd} · {item.overlapMinutes} min juntos</small></li>)}</ul></details></td></tr>)}</tbody></table></div>
  </section>;
}

function formatDate(value: string) { return new Intl.DateTimeFormat("es-AR", {day: "2-digit", month: "short", year: "numeric", timeZone: "UTC"}).format(new Date(`${value}T00:00:00Z`)); }
