import {ChevronDown} from "lucide-react";
import type {CoincidenceResult} from "../types";
import {locationLabel, titleCase} from "./SearchResults";

type Props = {results: CoincidenceResult[]; loading: boolean; error: string | null};

export function CoincidenceRanking({results, loading, error}: Props) {
  return <section className="coincidences" aria-labelledby="coincidences-title">
    <div className="records-heading"><div><h3 id="coincidences-title">Personas con más coincidencias</h3><p>Ranking por días con horarios superpuestos al menos 10 minutos en el mismo destino.</p></div><span>Top 10</span></div>
    <p className="coincidence-warning"><strong>Importante:</strong> la coincidencia en los registros indica presencia compatible; no demuestra un encuentro ni una interacción.</p>
    {loading && <p role="status">Calculando coincidencias…</p>}
    {error && <div className="notice notice--error" role="alert"><strong>No se pudieron cargar las coincidencias.</strong><span>{error}</span></div>}
    {!loading && !error && !results.length && <p className="selection-empty">No encontramos intervalos comparables con otras personas para esta selección.</p>}
    {!loading && !error && results.length > 0 && <div className="coincidence-table-wrap"><table className="coincidence-table"><caption className="sr-only">Diez personas con mayor cantidad de días coincidentes</caption><thead><tr><th scope="col">#</th><th scope="col">Persona</th><th scope="col">Días</th><th scope="col">Episodios</th><th scope="col">Tiempo superpuesto</th><th scope="col">Destino específico</th><th scope="col">Última</th><th scope="col">Evidencia</th></tr></thead><tbody>{results.map((result, index) => <tr key={result.entityId}><td>{index + 1}</td><td><strong>{titleCase(result.canonicalName)}</strong><small>{result.documentType && result.documentNumber ? `${result.documentType} ${result.documentNumber}` : "Documento no informado"}</small></td><td>{result.days}</td><td>{result.episodes}</td><td>{formatDuration(result.overlapMinutes)}</td><td>{Math.round(result.specificEpisodes / result.episodes * 100)}%</td><td><time dateTime={result.latestDate}>{formatDate(result.latestDate)}</time></td><td><details><summary>Ver <ChevronDown aria-hidden="true" /></summary><ul>{result.evidence.slice(0, 20).map((item, evidenceIndex) => <li key={`${item.date}-${item.destination}-${evidenceIndex}`}><span><time dateTime={item.date}>{formatDate(item.date)}</time> · {locationLabel(item.location)}</span><strong>{item.destination}</strong><small>{item.overlapStart}–{item.overlapEnd} · {item.overlapMinutes} min · destino {item.specificDestination ? "específico" : "general"}</small></li>)}</ul>{result.evidence.length > 20 && <p className="evidence-limit">20 más recientes de {result.evidence.length} episodios.</p>}</details></td></tr>)}</tbody></table></div>}
  </section>;
}

function formatDuration(minutes: number) { const hours = Math.floor(minutes / 60); const rest = minutes % 60; return hours ? `${hours} h ${rest ? `${rest} min` : ""}`.trim() : `${rest} min`; }
function formatDate(value: string) { return new Intl.DateTimeFormat("es-AR", {day: "2-digit", month: "short", year: "numeric", timeZone: "UTC"}).format(new Date(`${value}T00:00:00Z`)); }
