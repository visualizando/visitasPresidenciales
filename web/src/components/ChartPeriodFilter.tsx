export type ChartPeriod = "all" | "current-presidency";

const OPTIONS: {value: ChartPeriod; label: string}[] = [
  {value: "all", label: "Todo"},
  {value: "current-presidency", label: "Presidencia actual"},
];

export function ChartPeriodFilter({value, onChange}: {value: ChartPeriod; onChange: (value: ChartPeriod) => void}) {
  return <fieldset className="chart-period-filter">
    <legend>Período</legend>
    <div className="segmented-control">{OPTIONS.map((option) => <button type="button" key={option.value} aria-pressed={value === option.value} onClick={() => onChange(option.value)}>{option.label}</button>)}</div>
  </fieldset>;
}
