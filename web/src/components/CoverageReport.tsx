import {useData} from "../hooks/useData";
import type {CoverageData, CoverageGap, Location} from "../types";

const LOCATION_LABELS: Record<Location, string> = {"casa-rosada": "Casa Rosada", olivos: "Olivos"};

export function CoverageReport({compact = false}: {compact?: boolean}) {
  const coverage = useData<CoverageData>("analytics/coverage.json");
  const data = coverage.data;
  return <>
    {!compact && <div className="section-heading coverage-heading section-heading--stacked">
      <div><p className="eyebrow">Cobertura</p><h3 id="coverage-title">Qué falta y por qué</h3></div>
      <p>La cobertura puede variar por sede y por fecha. Un mes con registros puede tener días sin datos, y un mes sin registros no permite saber si hubo accesos.</p>
    </div>}
    <div className="coverage-panel">
      {coverage.loading && <p className="coverage-status" role="status">Cargando informe de cobertura…</p>}
      {coverage.error && <div className="notice notice--error" role="alert"><strong>No se pudo cargar el informe de cobertura.</strong><span>{coverage.error}</span></div>}
      {data && !coverage.loading && !coverage.error && <>
        {data.first_date && data.last_date && <p className="coverage-note">
          <strong>Fechas de los registros publicados.</strong> Del {formatDate(data.first_date)} al {formatDate(data.last_date)}, considerando ambas sedes. Fuera de ese rango todavía no hay registros publicados.
        </p>}
        <p className="coverage-note"><strong>Qué se sumó en noviembre de 2026.</strong> La revisión de las carpetas de Poder Ciudadano incorporó 22.537 registros de Olivos de 2020 y 2021. Los archivos de Casa Rosada revisados en esa ocasión ya estaban incorporados. Las dos carpetas se revisan cada mes.</p>
        {data.drive_issues && <div className="coverage-note">
          <strong>Archivos pendientes en Drive</strong>
          <div>Se detectaron {data.drive_issues.empty_files.toLocaleString("es-AR")} archivos vacíos y {data.drive_issues.other_files.toLocaleString("es-AR")} con otros problemas de incorporación. Algunos también pueden figurar en el inventario histórico de abajo.</div>
        </div>}
        <div className="coverage-summary" aria-label="Resumen del inventario histórico">
          <span><strong>{data.summary.active_files.toLocaleString("es-AR")}</strong> archivos incorporados</span>
          <span><strong>{data.summary.quarantined_files}</strong> con problemas de lectura o formato</span>
          <span><strong>{data.summary.missing_files}</strong> ya no visibles en origen</span>
          <span><strong>{data.summary.zero_record_files}</strong> sin registros utilizables</span>
        </div>
        <div className="coverage-locations">
          {data.locations.map((location) => <details key={location.location} open={location.gaps.length > 0}>
            <summary><span>{LOCATION_LABELS[location.location]}</span><small>{location.months_with_data} meses con datos · {location.gaps.length} período{location.gaps.length === 1 ? "" : "s"} sin registros</small></summary>
            {location.gaps.length ? <ul>{location.gaps.map((gap) => <li key={`${gap.start_month}-${gap.end_month}`}><strong>{formatPeriod(gap)}</strong><span>{gap.reason}</span></li>)}</ul> : <p className="coverage-clear">Hay al menos un registro por mes en el rango mostrado.</p>}
          </details>)}
        </div>
        {data.file_issues.length > 0 ? <details className="coverage-files">
          <summary>Archivos sin registros o con problemas ({data.file_issues.length})</summary>
          <ul>{data.file_issues.map((file) => <li key={file.path}><strong>{formatMonth(`${file.year}-${String(file.month).padStart(2, "0")}`)} · {LOCATION_LABELS[file.location]}</strong><span>{file.reason}</span><small>{file.path}</small></li>)}</ul>
        </details> : <p className="coverage-clear">El inventario histórico no indica archivos con problemas de incorporación.</p>}
      </>}
    </div>
  </>;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("es-AR", {day: "numeric", month: "long", year: "numeric", timeZone: "UTC"}).format(new Date(`${value}T00:00:00Z`));
}

function formatMonth(value: string) {
  return new Intl.DateTimeFormat("es-AR", {month: "short", year: "numeric", timeZone: "UTC"}).format(new Date(`${value}-01T00:00:00Z`));
}

function formatPeriod(gap: CoverageGap) {
  const start = formatMonth(gap.start_month);
  return gap.start_month === gap.end_month ? start : `${start}–${formatMonth(gap.end_month)}`;
}
