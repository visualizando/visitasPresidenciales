import {Building2, CalendarDays, Check, Plus} from "lucide-react";
import type {PersonSummary} from "../types";
import {AudienciasBadge} from "./AudienciasBadge";

type SearchResultsProps = {
  query: string;
  results: PersonSummary[];
  selectedIds: Set<string>;
  loading: boolean;
  phase: "searching" | "broadening" | null;
  error: string | null;
  onToggle: (person: PersonSummary) => void;
};

export function SearchResults({query, results, selectedIds, loading, phase, error, onToggle}: SearchResultsProps) {
  if (error) return <div className="notice notice--error" role="alert"><strong>No se pudo buscar.</strong><span>{error}. Volvé a intentar.</span></div>;
  if (loading) return <div className="results-loading"><p role="status">{phase === "broadening" ? "Probando una búsqueda más amplia…" : "Buscando coincidencias…"}</p><div aria-hidden="true">{Array.from({length: 3}, (_, index) => <div className="result-skeleton" key={index} />)}</div></div>;
  if (query.trim().length < 2) return <div className="search-guidance"><p>Escribí al menos dos letras o tres dígitos.</p><span>Podés buscar por apellido, nombre, DNI o CUIL.</span></div>;
  if (!results.length) return <div className="empty-state"><strong>Sin resultados para “{query}”</strong><p>Revisá la escritura o probá sin filtros.</p></div>;
  return <div className="results-list" aria-label="Coincidencias">{results.map((person) => {
    const isSelected = selectedIds.has(person.entity_id);
    return <button type="button" className={`result-card${isSelected ? " result-card--selected" : ""}`} key={person.entity_id} aria-pressed={isSelected} onClick={() => onToggle(person)}>
      <span className="result-main"><span className="result-title-row"><strong>{titleCase(person.canonical_name)}</strong>{person.audiencias_cr && <AudienciasBadge />}</span><span className="result-doc">{person.document_type ?? "Documento"} <bdi>{person.document_number ?? "no informado"}</bdi></span></span>
      <span className="result-meta"><span><Building2 aria-hidden="true" />{person.locations.map(locationLabel).join(" · ")}</span><span><CalendarDays aria-hidden="true" />{person.record_count.toLocaleString("es-AR")} registros</span></span>
      <span className="result-action" aria-hidden="true">{isSelected ? <Check /> : <Plus />}</span>
    </button>;
  })}</div>;
}

export function titleCase(value: string) { return value.toLocaleLowerCase("es-AR").replace(/(^|\s)(\p{L})/gu, (_, space, letter) => `${space}${letter.toLocaleUpperCase("es-AR")}`); }
export function locationLabel(value: string) { return value === "casa-rosada" ? "Casa Rosada" : "Olivos"; }
