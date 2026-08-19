import {Database, Download, Search, ShieldCheck} from "lucide-react";
import {useEffect, useMemo, useState} from "react";
import {HeatmapChart} from "./components/HeatmapChart";
import {PersonProfile} from "./components/PersonProfile";
import {PurposeChart} from "./components/PurposeChart";
import {SearchResults} from "./components/SearchResults";
import {TrendChart} from "./components/TrendChart";
import {useData} from "./hooks/useData";
import {useSearch} from "./hooks/useSearch";
import type {AccessEvent, Analytics, ExportFile, Meta, PersonSummary, SearchFilters} from "./types";

const DEFAULT_FILTERS: SearchFilters = {location: "all", year: "all", recordType: "all"};

export default function App() {
  const meta = useData<Meta>("meta.json");
  const exportsData = useData<ExportFile[]>("exports/index.json");
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<SearchFilters>(DEFAULT_FILTERS);
  const search = useSearch(query, filters);
  const [selected, setSelected] = useState<PersonSummary[]>([]);
  const [events, setEvents] = useState<{data: AccessEvent[]; loading: boolean; error: string | null}>({data: [], loading: false, error: null});
  const years = useMemo(() => {
    const first = meta.data?.first_date ? new Date(meta.data.first_date).getUTCFullYear() : 2023;
    const last = meta.data?.last_date ? new Date(meta.data.last_date).getUTCFullYear() : new Date().getFullYear();
    return Array.from({length: Math.max(1, last - first + 1)}, (_, index) => last - index);
  }, [meta.data]);

  const selectionKey = selected.map((person) => person.entity_id).sort().join(",");
  useEffect(() => {
    if (!selected.length) {
      setEvents({data: [], loading: false, error: null});
      return;
    }
    const controller = new AbortController();
    const selectedIds = new Set(selected.map((person) => person.entity_id));
    const shards = [...new Set(selected.map((person) => person.event_shard))];
    setEvents({data: [], loading: true, error: null});
    Promise.all(shards.map(async (shard) => {
      const response = await fetch(new URL(`data/events/${shard}.json`, document.baseURI), {signal: controller.signal});
      if (!response.ok) throw new Error("El archivo de detalle no está disponible");
      return response.json() as Promise<AccessEvent[]>;
    }))
      .then((groups) => setEvents({data: groups.flat().filter((row) => selectedIds.has(row.entity_id)), loading: false, error: null}))
      .catch((error: Error) => {
        if (error.name !== "AbortError") setEvents({data: [], loading: false, error: error.message});
      });
    return () => controller.abort();
  // selectionKey represents the same stable selection without refetching on array identity changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectionKey]);

  const selectedIds = useMemo(() => new Set(selected.map((person) => person.entity_id)), [selected]);
  const selectionAnalytics = useMemo(() => aggregateEvents(events.data), [events.data]);
  const heatmapLocation = useMemo(() => {
    const totals = events.data.reduce((result, event) => ({...result, [event.location]: result[event.location] + 1}), {"casa-rosada": 0, olivos: 0});
    return totals.olivos > totals["casa-rosada"] ? "olivos" : "casa-rosada";
  }, [events.data]);

  function togglePerson(person: PersonSummary) {
    setSelected((current) => current.some((item) => item.entity_id === person.entity_id)
      ? current.filter((item) => item.entity_id !== person.entity_id)
      : [...current, person]);
  }

  const statusMessage = search.loading ? "Buscando…" : query.trim().length >= 2 ? `${search.results.length} resultados para ${query}` : "";
  const selectedLabel = selected.length === 1 ? selected[0].canonical_name : `${selected.length} variantes seleccionadas`;

  return <>
    <a className="skip-link" href="#main">Saltar al contenido</a>
    <header className="site-header">
      <a className="brand" href="./" aria-label="Accesos públicos, inicio"><span className="brand-mark" aria-hidden="true"><Database /></span><span>Accesos <em>públicos</em></span></a>
      <nav aria-label="Principal"><a href="#buscar">Buscar</a><a href="#panorama">Gráficos</a><a href="#descargas">Descargas</a></nav>
    </header>
    <main id="main">
      <section className="hero" aria-labelledby="page-title">
        <div className="hero-copy"><p className="eyebrow">Casa Rosada y Quinta de Olivos</p><h1 id="page-title">Buscador de accesos presidenciales</h1><p>Consultá registros públicos y comprobá cada dato en su fuente original.</p></div>
        <div className="hero-facts" aria-label="Estado de la base"><div><strong>{formatNumber(meta.data?.record_count)}</strong><span>registros</span></div><div><strong>{formatNumber(meta.data?.people_count)}</strong><span>personas</span></div><div><strong>{formatNumber(meta.data?.source_count)}</strong><span>PDF</span></div></div>
      </section>

      <section className="search-section" id="buscar" aria-labelledby="search-title">
        <div className="section-heading"><div><p className="eyebrow">Buscador</p><h2 id="search-title">Encontrá y agrupá personas</h2></div><p>Seleccioná varias coincidencias cuando parezcan ser la misma persona escrita de distintas maneras.</p></div>
        <div className="search-panel">
          <form className="search-form" role="search" onSubmit={(event) => event.preventDefault()}>
            <label htmlFor="person-query">Nombre, DNI o CUIL</label>
            <div className="search-input-wrap"><Search aria-hidden="true" /><input id="person-query" name="query" type="search" autoComplete="off" spellCheck="false" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ej.: Ana Pérez o 20.123.456" /></div>
            <div className="filters" aria-label="Filtros de búsqueda">
              <label>Sede<select value={filters.location} onChange={(event) => setFilters({...filters, location: event.target.value as SearchFilters["location"]})}><option value="all">Todas</option><option value="casa-rosada">Casa Rosada</option><option value="olivos">Olivos</option></select></label>
              <label>Año<select value={filters.year} onChange={(event) => setFilters({...filters, year: event.target.value === "all" ? "all" : Number(event.target.value)})}><option value="all">Todos</option>{years.map((year) => <option value={year} key={year}>{year}</option>)}</select></label>
              <label>Tipo<select value={filters.recordType} onChange={(event) => setFilters({...filters, recordType: event.target.value as SearchFilters["recordType"]})}><option value="all">Todos</option><option value="movement">Movimiento</option><option value="person">Persona</option><option value="vehicle">Vehículo</option><option value="visitor">Visita</option></select></label>
              {JSON.stringify(filters) !== JSON.stringify(DEFAULT_FILTERS) && <button type="button" className="text-button" onClick={() => setFilters(DEFAULT_FILTERS)}>Limpiar filtros</button>}
            </div>
          </form>
          <div className="results-region" aria-busy={search.loading}><div className="sr-only" role="status" aria-live="polite">{statusMessage}</div><SearchResults query={query} results={search.results} selectedIds={selectedIds} loading={search.loading} error={search.error} onToggle={togglePerson} /></div>
        </div>
        {selected.length > 0 && <PersonProfile people={selected} events={events.data} loading={events.loading} error={events.error} onRemove={(entityId) => setSelected((current) => current.filter((person) => person.entity_id !== entityId))} onClear={() => setSelected([])} />}
      </section>

      <section className="dashboard-section" id="panorama" aria-labelledby="dashboard-title">
        <div className="section-heading"><div><p className="eyebrow">Gráficos</p><h2 id="dashboard-title">Actividad de la selección</h2></div><p>{selected.length ? `Los gráficos reúnen los registros de ${selectedLabel}.` : "Seleccioná una o más personas para actualizar esta sección."}</p></div>
        {!selected.length && <div className="selection-empty"><strong>No hay personas seleccionadas</strong><span>Buscá arriba y elegí las variantes que quieras comparar como una sola identidad.</span></div>}
        {events.loading && <p role="status">Cargando gráficos…</p>}
        {events.error && <div className="notice notice--error" role="alert"><strong>No se pudieron cargar los gráficos.</strong><span>{events.error}</span></div>}
        {selected.length > 0 && !events.loading && !events.error && <div className="dashboard-grid"><div className="dashboard-wide"><TrendChart data={selectionAnalytics.monthly} /></div><HeatmapChart data={selectionAnalytics.heatmap} location={heatmapLocation} /><PurposeChart data={selectionAnalytics.purposes} /></div>}
      </section>

      <section className="downloads-section" id="descargas" aria-labelledby="downloads-title">
        <div className="downloads-intro"><p className="eyebrow">Datos abiertos</p><h2 id="downloads-title">Descargá los registros</h2><p>CSV comprimidos por sede y mes, con procedencia y página de la fuente.</p><div className="trust-points"><span><ShieldCheck aria-hidden="true" />Checksums y procedencia</span><span><Database aria-hidden="true" />Esquema estable</span></div></div>
        <div className="download-list">{exportsData.data?.length ? exportsData.data.slice(-12).reverse().map((file) => <a className="download-row" key={`${file.location}-${file.year}-${file.month}`} href={new URL(`data/exports/${file.path}`, document.baseURI).href} download><span><strong>{file.location === "casa-rosada" ? "Casa Rosada" : "Olivos"}</strong><small>{monthLabel(file.year, file.month)} · {file.records.toLocaleString("es-AR")} registros</small></span><Download aria-hidden="true" /></a>) : <p className="empty-state">Los CSV aparecerán después de la primera actualización de datos.</p>}</div>
      </section>
    </main>
    <footer><p>Datos publicados por sus fuentes originales. Este proyecto facilita su consulta, no certifica su exactitud.</p><p>Actualización: {meta.data?.generated_at ? formatDate(meta.data.generated_at) : "pendiente"}</p></footer>
  </>;
}

function aggregateEvents(events: AccessEvent[]): Analytics {
  const monthly = new Map<string, {month: string; location: AccessEvent["location"]; records: number; people: Set<string>}>();
  const heatmap = new Map<string, {location: AccessEvent["location"]; weekday: number; hour: number; records: number}>();
  const purposes = new Map<string, {location: AccessEvent["location"]; label: string; records: number}>();

  for (const event of events) {
    const dateValue = event.occurred_at ?? event.entered_at ?? event.exited_at;
    if (dateValue) {
      const date = new Date(dateValue);
      if (!Number.isNaN(date.valueOf())) {
        const month = date.toISOString().slice(0, 7);
        const monthKey = `${month}|${event.location}`;
        const monthPoint = monthly.get(monthKey) ?? {month, location: event.location, records: 0, people: new Set<string>()};
        monthPoint.records += 1;
        monthPoint.people.add(event.entity_id);
        monthly.set(monthKey, monthPoint);
        const heatmapKey = `${event.location}|${date.getDay()}|${date.getHours()}`;
        const heatmapPoint = heatmap.get(heatmapKey) ?? {location: event.location, weekday: date.getDay(), hour: date.getHours(), records: 0};
        heatmapPoint.records += 1;
        heatmap.set(heatmapKey, heatmapPoint);
      }
    }
    const label = event.destination ?? event.purpose ?? event.activity;
    if (label) {
      const purposeKey = `${event.location}|${label}`;
      const purposePoint = purposes.get(purposeKey) ?? {location: event.location, label, records: 0};
      purposePoint.records += 1;
      purposes.set(purposeKey, purposePoint);
    }
  }

  return {
    daily: [],
    monthly: [...monthly.values()].map(({people, ...point}) => ({...point, people: people.size})).sort((a, b) => a.month.localeCompare(b.month)),
    heatmap: [...heatmap.values()],
    purposes: [...purposes.values()].sort((a, b) => b.records - a.records),
    coverage: {first_date: null, last_date: null},
  };
}

function formatNumber(value?: number) { return value == null ? "—" : Intl.NumberFormat("es-AR", {notation: value >= 100000 ? "compact" : "standard", maximumFractionDigits: 1}).format(value); }
function formatDate(value: string) { return new Intl.DateTimeFormat("es-AR", {dateStyle: "long"}).format(new Date(value)); }
function monthLabel(year: number, month: number) { return new Intl.DateTimeFormat("es-AR", {month: "long", year: "numeric", timeZone: "UTC"}).format(new Date(Date.UTC(year, month - 1, 1))); }
