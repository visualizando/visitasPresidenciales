import {hierarchy, treemap} from "d3-hierarchy";
import {useId, useMemo} from "react";
import type {ComparisonSeries, Location, PurposePoint} from "../types";
import {PersonLegend} from "./PersonLegend";

const DESKTOP_SIZE = {width: 640, height: 360};
const MOBILE_SIZE = {width: 320, height: 420};

interface TreeDatum {
  label: string;
  location?: Location;
  entityId?: string;
  color?: string;
  records?: number;
  children?: TreeDatum[];
}

export function PurposeChart({data, series = []}: {data: PurposePoint[]; series?: ComparisonSeries[]}) {
  const titleId = useId();
  const points = data.filter((point) => point.records > 0);
  const locations = new Set(points.map((point) => point.location));
  const layouts = useMemo(() => ({
    desktop: createLayout(points, series, DESKTOP_SIZE.width, DESKTOP_SIZE.height),
    mobile: createLayout(points, series, MOBILE_SIZE.width, MOBILE_SIZE.height),
  }), [points, series]);

  return (
    <figure className="chart-card" aria-labelledby={titleId}>
      <div className="chart-heading">
        <h3 id={titleId}>Destinos y motivos</h3>
        {!series.length && points.length > 0 && <div className="legend" aria-label="Sedes">{locations.has("casa-rosada") && <span><i className="legend-dot legend-dot--casa-rosada" />Casa Rosada</span>}{locations.has("olivos") && <span><i className="legend-dot legend-dot--olivos" />Olivos</span>}</div>}
      </div>
      <PersonLegend series={series} />
      {layouts.desktop ? (
        <>
          <div className="treemap-graphic" role="img" aria-label="Treemap de destinos y motivos. El área de cada rectángulo representa la cantidad de registros.">
            <TreemapSvg layout={layouts.desktop} series={series} width={DESKTOP_SIZE.width} height={DESKTOP_SIZE.height} className="treemap-chart--desktop" />
            {layouts.mobile && <TreemapSvg layout={layouts.mobile} series={series} width={MOBILE_SIZE.width} height={MOBILE_SIZE.height} className="treemap-chart--mobile" />}
          </div>
          <details className="data-table-disclosure">
            <summary>Ver datos del gráfico</summary>
            <div className="table-scroll"><table><caption>Destinos y motivos por {series.length ? "persona" : "sede"}</caption><thead><tr><th>Destino o motivo</th>{series.length > 0 && <th>Persona</th>}<th>Sede</th><th>Registros</th></tr></thead><tbody>{points.map((point) => <tr key={`${point.entity_id ?? point.location}-${point.label}`}><td>{point.label}</td>{series.length > 0 && <td>{series.find((item) => item.entityId === point.entity_id)?.name ?? point.person_name}</td>}<td>{locationLabel(point.location)}</td><td>{formatNumber(point.records)}</td></tr>)}</tbody></table></div>
          </details>
        </>
      ) : <p className="chart-empty-copy">Las fuentes procesadas todavía no incluyen destinos o motivos.</p>}
    </figure>
  );
}

function createLayout(points: PurposePoint[], series: ComparisonSeries[], width: number, height: number) {
  if (!points.length) return null;
  const groups: TreeDatum[] = series.length ? series.map((person) => ({
    label: person.name,
    entityId: person.entityId,
    color: person.color,
    children: points.filter((point) => point.entity_id === person.entityId).map((point) => ({...point, entityId: person.entityId})),
  })).filter((group) => group.children?.length) : (["casa-rosada", "olivos"] as Location[]).map((location) => ({
    label: locationLabel(location),
    location,
    children: points.filter((point) => point.location === location).map((point) => ({...point})),
  })).filter((group) => group.children?.length);
  const root = hierarchy<TreeDatum>({label: "Destinos y motivos", children: groups})
    .sum((node) => node.records ?? 0)
    .sort((left, right) => (right.value ?? 0) - (left.value ?? 0));
  return treemap<TreeDatum>()
    .size([width, height])
    .paddingOuter(2)
    .paddingInner(3)
    .paddingTop((node) => node.depth === 1 ? 24 : 2)
    .round(true)(root);
}

function TreemapSvg({layout, series, width, height, className}: {layout: NonNullable<ReturnType<typeof createLayout>>; series: ComparisonSeries[]; width: number; height: number; className: string}) {
  const groups = layout.children ?? [];
  return <svg className={`treemap-chart ${className}`} viewBox={`0 0 ${width} ${height}`} aria-hidden="true" focusable="false">
    {groups.map((group) => <rect key={`background-${group.data.entityId ?? group.data.label}`} className="treemap-group-background" x={group.x0} y={group.y0} width={group.x1 - group.x0} height={group.y1 - group.y0} />)}
    {layout.leaves().map((leaf) => {
      const location = leaf.data.location ?? "casa-rosada";
      const person = series.find((item) => item.entityId === leaf.data.entityId);
      const boxWidth = leaf.x1 - leaf.x0;
      const boxHeight = leaf.y1 - leaf.y0;
      const label = fitLabel(leaf.data.label, boxWidth);
      const showLabel = boxWidth >= 52 && boxHeight >= 32;
      return <g key={`${leaf.data.entityId ?? location}-${leaf.data.label}`} className={`treemap-leaf treemap-leaf--${person ? "person" : location}`} aria-hidden="true">
        <rect x={leaf.x0} y={leaf.y0} width={boxWidth} height={boxHeight} rx="3" style={person ? {fill: person.color} : undefined} />
        <title>{`${leaf.data.label} · ${person?.name ?? locationLabel(location)} · ${formatNumber(leaf.data.records ?? 0)} registros`}</title>
        {showLabel && <text x={leaf.x0 + 7} y={leaf.y0 + 15}><tspan className="treemap-label">{label}</tspan>{boxHeight >= 48 && <tspan className="treemap-value" x={leaf.x0 + 7} dy="1.25em">{formatCompact(leaf.data.records ?? 0)}</tspan>}</text>}
      </g>;
    })}
    {groups.map((group) => <g key={`label-${group.data.entityId ?? group.data.label}`} className="treemap-group" aria-hidden="true"><rect x={group.x0} y={group.y0} width={group.x1 - group.x0} height={group.y1 - group.y0} /><text x={group.x0 + 8} y={group.y0 + 16}>{group.data.label}</text></g>)}
  </svg>;
}

function fitLabel(label: string, width: number) {
  const limit = Math.max(5, Math.floor((width - 14) / 6.2));
  return label.length <= limit ? label : `${label.slice(0, Math.max(1, limit - 1)).trim()}…`;
}

function formatCompact(value: number) { return Intl.NumberFormat("es-AR", {notation: "compact", maximumFractionDigits: 1}).format(value); }
function formatNumber(value: number) { return Intl.NumberFormat("es-AR").format(value); }
function locationLabel(value: Location) { return value === "casa-rosada" ? "Casa Rosada" : "Olivos"; }
