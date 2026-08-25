import {useId} from "react";
import type {Location} from "../types";

const OPTIONS: {value: Location; label: string}[] = [
  {value: "casa-rosada", label: "Casa Rosada"},
  {value: "olivos", label: "Olivos"},
];

export function ChartLocationFilter({value, onChange}: {value: Location[]; onChange: (value: Location[]) => void}) {
  const helpId = useId();
  function toggle(location: Location) {
    if (value.includes(location)) {
      if (value.length === 1) return;
      onChange(value.filter((item) => item !== location));
    } else {
      onChange([...value, location]);
    }
  }

  return <fieldset className="chart-location-filter">
    <legend>Sedes</legend>
    <div>{OPTIONS.map((option) => {
      const checked = value.includes(option.value);
      return <label key={option.value}><input type="checkbox" name="chart-location" value={option.value} checked={checked} disabled={checked && value.length === 1} aria-describedby={helpId} onChange={() => toggle(option.value)} />{option.label}</label>;
    })}</div>
    <small id={helpId}>Elegí al menos una.</small>
  </fieldset>;
}
