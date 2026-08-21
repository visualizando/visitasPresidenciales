import {AlertTriangle, Check, ChevronLeft, ChevronRight, Clock3, GitMerge, Layers3, RotateCcw, Search, ShieldCheck, X} from "lucide-react";
import {StrictMode, useEffect, useMemo, useRef, useState} from "react";
import {createRoot} from "react-dom/client";
import type {ActivityLevel, BatchPreview, Candidate, CandidatePage, CandidateStatus, Confidence, Summary} from "./types";
import "./styles.css";

const PAGE_SIZE = 50;
const EMPTY_SUMMARY: Summary = {total: 0, pending: 0, merged: 0, rejected: 0, deferred: 0, high: 0, review: 0};

function App() {
  const [token, setToken] = useState("");
  const [page, setPage] = useState<CandidatePage | null>(null);
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [confidence, setConfidence] = useState<Confidence | "all">("high");
  const [status, setStatus] = useState<CandidateStatus | "all">("pending");
  const [activity, setActivity] = useState<ActivityLevel | "all">("all");
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const [mergeCandidate, setMergeCandidate] = useState<Candidate | null>(null);
  const [batchOpen, setBatchOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const selected = page?.items.find((candidate) => candidate.candidate_id === selectedId) ?? page?.items[0] ?? null;

  useEffect(() => {
    fetchJson<{token: string}>("/api/config")
      .then((config) => setToken(config.token))
      .catch((reason: Error) => setError(reason.message));
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedQuery(query.trim());
      setOffset(0);
    }, 220);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    const parameters = new URLSearchParams({q: debouncedQuery, confidence, status, activity, offset: String(offset), limit: String(PAGE_SIZE)});
    fetchJson<CandidatePage>(`/api/candidates?${parameters}`, {signal: controller.signal})
      .then((result) => {
        setPage(result);
        setSelectedId((current) => result.items.some((item) => item.candidate_id === current) ? current : result.items[0]?.candidate_id ?? null);
        setAnnouncement(`${result.total.toLocaleString("es-AR")} candidatos en esta vista.`);
      })
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setError(reason.message);
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [token, debouncedQuery, confidence, status, activity, offset]);

  useEffect(() => {
    function handleKeydown(event: KeyboardEvent) {
      const target = event.target as HTMLElement;
      if (target.closest("input, select, textarea, button, dialog")) return;
      if (event.key === "/") {
        event.preventDefault();
        searchRef.current?.focus();
      }
      if ((event.key === "j" || event.key === "k") && page?.items.length) {
        event.preventDefault();
        const current = Math.max(0, page.items.findIndex((item) => item.candidate_id === selected?.candidate_id));
        const next = event.key === "j" ? Math.min(page.items.length - 1, current + 1) : Math.max(0, current - 1);
        setSelectedId(page.items[next].candidate_id);
        document.getElementById(`candidate-${page.items[next].candidate_id}`)?.focus();
      }
    }
    window.addEventListener("keydown", handleKeydown);
    return () => window.removeEventListener("keydown", handleKeydown);
  }, [page, selected]);

  async function decide(candidate: Candidate, action: "reject" | "defer" | "undo") {
    try {
      setError(null);
      await sendDecision(token, {candidate_id: candidate.candidate_id, action});
      setAnnouncement(action === "reject" ? "Candidato rechazado." : action === "defer" ? "Candidato pospuesto." : "Decisión deshecha.");
      await refreshCurrentPage();
    } catch (reason) {
      setError((reason as Error).message);
    }
  }

  async function refreshCurrentPage() {
    const parameters = new URLSearchParams({q: debouncedQuery, confidence, status, activity, offset: String(offset), limit: String(PAGE_SIZE)});
    const result = await fetchJson<CandidatePage>(`/api/candidates?${parameters}`);
    if (!result.items.length && offset > 0) {
      setOffset(Math.max(0, offset - PAGE_SIZE));
      return;
    }
    setPage(result);
    setSelectedId(result.items[0]?.candidate_id ?? null);
  }

  const summary = page?.summary ?? EMPTY_SUMMARY;
  const start = page?.total ? offset + 1 : 0;
  const end = page ? Math.min(offset + PAGE_SIZE, page.total) : 0;

  return <>
    <a className="skip-link" href="#candidate-detail">Saltar a la comparación</a>
    <header className="app-header">
      <div>
        <p className="eyebrow">Herramienta privada · sólo local</p>
        <h1>Curación de identidades</h1>
        <p>Revisá variantes sin modificar la base hasta confirmar una decisión.</p>
      </div>
      <div className="local-badge"><ShieldCheck aria-hidden="true" /><span><strong>127.0.0.1</strong>Los datos no salen de este equipo</span></div>
    </header>

    <main className="workspace">
      <section className="summary-strip" aria-label="Resumen de curación">
        <Metric label="Pendientes" value={summary.pending} accent />
        <Metric label="Unificados" value={summary.merged} />
        <Metric label="Rechazados" value={summary.rejected} />
        <Metric label="Pospuestos" value={summary.deferred} />
        <Metric label="Alta confianza" value={summary.high} />
      </section>

      <section className="toolbar" aria-label="Filtros de candidatos">
        <label className="search-field"><span>Buscar nombre o documento</span><div><Search aria-hidden="true" /><input ref={searchRef} type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ej.: Cerimedo o 28.675.966" autoComplete="off" /></div></label>
        <label><span>Confianza</span><select value={confidence} onChange={(event) => {setConfidence(event.target.value as Confidence | "all"); setOffset(0);}}><option value="high">Alta confianza</option><option value="review">Requiere revisión</option><option value="all">Todas</option></select></label>
        <label><span>Estado</span><select value={status} onChange={(event) => {setStatus(event.target.value as CandidateStatus | "all"); setOffset(0);}}><option value="pending">Pendientes</option><option value="deferred">Pospuestos</option><option value="merged">Unificados</option><option value="rejected">Rechazados</option><option value="all">Todos</option></select></label>
        <label><span>Actividad combinada</span><select value={activity} onChange={(event) => {setActivity(event.target.value as ActivityLevel | "all"); setOffset(0);}}><option value="all">Todas · {formatCount(page?.activity_summary.all)}</option><option value="very_high">Muy alta · 100+ ({formatCount(page?.activity_summary.very_high)})</option><option value="high">Alta · 20–99 ({formatCount(page?.activity_summary.high)})</option><option value="medium">Media · 5–19 ({formatCount(page?.activity_summary.medium)})</option><option value="low">Baja · 1–4 ({formatCount(page?.activity_summary.low)})</option></select></label>
        <button className="button button--batch" type="button" onClick={() => setBatchOpen(true)}><Layers3 aria-hidden="true" /><span><strong>Fusión segura</strong><small>Ver lote con 100% de confianza</small></span></button>
      </section>

      {error && <div className="notice notice--error" role="alert"><AlertTriangle aria-hidden="true" /><span><strong>No se pudo completar la acción.</strong>{error}</span><button type="button" onClick={() => setError(null)} aria-label="Cerrar error"><X /></button></div>}
      <div className="sr-only" role="status" aria-live="polite">{announcement}</div>

      <div className="review-layout">
        <aside className="candidate-pane" aria-label="Cola de candidatos" aria-busy={loading}>
          <div className="pane-heading"><div><h2>Candidatos</h2><span>{start}–{end} de {page?.total.toLocaleString("es-AR") ?? "—"}</span></div><small>Atajos: <kbd>j</kbd>/<kbd>k</kbd> para recorrer, <kbd>/</kbd> para buscar</small></div>
          {loading && !page ? <CandidateSkeleton /> : page?.items.length ? <ol className="candidate-list">{page.items.map((candidate) => <li key={candidate.candidate_id}><button id={`candidate-${candidate.candidate_id}`} type="button" className="candidate-row" aria-current={selected?.candidate_id === candidate.candidate_id ? "true" : undefined} onClick={() => setSelectedId(candidate.candidate_id)}><span className="row-top"><StatusBadge status={candidate.status} /><b>{candidate.score}</b></span><strong>{candidate.left_name}</strong><span className="comparison-arrow" aria-hidden="true">↔</span><strong>{candidate.right_name}</strong><small><b>{candidate.total_records.toLocaleString("es-AR")} en total</b> · {candidate.left_records.toLocaleString("es-AR")} + {candidate.right_records.toLocaleString("es-AR")}</small></button></li>)}</ol> : <div className="empty-state"><Check aria-hidden="true" /><strong>No hay candidatos en esta vista.</strong><span>Probá otro estado, actividad, nivel de confianza o búsqueda.</span></div>}
          <nav className="pagination" aria-label="Paginación"><button type="button" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}><ChevronLeft aria-hidden="true" />Anterior</button><button type="button" disabled={!page || offset + PAGE_SIZE >= page.total || loading} onClick={() => setOffset(offset + PAGE_SIZE)}>Siguiente<ChevronRight aria-hidden="true" /></button></nav>
        </aside>

        <section className="detail-pane" id="candidate-detail" aria-labelledby="detail-title">
          {selected ? <CandidateDetail candidate={selected} onMerge={() => setMergeCandidate(selected)} onReject={() => decide(selected, "reject")} onDefer={() => decide(selected, "defer")} onUndo={() => decide(selected, "undo")} onBatch={() => setBatchOpen(true)} /> : <div className="empty-detail"><GitMerge aria-hidden="true" /><h2 id="detail-title">Elegí un candidato</h2><p>La comparación, la evidencia y las acciones aparecerán acá.</p></div>}
        </section>
      </div>
    </main>
    <footer>Las decisiones se guardan localmente en <code>data/curation/entity_merges.json</code>. Revisá el diff antes de commitear.</footer>
    <MergeDialog candidate={mergeCandidate} token={token} onClose={() => setMergeCandidate(null)} onSaved={async () => {setMergeCandidate(null); setAnnouncement("Identidades unificadas."); await refreshCurrentPage();}} onError={(message) => setError(message)} />
    <BatchDialog open={batchOpen} token={token} onClose={() => setBatchOpen(false)} onChanged={async (message) => {setAnnouncement(message); await refreshCurrentPage();}} onError={(message) => setError(message)} />
  </>;
}

function CandidateDetail({candidate, onMerge, onReject, onDefer, onUndo, onBatch}: {candidate: Candidate; onMerge: () => void; onReject: () => void; onDefer: () => void; onUndo: () => void; onBatch: () => void}) {
  const decided = candidate.status !== "pending";
  return <>
    <div className="detail-heading"><div><p className="eyebrow">Comparación seleccionada</p><h2 id="detail-title">¿Es la misma persona?</h2></div><div className={`score score--${candidate.confidence}`}><strong>{candidate.score}</strong><span>{candidate.confidence === "high" ? "confianza alta" : "revisar"}</span></div></div>
    <div className="person-grid">
      <PersonCard side="left" candidate={candidate} recommended={candidate.recommended_canonical_id === candidate.left_entity_id} />
      <PersonCard side="right" candidate={candidate} recommended={candidate.recommended_canonical_id === candidate.right_entity_id} />
    </div>
    <section className="evidence" aria-labelledby="evidence-title"><h3 id="evidence-title">Por qué fue propuesto</h3><ul>{candidate.reasons.map((reason) => <li key={reason}>{reasonLabel(reason)}</li>)}</ul>{candidate.warnings.length > 0 && <div className="warning"><AlertTriangle aria-hidden="true" /><span><strong>Requiere atención adicional</strong>{candidate.warnings.map(reasonLabel).join(" · ")}</span></div>}</section>
    <div className="action-bar">
      {decided ? <><span>Estado actual: <StatusBadge status={candidate.status} />{candidate.batch_id && <> · lote seguro</>}</span>{candidate.batch_id ? <button className="button button--secondary" type="button" onClick={onBatch}><Layers3 aria-hidden="true" />Administrar lote</button> : <button className="button button--secondary" type="button" onClick={onUndo}><RotateCcw aria-hidden="true" />Deshacer decisión</button>}</> : <><button className="button button--primary" type="button" onClick={onMerge}><GitMerge aria-hidden="true" />Unificar</button><button className="button button--danger" type="button" onClick={onReject}><X aria-hidden="true" />No son la misma</button><button className="button button--secondary" type="button" onClick={onDefer}><Clock3 aria-hidden="true" />Revisar después</button></>}
    </div>
  </>;
}

function BatchDialog({open, token, onClose, onChanged, onError}: {open: boolean; token: string; onClose: () => void; onChanged: (message: string) => Promise<void>; onError: (message: string) => void}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [preview, setPreview] = useState<BatchPreview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [working, setWorking] = useState(false);
  useEffect(() => {
    if (!open) {
      if (dialogRef.current?.open) dialogRef.current.close();
      return;
    }
    setPreview(null);
    setConfirmed(false);
    dialogRef.current?.showModal();
    fetchJson<BatchPreview>("/api/batch-preview").then(setPreview).catch((reason: Error) => onError(reason.message));
  }, [open]);
  async function applyBatch() {
    if (!confirmed) return;
    setWorking(true);
    try {
      const result = await fetchJson<BatchPreview>("/api/batch", {method: "POST", headers: {"Content-Type": "application/json", "X-Curation-Token": token}, body: JSON.stringify({action: "apply", confirmed: true})});
      setPreview(await fetchJson<BatchPreview>("/api/batch-preview"));
      setConfirmed(false);
      await onChanged(`${result.batch?.merge_count.toLocaleString("es-AR") ?? 0} fusiones seguras aplicadas.`);
    } catch (reason) { onError((reason as Error).message); } finally { setWorking(false); }
  }
  async function undoBatch(batchId: string) {
    setWorking(true);
    try {
      const result = await fetchJson<{preview: BatchPreview}>("/api/batch", {method: "POST", headers: {"Content-Type": "application/json", "X-Curation-Token": token}, body: JSON.stringify({action: "undo", batch_id: batchId})});
      setPreview(result.preview);
      setConfirmed(false);
      await onChanged("Lote deshecho. Las decisiones manuales se conservaron.");
    } catch (reason) { onError((reason as Error).message); } finally { setWorking(false); }
  }
  return <dialog ref={dialogRef} className="merge-dialog batch-dialog" onClose={onClose} aria-labelledby="batch-title"><div className="batch-dialog__body"><div className="dialog-heading"><div><p className="eyebrow">Acción masiva reversible</p><h2 id="batch-title">Fusión segura por lote</h2></div><button type="button" onClick={() => dialogRef.current?.close()} aria-label="Cerrar"><X /></button></div>
    {!preview ? <div className="batch-loading" role="status">Calculando una vista previa segura…</div> : <>
      <p>Sólo incluye coincidencias con puntaje 100 y exactamente un documento consistente en todo el grupo.</p>
      <div className="batch-summary"><div><strong>{preview.merge_operations.toLocaleString("es-AR")}</strong><span>fusiones a escribir</span></div><div><strong>{preview.eligible_components.toLocaleString("es-AR")}</strong><span>grupos seguros</span></div><div><strong>{preview.eligible_identities.toLocaleString("es-AR")}</strong><span>identidades involucradas</span></div></div>
      <section className="batch-exclusions" aria-labelledby="exclusions-title"><h3 id="exclusions-title">Quedan fuera para revisión manual</h3><ul><li><strong>{preview.excluded_no_document_merges.toLocaleString("es-AR")}</strong> fusiones sin documento</li><li><strong>{preview.excluded_conflict_merges.toLocaleString("es-AR")}</strong> con documentos en conflicto</li><li><strong>{preview.excluded_curated_merges.toLocaleString("es-AR")}</strong> vinculadas a decisiones previas</li></ul></section>
      {preview.latest_batch && <div className="batch-active" role="status"><span><strong>Último lote aplicado</strong>{preview.latest_batch.merge_count.toLocaleString("es-AR")} fusiones · {formatDate(preview.latest_batch.created_at)}</span><button className="button button--secondary" type="button" disabled={working} onClick={() => undoBatch(preview.latest_batch!.batch_id)}><RotateCcw aria-hidden="true" />Deshacer este lote</button></div>}
      {preview.merge_operations > 0 ? <><label className="batch-confirm"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /><span>Entiendo que se escribirán <strong>{preview.merge_operations.toLocaleString("es-AR")} fusiones</strong> en el archivo de curación y que podré deshacer el lote completo.</span></label><div className="dialog-actions"><button type="button" className="button button--secondary" onClick={() => dialogRef.current?.close()}>Cancelar</button><button type="button" className="button button--primary" disabled={!confirmed || working} onClick={applyBatch}>{working ? "Aplicando…" : "Aplicar lote seguro"}</button></div></> : !preview.latest_batch && <div className="batch-active"><span><strong>No hay fusiones seguras pendientes.</strong>Las coincidencias restantes requieren revisión manual.</span></div>}
    </>}
  </div></dialog>;
}

function PersonCard({candidate, side, recommended}: {candidate: Candidate; side: "left" | "right"; recommended: boolean}) {
  const value = (suffix: string) => candidate[`${side}_${suffix}` as keyof Candidate] as string | number;
  return <article className={recommended ? "person-card person-card--recommended" : "person-card"}><div className="person-heading"><span>Variante {side === "left" ? "A" : "B"}</span>{recommended && <em><Check aria-hidden="true" />Canónica sugerida</em>}</div><h3>{value("name")}</h3><dl><div><dt>Documento</dt><dd>{value("document") || "Sin documento"}</dd></div><div><dt>Registros</dt><dd>{Number(value("records")).toLocaleString("es-AR")}</dd></div><div><dt>Primera aparición</dt><dd>{formatDate(String(value("first_seen")))}</dd></div><div><dt>Última aparición</dt><dd>{formatDate(String(value("last_seen")))}</dd></div><div><dt>Sedes</dt><dd>{locationLabel(String(value("locations")))}</dd></div></dl><code>{value("entity_id")}</code></article>;
}

function MergeDialog({candidate, token, onClose, onSaved, onError}: {candidate: Candidate | null; token: string; onClose: () => void; onSaved: () => Promise<void>; onError: (message: string) => void}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [canonical, setCanonical] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (candidate) {
      setCanonical(candidate.recommended_canonical_id);
      setNote("");
      dialogRef.current?.showModal();
    } else if (dialogRef.current?.open) dialogRef.current.close();
  }, [candidate]);
  if (!candidate) return <dialog ref={dialogRef} />;
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      await sendDecision(token, {candidate_id: candidate!.candidate_id, action: "merge", canonical_entity_id: canonical, confirmed: true, note});
      await onSaved();
    } catch (reason) {
      onError((reason as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return <dialog ref={dialogRef} className="merge-dialog" onClose={onClose}><form onSubmit={submit}><div className="dialog-heading"><div><p className="eyebrow">Confirmar unificación</p><h2>Elegí la identidad canónica</h2></div><button type="button" onClick={() => dialogRef.current?.close()} aria-label="Cerrar"><X /></button></div><p>Todos los registros seguirán disponibles, pero búsquedas, rankings y gráficos los tratarán como una sola persona.</p><fieldset><legend>Identidad que se conservará</legend><label><input type="radio" name="canonical" value={candidate.left_entity_id} checked={canonical === candidate.left_entity_id} onChange={(event) => setCanonical(event.target.value)} /><span><strong>{candidate.left_name}</strong><small>{candidate.left_document || "Sin documento"} · {candidate.left_records.toLocaleString("es-AR")} registros</small></span></label><label><input type="radio" name="canonical" value={candidate.right_entity_id} checked={canonical === candidate.right_entity_id} onChange={(event) => setCanonical(event.target.value)} /><span><strong>{candidate.right_name}</strong><small>{candidate.right_document || "Sin documento"} · {candidate.right_records.toLocaleString("es-AR")} registros</small></span></label></fieldset><label className="note-field"><span>Nota opcional</span><textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} rows={3} placeholder="Qué evidencia justifica esta decisión" /></label>{candidate.warnings.length > 0 && <div className="warning"><AlertTriangle aria-hidden="true" /><span><strong>Confirmación reforzada</strong>{candidate.warnings.map(reasonLabel).join(" · ")}</span></div>}<div className="dialog-actions"><button type="button" className="button button--secondary" onClick={() => dialogRef.current?.close()}>Cancelar</button><button type="submit" className="button button--primary" disabled={saving}>{saving ? "Guardando…" : "Confirmar unificación"}</button></div></form></dialog>;
}

function Metric({label, value, accent = false}: {label: string; value: number; accent?: boolean}) { return <div className={accent ? "metric metric--accent" : "metric"}><strong>{value.toLocaleString("es-AR")}</strong><span>{label}</span></div>; }
function StatusBadge({status}: {status: CandidateStatus}) { return <span className={`status status--${status}`}>{({pending: "Pendiente", merged: "Unificado", rejected: "Rechazado", deferred: "Pospuesto"})[status]}</span>; }
function CandidateSkeleton() { return <div className="skeletons" aria-label="Cargando candidatos">{Array.from({length: 7}, (_, index) => <span key={index} />)}</div>; }

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Error ${response.status}`);
  return payload as T;
}

async function sendDecision(token: string, payload: Record<string, unknown>) {
  return fetchJson<{candidate: Candidate}>("/api/decision", {method: "POST", headers: {"Content-Type": "application/json", "X-Curation-Token": token}, body: JSON.stringify(payload)});
}

function reasonLabel(reason: string) {
  const labels: Record<string, string> = {mismos_tokens: "Mismos nombres en distinto orden", nombre_o_apellido_adicional: "Una variante agrega un nombre o apellido", posible_error_tipografico: "Posible diferencia de escritura", iniciales_compatibles: "Iniciales compatibles", documento_solo_en_una_variante: "El documento aparece sólo en una variante", nombre_compartido_frecuente: "Es un nombre frecuente", nombre_asociado_a_documentos_distintos: "El nombre aparece asociado a documentos diferentes", confianza_de_revision: "El puntaje requiere revisión humana", nombre_frecuente: "Nombre frecuente", fusion_en_cadena: "La decisión se conecta con fusiones anteriores"};
  return labels[reason] ?? reason.replaceAll("_", " ");
}
function formatDate(value: string) { if (!value) return "Sin fecha"; return new Intl.DateTimeFormat("es-AR", {day: "2-digit", month: "short", year: "numeric", timeZone: "UTC"}).format(new Date(value)); }
function formatCount(value: number | undefined) { return value == null ? "—" : value.toLocaleString("es-AR"); }
function locationLabel(value: string) { return value.split("|").map((location) => location === "casa-rosada" ? "Casa Rosada" : location === "olivos" ? "Olivos" : location).join(" · "); }

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
