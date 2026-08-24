import {extent, max} from "d3-array";
import {scaleLinear, scaleUtc} from "d3-scale";
import {line} from "d3-shape";
import type {ComparisonSeries, MonthlyPoint} from "../types";
import {PersonLegend} from "./PersonLegend";

const WIDTH = 760;
const HEIGHT = 270;
const MARGIN = {top: 18, right: 18, bottom: 44, left: 58};

export function TrendChart({data, series = []}: {data: MonthlyPoint[]; series?: ComparisonSeries[]}) {
  const chartData = series.length ? aggregatePeople(data) : data;
  const parsed = chartData.map((point) => ({...point, date: new Date(`${point.month}-01T00:00:00Z`)}));
  if (!parsed.length) return <ChartEmpty text="Todavía no hay datos temporales para graficar." />;
  const domain = extent(parsed, (point) => point.date) as [Date, Date];
  if (+domain[0] === +domain[1]) domain[1] = new Date(Date.UTC(domain[1].getUTCFullYear(), domain[1].getUTCMonth() + 1, 1));
  const x = scaleUtc().domain(domain).range([MARGIN.left, WIDTH - MARGIN.right]);
  const y = scaleLinear().domain([0, max(parsed, (point) => point.records) ?? 1]).nice().range([HEIGHT - MARGIN.bottom, MARGIN.top]);
  const paths = series.length ? series.map((person, index) => ({
    key: person.entityId,
    color: person.color,
    dash: [undefined, "8 4", "2 3", "12 4 2 4"][index % 4],
    className: "trend-line",
    path: line<(typeof parsed)[number]>().x((point) => x(point.date)).y((point) => y(point.records))(parsed.filter((point) => point.entity_id === person.entityId)) ?? "",
  })) : (["casa-rosada", "olivos"] as const).map((location) => ({
    key: location,
    color: undefined,
    dash: undefined,
    className: `trend-line trend-line--${location}`,
    path: line<(typeof parsed)[number]>().x((point) => x(point.date)).y((point) => y(point.records))(parsed.filter((point) => point.location === location)) ?? "",
  }));
  const yTicks = y.ticks(4);
  const xTicks = x.ticks(Math.min(6, parsed.length));

  return (
    <figure className="chart-card" aria-labelledby="trend-title">
      <div className="chart-heading">
        <div>
          <p className="eyebrow">Evolución</p>
          <h3 id="trend-title">Movimientos por mes</h3>
        </div>
        {!series.length && <div className="legend" aria-label="Series">
          <span><i className="legend-line legend-line--solid" />Casa Rosada</span>
          <span><i className="legend-line legend-line--dashed" />Olivos</span>
        </div>}
      </div>
      <PersonLegend series={series} />
      <div className="chart-scroll" tabIndex={0} aria-label="Gráfico desplazable horizontalmente">
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-labelledby="trend-svg-title trend-svg-desc">
          <title id="trend-svg-title">Movimientos mensuales por {series.length ? "persona" : "sede"}</title>
          <desc id="trend-svg-desc">{series.length ? `${series.length} líneas comparan la cantidad mensual de registros de las personas seleccionadas.` : "Dos líneas comparan la cantidad mensual de registros de Casa Rosada y Olivos."}</desc>
          {yTicks.map((tick) => <g key={tick}><line className="grid-line" x1={MARGIN.left} x2={WIDTH - MARGIN.right} y1={y(tick)} y2={y(tick)} /><text className="axis-label" x={MARGIN.left - 10} y={y(tick) + 4} textAnchor="end">{formatCompact(tick)}</text></g>)}
          {xTicks.map((tick) => <text className="axis-label" key={tick.toISOString()} x={x(tick)} y={HEIGHT - 16} textAnchor="middle">{tick.toLocaleDateString("es-AR", {month: "short", year: "2-digit", timeZone: "UTC"})}</text>)}
          {paths.map(({key, path, className, color, dash}) => <path key={key} d={path} className={className} style={color ? {stroke: color, strokeDasharray: dash} : undefined} />)}
        </svg>
      </div>
      <details className="data-table-disclosure">
        <summary>Ver datos del gráfico</summary>
        <div className="table-scroll"><table><caption>Movimientos mensuales por {series.length ? "persona" : "sede"}</caption><thead><tr><th>Mes</th>{series.length > 0 && <th>Persona</th>}<th>Sede</th><th>Registros</th><th>Personas</th></tr></thead><tbody>{chartData.map((point) => <tr key={`${point.month}-${point.entity_id ?? point.location}`}><td>{point.month}</td>{series.length > 0 && <td>{series.find((item) => item.entityId === point.entity_id)?.name ?? point.person_name}</td>}<td>{series.length ? "Ambas" : locationLabel(point.location)}</td><td>{formatNumber(point.records)}</td><td>{formatNumber(point.people)}</td></tr>)}</tbody></table></div>
      </details>
    </figure>
  );
}

function ChartEmpty({text}: {text: string}) { return <div className="chart-card chart-empty"><p>{text}</p></div>; }
function formatCompact(value: number) { return Intl.NumberFormat("es-AR", {notation: "compact", maximumFractionDigits: 1}).format(value); }
function formatNumber(value: number) { return Intl.NumberFormat("es-AR").format(value); }
function locationLabel(value: string) { return value === "casa-rosada" ? "Casa Rosada" : "Olivos"; }

function aggregatePeople(data: MonthlyPoint[]) {
  const result = new Map<string, MonthlyPoint>();
  for (const point of data) {
    const key = `${point.month}|${point.entity_id}`;
    const current = result.get(key) ?? {...point, records: 0, people: 1};
    current.records += point.records;
    result.set(key, current);
  }
  return [...result.values()].sort((left, right) => left.month.localeCompare(right.month));
}
