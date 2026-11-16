import {useData} from "../hooks/useData";
import type {CoverageData, CoverageGap, Location} from "../types";

const LOCATION_LABELS: Record<Location, string> = {"casa-rosada": "Casa Rosada", olivos: "Quinta de Olivos"};

export function CoverageReport({compact = false}: {compact?: boolean}) {
  const coverage = useData<CoverageData>("analytics/coverage.json");
  const data = coverage.data;
  return <>
    {!compact && <div className="section-heading coverage-heading section-heading--stacked">
      <div><p className="eyebrow">Cobertura</p><h3 id="coverage-title">Qué falta y por qué</h3></div>
      <p>Faltan datos de algunos períodos porque no recibimos respuesta a los pedidos de acceso a la información o porque los archivos que recibimos no se pudieron reutilizar.</p>
    </div>}
    <div className="coverage-panel">
      {coverage.loading && <p className="coverage-status" role="status">Cargando informe de cobertura…</p>}
      {coverage.error && <p className="notice notice--error" role="alert">No se pudo cargar el informe de cobertura.</p>}
      {data && !coverage.loading && !coverage.error && <>
        <p className="coverage-note">Estos son los períodos sin registros publicados por sede. En otros meses también puede haber días sin datos.</p>
        <div className="coverage-locations">
          {data.locations.map((location) => <details key={location.location} open={location.gaps.length > 0}>
            <summary>{LOCATION_LABELS[location.location]}</summary>
            {location.gaps.length > 0
              ? <ul>{location.gaps.map((gap) => <li key={gap.start_month}><strong>{formatPeriod(gap)}</strong></li>)}</ul>
              : <p className="coverage-clear">Hay registros publicados en todos los meses del período cubierto.</p>}
          </details>)}
        </div>
      </>}
    </div>
  </>;
}

function formatMonth(value: string) {
  return new Intl.DateTimeFormat("es-AR", {month: "long", year: "numeric", timeZone: "UTC"}).format(new Date(`${value}-01T00:00:00Z`));
}

function formatPeriod(gap: CoverageGap) {
  const start = formatMonth(gap.start_month);
  return gap.start_month === gap.end_month ? start : `${start} a ${formatMonth(gap.end_month)}`;
}
