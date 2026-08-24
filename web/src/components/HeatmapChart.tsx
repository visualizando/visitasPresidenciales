import {max} from "d3-array";
import {scaleLinear} from "d3-scale";
import type {ComparisonSeries, HeatmapPoint, Location} from "../types";
import {PersonLegend} from "./PersonLegend";

const DAYS = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"];

export function HeatmapChart({data, location, series = []}: {data: HeatmapPoint[]; location: Location; series?: ComparisonSeries[]}) {
  const points = data.filter((point) => series.length ? true : point.location === location);
  return (
    <figure className="chart-card" aria-labelledby="heatmap-title">
      <div className="chart-heading"><div><p className="eyebrow">Ritmos</p><h3 id="heatmap-title">Días y horarios</h3></div><span className="chart-context">{series.length ? "Ambas sedes" : location === "casa-rosada" ? "Casa Rosada" : "Olivos"}</span></div>
      <PersonLegend series={series} />
      {points.length ? (
        <div className={`heatmap-comparison${series.length ? " heatmap-comparison--people" : ""}`}>{series.length
          ? series.map((person) => <HeatmapGrid key={person.entityId} points={points.filter((point) => point.entity_id === person.entityId)} color={person.color} label={person.name} />)
          : <HeatmapGrid points={points} color="#075c70" label={location === "casa-rosada" ? "Casa Rosada" : "Olivos"} />}
        </div>
      ) : <p className="chart-empty-copy">Todavía no hay horarios suficientes para este gráfico.</p>}
      <details className="data-table-disclosure"><summary>Ver resumen accesible</summary>{series.length ? series.map((person) => <p key={person.entityId}><strong>{person.name}:</strong> mayor actividad en {peakDescription(points.filter((point) => point.entity_id === person.entityId))}.</p>) : <p>La mayor actividad se registra en {peakDescription(points)}.</p>}</details>
    </figure>
  );
}

function HeatmapGrid({points, color: highColor, label}: {points: HeatmapPoint[]; color: string; label: string}) {
  const totals = new Map<string, number>();
  for (const point of points) totals.set(`${point.weekday}-${point.hour}`, (totals.get(`${point.weekday}-${point.hour}`) ?? 0) + point.records);
  const color = scaleLinear<string>().domain([0, max([...totals.values()]) || 1]).range(["#e6edf0", highColor]);
  return <div className="heatmap-wrap" role="img" aria-label={`Mapa de calor de ${label}`}>
    <strong className="heatmap-person">{label}</strong>
    <div className="heatmap" aria-hidden="true">
      <span />{[0, 4, 8, 12, 16, 20].map((hour) => <span className="heatmap-hour" key={hour}>{hour} h</span>)}
      {DAYS.map((day, weekday) => <div className="heatmap-row" key={day}><span className="heatmap-day">{day}</span>{Array.from({length: 24}, (_, hour) => { const value = totals.get(`${weekday}-${hour}`) ?? 0; return <span key={hour} className="heatmap-cell" style={{backgroundColor: color(value)}} title={`${label} · ${day}, ${hour}:00: ${value.toLocaleString("es-AR")} registros`} />; })}</div>)}
    </div>
    <div className="heatmap-key"><span>Menos</span><i style={{background: `linear-gradient(90deg, #e6edf0, ${highColor})`}} /><span>Más</span></div>
  </div>;
}

function peakDescription(points: HeatmapPoint[]) {
  if (!points.length) return "un período todavía no determinado";
  const peak = [...points].sort((a, b) => b.records - a.records)[0];
  return `${DAYS[peak.weekday]} a las ${peak.hour}:00, con ${peak.records.toLocaleString("es-AR")} registros`;
}
