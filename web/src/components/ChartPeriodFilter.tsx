export type ChartPeriod = "all" | "current-presidency";

export function ChartPeriodFilter({value, onChange}: {value: ChartPeriod; onChange: (value: ChartPeriod) => void}) {
  return <fieldset className="chart-period-filter">
    <legend className="sr-only">Período mostrado</legend>
    <span>Mostrar todo</span>
    <label className="period-switch">
      <input
        type="checkbox"
        checked={value === "current-presidency"}
        aria-label="Mostrar solo la presidencia actual"
        onChange={(event) => onChange(event.target.checked ? "current-presidency" : "all")}
      />
      <span aria-hidden="true" />
    </label>
    <span>Solo presidencia actual</span>
  </fieldset>;
}
