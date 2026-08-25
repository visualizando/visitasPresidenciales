import {useData} from "../hooks/useData";
import type {CoverageData, CoverageGap, Location} from "../types";

const LOCATION_LABELS: Record<Location, string> = {"casa-rosada": "Casa Rosada", olivos: "Olivos"};

export function CoverageReport({compact = false}: {compact?: boolean}) {
  const coverage = useData<CoverageData>("analytics/coverage.json");
  const data = coverage.data;
  return <>
    {!compact && <div className="section-heading coverage-heading">
      <div><p className="eyebrow">Cobertura</p><h2 id="coverage-title">Qué falta y por qué</h2></div>
      <p>Este informe distingue los períodos sin registros de los archivos que no pudieron incorporarse. Un hueco no demuestra que no haya habido accesos.</p>
    </div>}
    <div className="coverage-panel">
      {coverage.loading && <p className="coverage-status" role="status">Cargando informe de cobertura…</p>}
      {coverage.error && <div className="notice notice--error" role="alert"><strong>No se pudo cargar el informe de cobertura.</strong><span>{coverage.error}</span></div>}
      {data && !coverage.loading && !coverage.error && <>
        <div className="coverage-summary" aria-label="Resumen de archivos">
          <span><strong>{data.summary.active_files.toLocaleString("es-AR")}</strong> archivos incorporados</span>
          <span><strong>{data.summary.quarantined_files}</strong> no legibles o sin parser</span>
          <span><strong>{data.summary.missing_files}</strong> ya no visibles en origen</span>
          <span><strong>{data.summary.zero_record_files}</strong> sin registros utilizables</span>
        </div>
        {data.older_period && <p className="coverage-note"><strong>Antes de {formatDate(data.older_period.end_date)}:</strong> {data.older_period.reason}</p>}
        <div className="coverage-locations">
          {data.locations.map((location) => <details key={location.location} open={location.gaps.length > 0}>
            <summary><span>{LOCATION_LABELS[location.location]}</span><small>{location.months_with_data} meses con datos · {location.gaps.length} período{location.gaps.length === 1 ? "" : "s"} sin registros</small></summary>
            {location.gaps.length ? <ul>{location.gaps.map((gap) => <li key={`${gap.start_month}-${gap.end_month}`}><strong>{formatPeriod(gap)}</strong><span>{gap.reason}</span></li>)}</ul> : <p className="coverage-clear">No hay meses sin registros dentro de la cobertura actual.</p>}
          </details>)}
        </div>
        {data.file_issues.length > 0 ? <details className="coverage-files">
          <summary>Archivos sin registros o con problemas ({data.file_issues.length})</summary>
          <ul>{data.file_issues.map((file) => <li key={file.path}><strong>{formatMonth(`${file.year}-${String(file.month).padStart(2, "0")}`)} · {LOCATION_LABELS[file.location]}</strong><span>{file.reason}</span><small>{file.path}</small></li>)}</ul>
        </details> : <p className="coverage-clear">En la última actualización no quedaron archivos marcados como faltantes, escaneados o con formato no compatible.</p>}
      </>}
    </div>
  </>;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("es-AR", {month: "long", year: "numeric", timeZone: "UTC"}).format(new Date(`${value}T00:00:00Z`));
}

function formatMonth(value: string) {
  return new Intl.DateTimeFormat("es-AR", {month: "short", year: "numeric", timeZone: "UTC"}).format(new Date(`${value}-01T00:00:00Z`));
}

function formatPeriod(gap: CoverageGap) {
  const start = formatMonth(gap.start_month);
  return gap.start_month === gap.end_month ? start : `${start}–${formatMonth(gap.end_month)}`;
}
