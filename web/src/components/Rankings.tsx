import {useEffect, useMemo, useState} from "react";
import {useData} from "../hooks/useData";
import type {RankingGrouping, RankingLocation, RankingsData} from "../types";

const LOCATION_LABELS: Record<RankingLocation, string> = {
  all: "Ambas sedes",
  "casa-rosada": "Casa Rosada",
  olivos: "Olivos",
};

export function Rankings({compact = false}: {compact?: boolean}) {
  const rankings = useData<RankingsData>("analytics/rankings.json");
  const [grouping, setGrouping] = useState<RankingGrouping>("presidency");
  const [location, setLocation] = useState<RankingLocation>("all");
  const periods = useMemo(
    () => grouping === "presidency" ? rankings.data?.presidencies ?? [] : [...(rankings.data?.years ?? [])].reverse(),
    [grouping, rankings.data],
  );
  const [periodId, setPeriodId] = useState("");

  useEffect(() => {
    if (!periods.some((period) => period.id === periodId)) setPeriodId(periods[0]?.id ?? "");
  }, [periodId, periods]);

  const activePeriod = periods.find((period) => period.id === periodId) ?? periods[0];
  const rows = useMemo(
    () => rankings.data?.rankings[grouping]?.[activePeriod?.id ?? ""]?.[location] ?? [],
    [activePeriod?.id, grouping, location, rankings.data],
  );

  return <>
    {!compact && <div className="section-heading rankings-heading">
      <div><p className="eyebrow">Rankings</p><h2 id="rankings-title">Quiénes aparecen más días</h2></div>
      <p>Contamos una sola presencia por persona, fecha y sede, aunque tenga varias entradas o salidas ese día. No implica una reunión presidencial.</p>
    </div>}
    <div className="rankings-panel">
      <form className="ranking-filters" onSubmit={(event) => event.preventDefault()}>
        <fieldset>
          <legend>Agrupar por</legend>
          <div className="segmented-control">
            <button type="button" aria-pressed={grouping === "presidency"} onClick={() => setGrouping("presidency")}>Presidencias</button>
            <button type="button" aria-pressed={grouping === "year"} onClick={() => setGrouping("year")}>Años</button>
          </div>
        </fieldset>
        <label>Período<select value={activePeriod?.id ?? ""} onChange={(event) => setPeriodId(event.target.value)}>{periods.map((period) => <option key={period.id} value={period.id}>{period.label}</option>)}</select></label>
        <label>Sede<select value={location} onChange={(event) => setLocation(event.target.value as RankingLocation)}>{Object.entries(LOCATION_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        {activePeriod && <p className="ranking-coverage">Cobertura: <time dateTime={activePeriod.start_date}>{formatDate(activePeriod.start_date)}</time>–<time dateTime={activePeriod.end_date}>{formatDate(activePeriod.end_date)}</time></p>}
      </form>

      {rankings.loading && <p className="ranking-status" role="status">Cargando ranking…</p>}
      {rankings.error && <div className="notice notice--error" role="alert"><strong>No se pudo cargar el ranking.</strong><span>{rankings.error}</span></div>}
      {!rankings.loading && !rankings.error && rows.length > 0 && <div className="ranking-table-wrap">
        <table className="ranking-table">
          <caption className="sr-only">Ranking de presencias diarias para {LOCATION_LABELS[location]} durante {activePeriod?.label}</caption>
          <thead><tr><th scope="col">Puesto</th><th scope="col">Persona</th><th scope="col">Días</th>{location === "all" && <><th scope="col">Casa Rosada</th><th scope="col">Olivos</th></>}<th scope="col">Primera</th><th scope="col">Última</th></tr></thead>
          <tbody>{rows.map((row, index) => <tr key={row.entity_id}>
            <td className="ranking-position">{index + 1}</td>
            <td><strong>{row.canonical_name}</strong>{row.document_number && <small>{row.document_type ?? "Documento"} {row.document_number}</small>}</td>
            <td className="ranking-total">{row.daily_visits.toLocaleString("es-AR")}</td>
            {location === "all" && <><td>{row.casa_rosada.toLocaleString("es-AR")}</td><td>{row.olivos.toLocaleString("es-AR")}</td></>}
            <td><time dateTime={row.first_visit}>{formatShortDate(row.first_visit)}</time></td><td><time dateTime={row.last_visit}>{formatShortDate(row.last_visit)}</time></td>
          </tr>)}</tbody>
        </table>
      </div>}
      {!rankings.loading && !rankings.error && !rows.length && <p className="ranking-status">No hay registros para este período y sede.</p>}
    </div>
  </>;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("es-AR", {day: "numeric", month: "short", year: "numeric", timeZone: "UTC"}).format(new Date(`${value}T00:00:00Z`));
}

function formatShortDate(value: string) {
  return new Intl.DateTimeFormat("es-AR", {day: "2-digit", month: "2-digit", year: "2-digit", timeZone: "UTC"}).format(new Date(`${value}T00:00:00Z`));
}
