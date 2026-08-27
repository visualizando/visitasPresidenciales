import {hierarchy, pack} from "d3-hierarchy";
import {useId, useMemo} from "react";
import type {ComparisonSeries, Location, PurposePoint} from "../types";
import {PersonLegend} from "./PersonLegend";

const WIDTH = 640;
const HEIGHT = 480;

interface PackDatum {
  label: string;
  location?: Location;
  entityId?: string;
  color?: string;
  records?: number;
  children?: PackDatum[];
}

export function PurposeChart({data, series = []}: {data: PurposePoint[]; series?: ComparisonSeries[]}) {
  const titleId = useId();
  const points = data.filter((point) => point.records > 0);
  const locations = new Set(points.map((point) => point.location));
  const layout = useMemo(() => createLayout(points, series), [points, series]);

  return (
    <figure className="chart-card" aria-labelledby={titleId}>
      <div className="chart-heading">
        <h3 id={titleId}>Destinos y motivos</h3>
        {!series.length && points.length > 0 && <div className="legend" aria-label="Sedes">{locations.has("casa-rosada") && <span><i className="legend-dot legend-dot--casa-rosada" />Casa Rosada</span>}{locations.has("olivos") && <span><i className="legend-dot legend-dot--olivos" />Olivos</span>}</div>}
      </div>
      <PersonLegend series={series} />
      {layout ? (
        <>
          <svg className="pack-chart" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Circle pack de destinos y motivos. El área de cada círculo representa la cantidad de registros." focusable="false">
            {layout.children?.map((group) => <g key={group.data.entityId ?? group.data.label} className={`pack-group pack-group--${group.data.location ?? "person"}`} aria-hidden="true"><circle cx={group.x} cy={group.y} r={group.r} style={group.data.color ? {stroke: group.data.color} : undefined} /><text x={group.x} y={group.y - group.r + 14}>{group.data.label}</text></g>)}
            {layout.leaves().map((leaf) => {
              const location = leaf.data.location ?? "casa-rosada";
              const lines = leaf.r >= 25 ? splitLabel(leaf.data.label, leaf.r) : [];
              const person = series.find((item) => item.entityId === leaf.data.entityId);
              return <g key={`${leaf.data.entityId ?? location}-${leaf.data.label}`} className={`pack-leaf pack-leaf--${person ? "person" : location}`} transform={`translate(${leaf.x} ${leaf.y})`} aria-hidden="true">
                <circle r={leaf.r} style={person ? {fill: person.color} : undefined} />
                <title>{`${leaf.data.label} · ${person?.name ?? locationLabel(location)} · ${formatNumber(leaf.data.records ?? 0)} registros`}</title>
                {lines.length > 0 && <text className="pack-label">{lines.map((line, index) => <tspan key={line} x="0" y={`${index - (lines.length - 1) / 2 - 0.35}em`}>{line}</tspan>)}<tspan className="pack-value" x="0" y={`${(lines.length - 1) / 2 + 1}em`}>{formatCompact(leaf.data.records ?? 0)}</tspan></text>}
              </g>;
            })}
          </svg>
          <details className="data-table-disclosure">
            <summary>Ver datos del gráfico</summary>
            <div className="table-scroll"><table><caption>Destinos y motivos por {series.length ? "persona" : "sede"}</caption><thead><tr><th>Destino o motivo</th>{series.length > 0 && <th>Persona</th>}<th>Sede</th><th>Registros</th></tr></thead><tbody>{points.map((point) => <tr key={`${point.entity_id ?? point.location}-${point.label}`}><td>{point.label}</td>{series.length > 0 && <td>{series.find((item) => item.entityId === point.entity_id)?.name ?? point.person_name}</td>}<td>{locationLabel(point.location)}</td><td>{formatNumber(point.records)}</td></tr>)}</tbody></table></div>
          </details>
        </>
      ) : <p className="chart-empty-copy">Las fuentes procesadas todavía no incluyen destinos o motivos.</p>}
    </figure>
  );
}

function createLayout(points: PurposePoint[], series: ComparisonSeries[]) {
  if (!points.length) return null;
  const groups: PackDatum[] = series.length ? series.map((person) => ({
    label: person.name,
    entityId: person.entityId,
    color: person.color,
    children: points.filter((point) => point.entity_id === person.entityId).map((point) => ({...point, entityId: person.entityId})),
  })).filter((group) => group.children?.length) : (["casa-rosada", "olivos"] as Location[]).map((location) => ({
    label: locationLabel(location),
    location,
    children: points.filter((point) => point.location === location).map((point) => ({...point})),
  })).filter((group) => group.children?.length);
  const root = hierarchy<PackDatum>({label: "Destinos y motivos", children: groups})
    .sum((node) => node.records ?? 0)
    .sort((left, right) => (right.value ?? 0) - (left.value ?? 0));
  return pack<PackDatum>().size([WIDTH, HEIGHT]).padding(4)(root);
}

function splitLabel(label: string, radius: number) {
  const characterLimit = Math.max(7, Math.min(18, Math.floor((radius * 2 - 12) / 6)));
  const words = label.split(/\s+/);
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length <= characterLimit && lines.length < 2) current = candidate;
    else if (lines.length === 0) { lines.push(current || `${word.slice(0, characterLimit - 1)}…`); current = current ? word : ""; }
    else break;
  }
  if (current && lines.length < 2) lines.push(current);
  const shown = lines.join(" ");
  if (shown.length < label.length && lines.length) lines[lines.length - 1] = `${lines[lines.length - 1].replace(/…$/, "").slice(0, Math.max(1, characterLimit - 1))}…`;
  return lines;
}

function formatCompact(value: number) { return Intl.NumberFormat("es-AR", {notation: "compact", maximumFractionDigits: 1}).format(value); }
function formatNumber(value: number) { return Intl.NumberFormat("es-AR").format(value); }
function locationLabel(value: Location) { return value === "casa-rosada" ? "Casa Rosada" : "Olivos"; }
