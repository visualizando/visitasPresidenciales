import {max} from "d3-array";
import {scaleLinear} from "d3-scale";
import type {HeatmapPoint, Location} from "../types";

const DAYS = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"];

export function HeatmapChart({data, location}: {data: HeatmapPoint[]; location: Location}) {
  const points = data.filter((point) => point.location === location);
  const color = scaleLinear<string>().domain([0, max(points, (point) => point.records) || 1]).range(["#e6edf0", "#075c70"]);
  const lookup = new Map(points.map((point) => [`${point.weekday}-${point.hour}`, point.records]));
  return (
    <figure className="chart-card" aria-labelledby="heatmap-title">
      <div className="chart-heading"><div><p className="eyebrow">Ritmos</p><h3 id="heatmap-title">Días y horarios</h3></div><span className="chart-context">{location === "casa-rosada" ? "Casa Rosada" : "Olivos"}</span></div>
      {points.length ? (
        <div className="heatmap-wrap" role="img" aria-label={`Mapa de calor de registros por día y hora en ${location === "casa-rosada" ? "Casa Rosada" : "Olivos"}`}>
          <div className="heatmap" aria-hidden="true">
            <span />{[0, 4, 8, 12, 16, 20].map((hour) => <span className="heatmap-hour" key={hour}>{hour} h</span>)}
            {DAYS.map((day, weekday) => <div className="heatmap-row" key={day}><span className="heatmap-day">{day}</span>{Array.from({length: 24}, (_, hour) => { const value = lookup.get(`${weekday}-${hour}`) ?? 0; return <span key={hour} className="heatmap-cell" style={{backgroundColor: color(value)}} title={`${day}, ${hour}:00: ${value.toLocaleString("es-AR")} registros`} />; })}</div>)}
          </div>
          <div className="heatmap-key"><span>Menos</span><i /><span>Más</span></div>
        </div>
      ) : <p className="chart-empty-copy">Todavía no hay horarios suficientes para este gráfico.</p>}
      <details className="data-table-disclosure"><summary>Ver resumen accesible</summary><p>La mayor actividad se registra en {peakDescription(points)}.</p></details>
    </figure>
  );
}

function peakDescription(points: HeatmapPoint[]) {
  if (!points.length) return "un período todavía no determinado";
  const peak = [...points].sort((a, b) => b.records - a.records)[0];
  return `${DAYS[peak.weekday]} a las ${peak.hour}:00, con ${peak.records.toLocaleString("es-AR")} registros`;
}

