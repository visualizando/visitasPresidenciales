import type {ComparisonSeries} from "../types";

export function PersonLegend({series}: {series: ComparisonSeries[]}) {
  if (!series.length) return null;
  return <div className="person-legend" aria-label="Personas comparadas">{series.map((person) => <span key={person.entityId}><i style={{backgroundColor: person.color}} aria-hidden="true" />{person.name}</span>)}</div>;
}
