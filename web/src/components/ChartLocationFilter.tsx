import {useId} from "react";
import type {Location} from "../types";

type LocationChoice = Location | "both";

const OPTIONS: {value: LocationChoice; label: string; locations: Location[]}[] = [
  {value: "casa-rosada", label: "Casa Rosada", locations: ["casa-rosada"]},
  {value: "olivos", label: "Olivos", locations: ["olivos"]},
  {value: "both", label: "Casa Rosada y Olivos", locations: ["casa-rosada", "olivos"]},
];

export function ChartLocationFilter({value, onChange}: {value: Location[]; onChange: (value: Location[]) => void}) {
  const name = useId();
  const selected: LocationChoice = value.length === 2 ? "both" : (value[0] ?? "both");

  return <fieldset className="chart-location-filter">
    <legend className="sr-only">Sede mostrada</legend>
    <div>{OPTIONS.map((option) => <label key={option.value}>
      <input type="radio" name={name} value={option.value} checked={selected === option.value} onChange={() => onChange(option.locations)} />
      {option.label}
    </label>)}</div>
  </fieldset>;
}
