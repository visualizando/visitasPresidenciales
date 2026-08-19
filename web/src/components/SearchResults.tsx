import {ArrowRight, Building2, CalendarDays} from "lucide-react";
import type {PersonSummary} from "../types";

export function SearchResults({query, results, loading, error, onSelect}: {query: string; results: PersonSummary[]; loading: boolean; error: string | null; onSelect: (person: PersonSummary) => void}) {
  if (error) return <div className="notice notice--error" role="alert"><strong>No se pudo buscar.</strong><span>{error}. Volvé a intentar.</span></div>;
  if (loading) return <div className="results-loading" aria-hidden="true">{Array.from({length: 3}, (_, index) => <div className="result-skeleton" key={index} />)}</div>;
  if (query.trim().length < 2) return <div className="search-guidance"><p>Escribí al menos dos letras o tres dígitos.</p><span>Podés buscar por apellido, nombre, DNI o CUIL.</span></div>;
  if (!results.length) return <div className="empty-state"><strong>Sin resultados para “{query}”</strong><p>Revisá la escritura o probá sin filtros.</p></div>;
  return <div className="results-list">{results.map((person) => <button type="button" className="result-card" key={person.entity_id} onClick={() => onSelect(person)}><span className="result-main"><strong>{titleCase(person.canonical_name)}</strong><span>{person.document_type ?? "Documento"} <bdi>{person.document_number ?? "no informado"}</bdi></span></span><span className="result-meta"><span><Building2 aria-hidden="true" />{person.locations.map(locationLabel).join(" · ")}</span><span><CalendarDays aria-hidden="true" />{person.record_count.toLocaleString("es-AR")} registros</span></span><ArrowRight className="result-arrow" aria-hidden="true" /></button>)}</div>;
}

export function titleCase(value: string) { return value.toLocaleLowerCase("es-AR").replace(/(^|\s)(\p{L})/gu, (_, space, letter) => `${space}${letter.toLocaleUpperCase("es-AR")}`); }
export function locationLabel(value: string) { return value === "casa-rosada" ? "Casa Rosada" : "Olivos"; }

