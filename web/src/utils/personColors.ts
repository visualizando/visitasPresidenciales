import type {ComparisonSeries, PersonSummary} from "../types";

// Paul Tol's bright qualitative palette, adjusted with a darker yellow for light surfaces.
export const PERSON_COLORS = ["#0077bb", "#d55e00", "#009988", "#cc3311", "#aa4499", "#0072b2", "#b38f00", "#ee3377"];

export function comparisonSeries(people: PersonSummary[]): ComparisonSeries[] {
  const used = new Set<number>();
  return people.map((person) => {
    let index = hash(person.entity_id) % PERSON_COLORS.length;
    while (used.has(index) && used.size < PERSON_COLORS.length) index = (index + 1) % PERSON_COLORS.length;
    used.add(index);
    return {entityId: person.entity_id, name: titleCase(person.canonical_name), color: PERSON_COLORS[index]};
  });
}

export function seriesColor(series: ComparisonSeries[], entityId?: string) {
  return series.find((item) => item.entityId === entityId)?.color ?? PERSON_COLORS[0];
}

function hash(value: string) {
  let result = 0;
  for (let index = 0; index < value.length; index += 1) result = (result * 31 + value.charCodeAt(index)) >>> 0;
  return result;
}

function titleCase(value: string) {
  return value.toLocaleLowerCase("es-AR").replace(/(^|[\s'-])\p{L}/gu, (letter) => letter.toLocaleUpperCase("es-AR"));
}
