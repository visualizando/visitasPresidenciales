import {Database, Download, Search} from "lucide-react";
import {useDeferredValue, useEffect, useMemo, useState} from "react";
import {CalendarChart} from "./components/CalendarChart";
import {CoverageReport} from "./components/CoverageReport";
import {HeatmapChart} from "./components/HeatmapChart";
import {PersonProfile} from "./components/PersonProfile";
import {PurposeChart} from "./components/PurposeChart";
import {Rankings} from "./components/Rankings";
import {SearchResults} from "./components/SearchResults";
import {SectionNav} from "./components/SectionNav";
import {useData} from "./hooks/useData";
import {useCoincidences} from "./hooks/useCoincidences";
import {useSearch} from "./hooks/useSearch";
import type {AccessEvent, Analytics, ExportFile, Meta, PersonSummary, SearchFilters} from "./types";
import {fetchGzipJson} from "./utils/fetchGzipJson";
import {comparisonSeries} from "./utils/personColors";
import {buildSelectionHash, parseSelectionHash, selectionIdShard} from "./utils/selectionHash";

const DEFAULT_FILTERS: SearchFilters = {location: "all", year: "all", recordType: "all"};

export default function App() {
  const meta = useData<Meta>("meta.json");
  const analytics = useData<Analytics>("analytics/overview.json");
  const exportsData = useData<ExportFile[]>("exports/index.json");
  const [selected, setSelected] = useState<PersonSummary[]>([]);
  const [selectionHashReady, setSelectionHashReady] = useState(false);
  const [selectionHashError, setSelectionHashError] = useState<string | null>(null);
  const coincidences = useCoincidences(selected);
  const [events, setEvents] = useState<{data: AccessEvent[]; loading: boolean; error: string | null}>({data: [], loading: false, error: null});
  const selectionKey = selected.map((person) => person.entity_id).sort().join(",");
  useEffect(() => {
    let activeController: AbortController | null = null;
    let disposed = false;
    const restoreSelection = () => {
      activeController?.abort();
      const entityIds = parseSelectionHash(window.location.hash);
      if (entityIds === null || !entityIds.length) {
        setSelected([]);
        setSelectionHashError(null);
        setSelectionHashReady(true);
        return;
      }
      const controller = new AbortController();
      activeController = controller;
      setSelectionHashReady(false);
      setSelectionHashError(null);
      const shards = [...new Set(entityIds.map(selectionIdShard))];
      Promise.all(shards.map((shard) => fetchGzipJson<PersonSummary[]>(new URL(`data/search/id/${shard}.json.gz`, document.baseURI), controller.signal)))
        .then((groups) => {
          if (disposed) return;
          const peopleById = new Map(groups.flat().map((person) => [person.entity_id, person]));
          const people = entityIds.map((entityId) => peopleById.get(entityId)).filter(Boolean) as PersonSummary[];
          setSelected(people);
          if (people.length !== entityIds.length) setSelectionHashError("Algunas personas del enlace ya no están disponibles en la base publicada.");
        })
        .catch((error: Error) => {
          if (error.name !== "AbortError" && !disposed) {
            setSelected([]);
            setSelectionHashError("No se pudo reconstruir la selección compartida.");
          }
        })
        .finally(() => {
          if (!disposed && !controller.signal.aborted) setSelectionHashReady(true);
        });
    };
    restoreSelection();
    window.addEventListener("hashchange", restoreSelection);
    return () => {
      disposed = true;
      activeController?.abort();
      window.removeEventListener("hashchange", restoreSelection);
    };
  }, []);

  useEffect(() => {
    if (!selectionHashReady) return;
    const nextHash = buildSelectionHash(selected.map((person) => person.entity_id));
    const currentSelection = parseSelectionHash(window.location.hash);
    if (nextHash && window.location.hash !== nextHash) {
      window.history.replaceState(window.history.state, "", `${window.location.pathname}${window.location.search}${nextHash}`);
    } else if (!nextHash && currentSelection !== null) {
      window.history.replaceState(window.history.state, "", `${window.location.pathname}${window.location.search}`);
    }
  }, [selectionHashReady, selectionKey, selected]);

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
      return fetchGzipJson<AccessEvent[]>(
        new URL(`data/events/${shard}.json.gz`, document.baseURI),
        controller.signal,
      );
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
  const personSeries = useMemo(() => comparisonSeries(selected), [selected]);
  const selectionAnalytics = useMemo(() => aggregateEvents(events.data), [events.data]);
  const activeAnalytics = selected.length ? selectionAnalytics : analytics.data;
  const heatmapLocation = useMemo(() => {
    const totals = (activeAnalytics?.heatmap ?? []).reduce((result, point) => ({...result, [point.location]: result[point.location] + point.records}), {"casa-rosada": 0, olivos: 0});
    return totals.olivos > totals["casa-rosada"] ? "olivos" : "casa-rosada";
  }, [activeAnalytics]);
  const dashboardLoading = selected.length ? events.loading : analytics.loading;
  const dashboardError = selected.length ? events.error : analytics.error;

  function togglePerson(person: PersonSummary) {
    setSelected((current) => current.some((item) => item.entity_id === person.entity_id)
      ? current.filter((item) => item.entity_id !== person.entity_id)
      : [...current, person]);
  }

  const selectedLabel = selected.length === 1 ? selected[0].canonical_name : `${selected.length} personas o variantes seleccionadas`;

  return <>
    <a className="skip-link" href="#main">Saltar al contenido</a>
    <header className="site-header">
      <a className="brand" href="./" aria-label="Accesos públicos, inicio"><span className="brand-mark" aria-hidden="true"><Database /></span><span>Accesos <em>públicos</em></span></a>
    </header>
    <main id="main">
      <section className="hero" aria-labelledby="page-title">
        <div className="hero-copy"><p className="eyebrow">Datos públicos</p><h1 id="page-title">Explorador de accesos a Olivos y Casa Rosada</h1><p>Este explorador se basa en datos obtenidos mediante pedidos de acceso a la información que Poder Ciudadano realiza regularmente.</p></div>
        <dl className="hero-facts" aria-label="Estado y cobertura de la base"><div><dd>{formatNumber(meta.data?.record_count)}</dd><dt>registros</dt></div><div><dd>{formatNumber(meta.data?.people_count)}</dd><dt>personas</dt></div><div><dd>{formatNumber(meta.data?.source_count)}</dd><dt>PDF</dt></div><div><dd>{formatMetricDate(meta.data?.first_date)}</dd><dt>primer registro</dt></div><div><dd>{formatMetricDate(meta.data?.last_date)}</dd><dt>último registro</dt></div></dl>
      </section>
      <SectionNav preserveHash={selected.length > 0 || !selectionHashReady} />

      <section className="search-section" id="buscar" aria-labelledby="search-title">
        <div className="section-heading"><div><p className="eyebrow">Buscador</p><h2 id="search-title">Encontrá y agrupá personas</h2></div><p>Seleccioná varias coincidencias cuando parezcan ser la misma persona escrita de distintas maneras.</p></div>
        {selectionHashError && <div className="notice notice--error" role="alert"><strong>El enlace compartido está incompleto.</strong><span>{selectionHashError}</span></div>}
        <SearchExplorer firstDate={meta.data?.first_date} lastDate={meta.data?.last_date} selectedIds={selectedIds} onToggle={togglePerson} />
        {selected.length > 0 && <PersonProfile people={selected} events={events.data} loading={events.loading} error={events.error} coincidences={coincidences.data} coincidencesLoading={coincidences.loading} coincidencesError={coincidences.error} onRemove={(entityId) => setSelected((current) => current.filter((person) => person.entity_id !== entityId))} onClear={() => setSelected([])} />}
      </section>

      <section className="dashboard-section" id="panorama" aria-labelledby="dashboard-title">
        <div className="section-heading"><div><p className="eyebrow">Gráficos</p><h2 id="dashboard-title">Actividad</h2></div><p>{selected.length ? `Vista filtrada por ${selectedLabel}. Limpiá la selección para volver al total.` : "Panorama general de todos los registros publicados."}</p></div>
        {dashboardLoading && <p role="status">Cargando gráficos…</p>}
        {dashboardError && <div className="notice notice--error" role="alert"><strong>No se pudieron cargar los gráficos.</strong><span>{dashboardError}</span></div>}
        {activeAnalytics && !dashboardLoading && !dashboardError && <div className="dashboard-grid"><div className="dashboard-wide"><CalendarChart data={activeAnalytics.daily} location={selected.length ? "all" : heatmapLocation} series={personSeries} mileiCasaRosadaDays={analytics.data?.milei_casa_rosada_days} /></div><HeatmapChart data={activeAnalytics.heatmap} location={heatmapLocation} series={personSeries} /><PurposeChart data={activeAnalytics.purposes} series={personSeries} /></div>}
      </section>

      <section className="downloads-section" id="descargas" aria-labelledby="downloads-title">
        <div className="downloads-intro"><p className="eyebrow">Datos abiertos</p><h2 id="downloads-title">Descargá los registros</h2><p>Un CSV comprimido por año con los registros de Olivos y Casa Rosada.</p></div>
        <div className="download-list">{exportsData.data?.length ? [...exportsData.data].sort((left, right) => right.year - left.year).map((file) => <a className="download-row" key={file.year} href={new URL(`data/exports/${file.path}`, document.baseURI).href} download><span><strong>{file.year}</strong><small>{file.records.toLocaleString("es-AR")} registros</small></span><Download aria-hidden="true" /></a>) : <p className="empty-state">Los CSV aparecerán después de la primera actualización de datos.</p>}</div>
      </section>

      <section className="rankings-section" id="rankings" aria-labelledby="rankings-title">
        <Rankings />
      </section>
      <section className="coverage-section" id="cobertura" aria-labelledby="coverage-title">
        <CoverageReport />
      </section>
    </main>
    <footer>
      <div className="footer-inner">
        <div className="footer-lead"><strong>Accesos públicos</strong><p>Una herramienta para explorar los registros de ingreso a Olivos y Casa Rosada.</p></div>
        <div className="footer-details"><p>Datos obtenidos por <a href="https://poderciudadano.org/">Poder Ciudadano</a> mediante pedidos de acceso a la información pública.</p><p>Creación y diseño: <a href="https://visualizando.ar/">Andrés Snitcofsky · Visualizando</a>.</p></div>
        <p className="footer-meta"><a href="https://github.com/visualizando/visitasPresidenciales">Código en GitHub</a><span>Actualización: {meta.data?.generated_at ? formatDate(meta.data.generated_at) : "pendiente"}</span></p>
      </div>
    </footer>
  </>;
}

function SearchExplorer({firstDate, lastDate, selectedIds, onToggle}: {
  firstDate?: string | null;
  lastDate?: string | null;
  selectedIds: Set<string>;
  onToggle: (person: PersonSummary) => void;
}) {
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const [filters, setFilters] = useState<SearchFilters>(DEFAULT_FILTERS);
  const search = useSearch(deferredQuery, filters);
  const inputPending = query !== deferredQuery;
  const loading = inputPending || search.loading;
  const years = useMemo(() => {
    const first = firstDate ? new Date(firstDate).getUTCFullYear() : 2023;
    const last = lastDate ? new Date(lastDate).getUTCFullYear() : new Date().getFullYear();
    return Array.from({length: Math.max(1, last - first + 1)}, (_, index) => last - index);
  }, [firstDate, lastDate]);
  const statusMessage = loading ? "Buscando…" : query.trim().length >= 2 ? `${search.results.length} resultados para ${query}` : "";

  return <div className="search-panel">
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
    <div className="results-region" aria-busy={loading}><div className="sr-only" role="status" aria-live="polite">{statusMessage}</div><SearchResults query={query} results={search.results} selectedIds={selectedIds} loading={loading} phase={search.phase} error={search.error} onToggle={onToggle} /></div>
  </div>;
}

function aggregateEvents(events: AccessEvent[]): Analytics {
  const daily = new Map<string, {date: string; location: AccessEvent["location"]; record_type: AccessEvent["record_type"]; records: number; people: Set<string>; entity_id: string; person_name: string}>();
  const monthly = new Map<string, {month: string; location: AccessEvent["location"]; records: number; people: Set<string>; entity_id: string; person_name: string}>();
  const heatmap = new Map<string, {location: AccessEvent["location"]; weekday: number; hour: number; records: number; entity_id: string; person_name: string}>();
  const purposes = new Map<string, {location: AccessEvent["location"]; label: string; records: number; entity_id: string; person_name: string}>();

  for (const event of events) {
    const dateValue = event.occurred_at ?? event.entered_at ?? event.exited_at;
    if (dateValue) {
      const date = new Date(dateValue);
      if (!Number.isNaN(date.valueOf())) {
        const day = date.toISOString().slice(0, 10);
        const dayKey = `${day}|${event.location}|${event.record_type}|${event.entity_id}`;
        const dayPoint = daily.get(dayKey) ?? {date: day, location: event.location, record_type: event.record_type, records: 0, people: new Set<string>(), entity_id: event.entity_id, person_name: event.canonical_name};
        dayPoint.records += 1;
        dayPoint.people.add(event.entity_id);
        daily.set(dayKey, dayPoint);
        const month = date.toISOString().slice(0, 7);
        const monthKey = `${month}|${event.location}|${event.entity_id}`;
        const monthPoint = monthly.get(monthKey) ?? {month, location: event.location, records: 0, people: new Set<string>(), entity_id: event.entity_id, person_name: event.canonical_name};
        monthPoint.records += 1;
        monthPoint.people.add(event.entity_id);
        monthly.set(monthKey, monthPoint);
        const heatmapKey = `${event.location}|${date.getDay()}|${date.getHours()}|${event.entity_id}`;
        const heatmapPoint = heatmap.get(heatmapKey) ?? {location: event.location, weekday: date.getDay(), hour: date.getHours(), records: 0, entity_id: event.entity_id, person_name: event.canonical_name};
        heatmapPoint.records += 1;
        heatmap.set(heatmapKey, heatmapPoint);
      }
    }
    const label = event.destination ?? event.purpose ?? event.activity;
    if (label) {
      const purposeKey = `${event.location}|${label}|${event.entity_id}`;
      const purposePoint = purposes.get(purposeKey) ?? {location: event.location, label, records: 0, entity_id: event.entity_id, person_name: event.canonical_name};
      purposePoint.records += 1;
      purposes.set(purposeKey, purposePoint);
    }
  }

  return {
    daily: [...daily.values()].map(({people, ...point}) => ({...point, people: people.size})).sort((a, b) => a.date.localeCompare(b.date)),
    monthly: [...monthly.values()].map(({people, ...point}) => ({...point, people: people.size})).sort((a, b) => a.month.localeCompare(b.month)),
    heatmap: [...heatmap.values()],
    purposes: [...purposes.values()].sort((a, b) => b.records - a.records),
    coverage: {first_date: null, last_date: null},
  };
}

function formatNumber(value?: number) { return value == null ? "—" : Intl.NumberFormat("es-AR", {notation: value >= 100000 ? "compact" : "standard", maximumFractionDigits: 1}).format(value); }
function formatMetricDate(value?: string | null) { return value ? new Intl.DateTimeFormat("es-AR", {day: "2-digit", month: "short", year: "numeric", timeZone: "UTC"}).format(new Date(value)) : "—"; }
function formatDate(value: string) { return new Intl.DateTimeFormat("es-AR", {dateStyle: "long"}).format(new Date(value)); }
