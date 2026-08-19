import type {PurposePoint} from "../types";

export function PurposeChart({data}: {data: PurposePoint[]}) {
  const points = data.slice(0, 7);
  const maximum = Math.max(...points.map((point) => point.records), 1);
  return (
    <figure className="chart-card" aria-labelledby="purpose-title">
      <div className="chart-heading"><div><p className="eyebrow">Contexto</p><h3 id="purpose-title">Destinos y motivos</h3></div></div>
      {points.length ? <ol className="bar-list">{points.map((point) => <li key={`${point.location}-${point.label}`}><div className="bar-label"><span>{point.label}</span><strong>{point.records.toLocaleString("es-AR")}</strong></div><div className="bar-track" aria-hidden="true"><span style={{width: `${(point.records / maximum) * 100}%`}} /></div><small>{point.location === "casa-rosada" ? "Casa Rosada" : "Olivos"}</small></li>)}</ol> : <p className="chart-empty-copy">Las fuentes procesadas todavía no incluyen destinos o motivos.</p>}
    </figure>
  );
}

