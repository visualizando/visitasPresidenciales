import {max} from "d3-array";
import {scaleSqrt} from "d3-scale";
import {useId, useMemo} from "react";
import type {DailyPoint, Location} from "../types";

const DAY_MS = 86_400_000;
const WEEKDAYS = ["L", "M", "X", "J", "V", "S", "D"];
const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

// Adapted from Observable's Calendar component (ISC):
// https://observablehq.com/@observablehq/calendar-component

interface CalendarDay {
  date: Date;
  key: string;
  records: number;
  inPeriod: boolean;
}

interface CalendarPeriod {
  key: string;
  label: string;
  weeks: number;
  months: {label: string; column: number}[];
  days: CalendarDay[];
}

export function CalendarChart({data, location}: {data: DailyPoint[]; location: Location}) {
  const titleId = useId();
  const points = useMemo(() => aggregateDays(data, location), [data, location]);
  const periods = useMemo(() => createPeriods(points), [points]);
  const maximum = max([...points.values()]) ?? 1;
  const color = scaleSqrt<string>().domain([0, maximum]).range(["#e9ede8", "#075c70"]);
  const peak = [...points.entries()].sort((left, right) => right[1] - left[1])[0];

  return (
    <figure className="chart-card" aria-labelledby={titleId}>
      <div className="chart-heading"><div><p className="eyebrow">Calendario</p><h3 id={titleId}>Actividad por día</h3></div><span className="chart-context">{locationLabel(location)}</span></div>
      {periods.length ? <>
        <div className="calendar-scroll" tabIndex={0} aria-label="Calendario anual desplazable horizontalmente">
          <div className="calendar-periods" role="img" aria-label={calendarDescription(points.size, peak, location)}>
            {periods.map((period) => <section className="calendar-period" key={period.key} aria-hidden="true">
              <h4>{period.label}</h4>
              <div className="calendar-months" style={{gridTemplateColumns: `repeat(${period.weeks}, minmax(0, 1fr))`}}>{period.months.map((month) => <span key={`${period.key}-${month.label}`} style={{gridColumnStart: month.column}}>{month.label}</span>)}</div>
              <div className="calendar-body">
                <div className="calendar-weekdays">{WEEKDAYS.map((day) => <span key={day}>{day}</span>)}</div>
                <div className="calendar-days" style={{gridTemplateColumns: `repeat(${period.weeks}, minmax(0, 1fr))`}}>{period.days.map((day, index) => <span key={day.key} className={`calendar-day${day.inPeriod ? "" : " calendar-day--outside"}`} style={day.inPeriod ? {backgroundColor: color(day.records), gridColumn: Math.floor(index / 7) + 1, gridRow: index % 7 + 1} : {gridColumn: Math.floor(index / 7) + 1, gridRow: index % 7 + 1}} title={day.inPeriod ? `${formatDate(day.date)}: ${formatNumber(day.records)} registros` : undefined} />)}</div>
              </div>
            </section>)}
          </div>
        </div>
        <div className="calendar-key" aria-hidden="true"><span>Menos</span><i /><span>Más</span></div>
        <details className="data-table-disclosure"><summary>Ver resumen accesible</summary><p>{calendarDescription(points.size, peak, location)}</p></details>
      </> : <p className="chart-empty-copy">Todavía no hay fechas suficientes para este calendario.</p>}
    </figure>
  );
}

function aggregateDays(data: DailyPoint[], location: Location) {
  const result = new Map<string, number>();
  for (const point of data) if (point.location === location) result.set(point.date, (result.get(point.date) ?? 0) + point.records);
  return result;
}

function createPeriods(points: Map<string, number>) {
  if (!points.size) return [];
  const keys = [...points.keys()].sort();
  const first = parseDate(keys[0]);
  const last = parseDate(keys[keys.length - 1]);
  const periods: CalendarPeriod[] = [];
  for (let year = first.getUTCFullYear(); year <= last.getUTCFullYear(); year += 1) {
    const start = new Date(Date.UTC(year, 0, 1));
    const end = new Date(Date.UTC(year + 1, 0, 1));
    const gridStart = addDays(start, -((start.getUTCDay() + 6) % 7));
    const weeks = Math.ceil((end.valueOf() - gridStart.valueOf()) / DAY_MS / 7);
    const days = Array.from({length: weeks * 7}, (_, index) => {
      const date = addDays(gridStart, index);
      const key = date.toISOString().slice(0, 10);
      return {date, key, records: points.get(key) ?? 0, inPeriod: date >= start && date < end};
    });
    const months = Array.from({length: 12}, (_, month) => {
      const date = new Date(Date.UTC(year, month, 1));
      return {label: MONTHS[month], column: Math.floor((date.valueOf() - gridStart.valueOf()) / DAY_MS / 7) + 1};
    });
    periods.push({key: `${year}`, label: `${year}`, weeks, months, days});
  }
  return periods;
}

function parseDate(value: string) { return new Date(`${value}T00:00:00Z`); }
function addDays(date: Date, amount: number) { return new Date(date.valueOf() + amount * DAY_MS); }
function formatNumber(value: number) { return Intl.NumberFormat("es-AR").format(value); }
function formatDate(date: Date) { return new Intl.DateTimeFormat("es-AR", {day: "numeric", month: "short", year: "numeric", timeZone: "UTC"}).format(date); }
function locationLabel(value: Location) { return value === "casa-rosada" ? "Casa Rosada" : "Olivos"; }
function calendarDescription(activeDays: number, peak: [string, number] | undefined, location: Location) {
  if (!peak) return `No hay actividad diaria disponible para ${locationLabel(location)}.`;
  return `${formatNumber(activeDays)} ${activeDays === 1 ? "día" : "días"} con actividad en ${locationLabel(location)}. El máximo fue el ${formatDate(parseDate(peak[0]))}, con ${formatNumber(peak[1])} registros.`;
}
