import {max} from "d3-array";
import {scaleSqrt} from "d3-scale";
import {useId, useMemo, useState} from "react";
import type {ComparisonSeries, DailyPoint, Location} from "../types";
import {PersonLegend} from "./PersonLegend";

const DAY_MS = 86_400_000;
const MONTH_GAP_PX = 3;
const WEEKDAYS = ["L", "M", "X", "J", "V", "S", "D"];
const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

// Adapted from Observable's Calendar component (ISC):
// https://observablehq.com/@observablehq/calendar-component

interface CalendarDay {
  date: Date;
  key: string;
  records: number;
  people: {entityId: string; records: number}[];
  inPeriod: boolean;
}

interface CalendarPeriod {
  key: string;
  label: string;
  weeks: number;
  months: {key: string; label: string; column: number}[];
  days: CalendarDay[];
}

type CalendarLocation = Location | "all";

export function CalendarChart({data, location, series = [], mileiCasaRosadaDays = []}: {data: DailyPoint[]; location: CalendarLocation; series?: ComparisonSeries[]; mileiCasaRosadaDays?: string[]}) {
  const titleId = useId();
  const tooltipId = useId();
  const [tooltip, setTooltip] = useState<{day: CalendarDay; mileiPresent: boolean; x: number; y: number} | null>(null);
  const [showMilei, setShowMilei] = useState(true);
  const points = useMemo(() => aggregateDays(data, location), [data, location]);
  const periods = useMemo(() => createPeriods(points), [points]);
  const mileiDays = useMemo(() => new Set(mileiCasaRosadaDays), [mileiCasaRosadaDays]);
  const maximum = max([...points.values()], (point) => point.records) ?? 1;
  const color = scaleSqrt<string>().domain([0, maximum]).range(["#e9ede8", "#075c70"]);
  const peak = [...points.entries()].sort((left, right) => right[1].records - left[1].records)[0];
  const sharedDays = [...points.values()].filter((point) => point.people.size > 1).length;

  return (
    <figure className="chart-card" aria-labelledby={titleId}>
      <div className="chart-heading"><h3 id={titleId}>Actividad por día</h3><span className="chart-context">{locationLabel(location)}</span></div>
      <PersonLegend series={series} />
      <label className="calendar-overlay-toggle"><input type="checkbox" checked={showMilei} onChange={(event) => setShowMilei(event.currentTarget.checked)} /><span className="calendar-milei-key" aria-hidden="true" />Actividad de Javier Milei en Casa Rosada</label>
      {series.length > 1 && <p className="comparison-summary"><span className="calendar-shared-key" aria-hidden="true" /><strong>{formatNumber(sharedDays)}</strong> {sharedDays === 1 ? "día compartido" : "días compartidos"}</p>}
      {periods.length ? <>
        <div className="calendar-scroll" tabIndex={0} aria-label="Calendario anual desplazable horizontalmente" onScroll={() => setTooltip(null)}>
          <div className="calendar-periods" role={series.length ? "group" : "img"} aria-label={calendarDescription(points.size, peak, location, sharedDays)}>
            {periods.map((period) => <section className="calendar-period" key={period.key} aria-hidden={series.length ? undefined : "true"}>
              <h4>{period.label}</h4>
              <div className="calendar-months" style={{gridTemplateColumns: `repeat(${period.weeks}, minmax(0, 1fr))`}}>{period.months.map((month, monthIndex) => <span key={month.key} data-month={month.key} style={{gridColumnStart: month.column, transform: `translateX(${monthIndex * MONTH_GAP_PX}px)`}}>{month.label}</span>)}</div>
              <div className="calendar-body">
                <div className="calendar-weekdays">{WEEKDAYS.map((day) => <span key={day}>{day}</span>)}</div>
                <div className="calendar-days" style={{gridTemplateColumns: `repeat(${period.weeks}, minmax(0, 1fr))`}}>{period.days.map((day, index) => {
                  const mileiPresent = showMilei && mileiDays.has(day.key);
                  const colors = personColors(day, series);
                  const canFocus = day.inPeriod && day.records > 0 && series.length > 0;
                  const position = {gridColumn: Math.floor(index / 7) + 1, gridRow: index % 7 + 1, transform: `translateX(${day.date.getUTCMonth() * MONTH_GAP_PX}px)`};
                  const showTooltip = (target: HTMLElement) => {
                    const bounds = target.getBoundingClientRect();
                    const center = bounds.left + bounds.width / 2;
                    setTooltip({day, mileiPresent, x: Math.min(Math.max(center, 112), window.innerWidth - 112), y: bounds.top});
                  };
                  return <span key={day.key} data-date={day.key} className={`calendar-day${day.inPeriod ? "" : " calendar-day--outside"}${day.records ? " calendar-day--active" : " calendar-day--empty"}${colors.length > 1 ? " calendar-day--shared" : ""}${mileiPresent ? " calendar-day--milei" : ""}`} style={day.inPeriod ? {...dayColor(day, colors, color), ...position} : position} tabIndex={canFocus ? 0 : undefined} aria-label={canFocus ? dayTitle(day, series, mileiPresent) : undefined} aria-describedby={canFocus && tooltip?.day.key === day.key ? tooltipId : undefined} onPointerEnter={(browserEvent) => day.inPeriod && showTooltip(browserEvent.currentTarget)} onPointerLeave={() => setTooltip(null)} onFocus={(browserEvent) => canFocus && showTooltip(browserEvent.currentTarget)} onBlur={() => setTooltip(null)}>
                    {colors.length > 1 && colors.map((item, colorIndex) => <i className="calendar-day-segment" style={{backgroundColor: item}} key={`${day.key}-${colorIndex}`} />)}
                    {day.inPeriod && <b className="calendar-day-number" aria-hidden="true">{day.date.getUTCDate()}</b>}
                  </span>;
                })}</div>
              </div>
            </section>)}
          </div>
        </div>
        {!series.length && <div className="calendar-key" aria-hidden="true"><span>Menos</span><i /><span>Más</span></div>}
        <details className="data-table-disclosure"><summary>Ver resumen accesible</summary><p>{calendarDescription(points.size, peak, location, sharedDays)}</p></details>
        {tooltip && <CalendarTooltip id={tooltipId} day={tooltip.day} series={series} mileiPresent={tooltip.mileiPresent} x={tooltip.x} y={tooltip.y} />}
      </> : <p className="chart-empty-copy">Todavía no hay fechas suficientes para este calendario.</p>}
    </figure>
  );
}

function CalendarTooltip({id, day, series, mileiPresent, x, y}: {id: string; day: CalendarDay; series: ComparisonSeries[]; mileiPresent: boolean; x: number; y: number}) {
  const records = new Map(day.people.map((person) => [person.entityId, person.records]));
  const people = series.length ? series.map((person) => ({...person, records: records.get(person.entityId) ?? 0})) : [];
  return <div id={id} className="calendar-tooltip" role="tooltip" style={{left: x, top: y}}>
    <strong>{formatDate(day.date)}</strong>
    <span className="calendar-tooltip-total">{formatNumber(day.records)} {day.records === 1 ? "registro" : "registros"} en total</span>
    {people.length > 0 && <ul>{people.map((person) => <li key={person.entityId}><i style={{backgroundColor: person.color}} aria-hidden="true" /><span>{person.name}</span><b>{formatNumber(person.records)}</b></li>)}</ul>}
    {mileiPresent && <small>Javier Milei registra actividad en Casa Rosada</small>}
  </div>;
}

function aggregateDays(data: DailyPoint[], location: CalendarLocation) {
  const result = new Map<string, {records: number; people: Map<string, number>}>();
  for (const point of data) if (location === "all" || point.location === location) {
    const day = result.get(point.date) ?? {records: 0, people: new Map<string, number>()};
    day.records += point.records;
    if (point.entity_id) day.people.set(point.entity_id, (day.people.get(point.entity_id) ?? 0) + point.records);
    result.set(point.date, day);
  }
  return result;
}

function createPeriods(points: Map<string, {records: number; people: Map<string, number>}>) {
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
      const point = points.get(key);
      return {date, key, records: point?.records ?? 0, people: [...(point?.people ?? new Map()).entries()].map(([entityId, records]) => ({entityId, records})), inPeriod: date >= start && date < end};
    });
    const months = Array.from({length: 12}, (_, month) => {
      const date = new Date(Date.UTC(year, month, 1));
      const firstMonday = addDays(date, (8 - date.getUTCDay()) % 7);
      return {key: `${year}-${String(month + 1).padStart(2, "0")}`, label: MONTHS[month], column: Math.floor((firstMonday.valueOf() - gridStart.valueOf()) / DAY_MS / 7) + 1};
    });
    periods.push({key: `${year}`, label: `${year}`, weeks, months, days});
  }
  return periods;
}

function parseDate(value: string) { return new Date(`${value}T00:00:00Z`); }
function addDays(date: Date, amount: number) { return new Date(date.valueOf() + amount * DAY_MS); }
function formatNumber(value: number) { return Intl.NumberFormat("es-AR").format(value); }
function formatDate(date: Date) { return new Intl.DateTimeFormat("es-AR", {day: "numeric", month: "short", year: "numeric", timeZone: "UTC"}).format(date); }
function locationLabel(value: CalendarLocation) { return value === "all" ? "Ambas sedes" : value === "casa-rosada" ? "Casa Rosada" : "Olivos"; }
function calendarDescription(activeDays: number, peak: [string, {records: number}] | undefined, location: CalendarLocation, sharedDays = 0) {
  if (!peak) return `No hay actividad diaria disponible para ${locationLabel(location)}.`;
  const shared = sharedDays ? ` ${formatNumber(sharedDays)} ${sharedDays === 1 ? "día tiene" : "días tienen"} registros de más de una persona seleccionada.` : "";
  return `${formatNumber(activeDays)} ${activeDays === 1 ? "día" : "días"} con actividad en ${locationLabel(location)}. El máximo fue el ${formatDate(parseDate(peak[0]))}, con ${formatNumber(peak[1].records)} registros.${shared}`;
}

function personColors(day: CalendarDay, series: ComparisonSeries[]) {
  if (!series.length || !day.people.length) return [];
  return day.people.map((person) => series.find((item) => item.entityId === person.entityId)?.color).filter(Boolean) as string[];
}

function dayColor(day: CalendarDay, colors: string[], fallback: (value: number) => string) {
  if (!colors.length) return {backgroundColor: fallback(day.records)};
  if (colors.length === 1) return {backgroundColor: colors[0]};
  return {backgroundColor: "#fff"};
}

function dayTitle(day: CalendarDay, series: ComparisonSeries[], mileiPresent = false) {
  const detail = day.people.map((person) => {
    const name = series.find((item) => item.entityId === person.entityId)?.name ?? "Persona";
    return `${name}: ${formatNumber(person.records)}`;
  });
  return `${formatDate(day.date)}: ${formatNumber(day.records)} registros${detail.length ? ` · ${detail.join(" · ")}` : ""}${mileiPresent ? " · Javier Milei registra actividad en Casa Rosada" : ""}`;
}
