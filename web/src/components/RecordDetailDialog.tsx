import {Check, Copy, ExternalLink, X} from "lucide-react";
import {useEffect, useMemo, useRef, useState} from "react";
import type {AccessEvent, AudienciaDetail} from "../types";
import {copyText} from "../utils/clipboard";
import {locationLabel, titleCase} from "./SearchResults";

const DATE_FORMATTER = new Intl.DateTimeFormat("es-AR", {day: "numeric", month: "numeric", year: "numeric"});
const TIME_FORMATTER = new Intl.DateTimeFormat("es-AR", {hour: "2-digit", minute: "2-digit"});

type RecordDetailDialogProps = {
  event: AccessEvent;
  onClose: () => void;
};

export function RecordDetailDialog({event, onClose}: RecordDetailDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const copiedTimer = useRef<number | null>(null);
  const [copyStatus, setCopyStatus] = useState<"copied" | "error" | null>(null);
  const citation = useMemo(() => buildRecordCitation(event), [event]);
  const source = event.sources?.[0];
  const audiencias = event.audiencia ? [event.audiencia] : event.fused_audiencias ?? [];

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    return () => {
      if (copiedTimer.current !== null) window.clearTimeout(copiedTimer.current);
      if (dialog.open && typeof dialog.close === "function") dialog.close();
    };
  }, []);

  async function copyCitation() {
    try {
      await copyText(citation);
      setCopyStatus("copied");
    } catch {
      setCopyStatus("error");
    }
    if (copiedTimer.current !== null) window.clearTimeout(copiedTimer.current);
    copiedTimer.current = window.setTimeout(() => setCopyStatus(null), 2_000);
  }

  return <dialog ref={dialogRef} className="record-detail-dialog" aria-labelledby="record-detail-title" onCancel={(browserEvent) => { browserEvent.preventDefault(); onClose(); }} onClick={(browserEvent) => { if (browserEvent.target === browserEvent.currentTarget) onClose(); }}>
    <article>
      <header className="record-detail-header">
        <div><p className="eyebrow">Registro público</p><h2 id="record-detail-title">Detalle para citar</h2></div>
        <button className="record-detail-close" type="button" onClick={onClose} aria-label="Cerrar detalle"><X aria-hidden="true" /></button>
      </header>

      <p className="record-detail-lead">Podés copiar este registro tal como figura en la base o hacer una captura de esta ventana.</p>

      <dl className="record-detail-fields">
        <DetailRow label={event.audiencia ? "Audiencia" : recordLabel(event)} value={visitDescription(event)} />
        <DetailRow label="Lugar" value={placeDescription(event)} />
        <DetailRow label="Persona" value={titleCase(event.canonical_name)} />
        <DetailRow label="Documento" value={documentDescription(event)} />
        <DetailRow label="Motivo" value={event.purpose} />
        <DetailRow label="Actividad" value={event.activity} />
        <DetailRow label="Dirección" value={event.direction} />
        <DetailRow label="Dispositivo" value={event.device} />
        <DetailRow label="Autorizó" value={event.authorized_by} />
        <DetailRow label="Estado" value={event.access_status} />
        <DetailRow label="Observaciones" value={event.raw_text} wide />
      </dl>

      {audiencias.length > 0 && <div className="record-detail-audiencias">
        <strong>Cruce con el Registro de Audiencias</strong>
        {audiencias.map((item) => <div className="record-detail-audiencia" key={item.audiencia_id}>
          <p><strong>{titleCase(item.official_name)}</strong>{(item.official_cargo || item.lugar) && <> · {item.official_cargo || item.lugar}</>}</p>
          <p><strong>{audienciaStatusLabel(item.status)}.</strong> <span>{audienciaStatusExplanation(item.status)}</span></p>
        </div>)}
      </div>}

      <div className="record-detail-source">
        <strong>Fuente</strong>
        {source ? <><p>{sourceDescription(event)}</p>{isPublicUrl(source.url) ? <a href={`${source.url}#page=${source.page}`} target="_blank" rel="noreferrer">Ver PDF, página {source.page}<ExternalLink aria-hidden="true" /></a> : <small>{source.path} · página {source.page}</small>}</> : event.audiencia ? <p>Registro de Audiencias de Gestión de Intereses, publicado por el Poder Ejecutivo Nacional.</p> : null}
      </div>

      <footer className="record-detail-actions">
        <span role={copyStatus === "error" ? "alert" : "status"} aria-live="polite">{copyStatus === "copied" ? "Detalle copiado al portapapeles." : copyStatus === "error" ? "No se pudo copiar. Seleccioná el texto e intentá nuevamente." : ""}</span>
        <button className="record-detail-copy" type="button" onClick={copyCitation} autoFocus>{copyStatus === "copied" ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}{copyStatus === "copied" ? "Copiado" : "Copiar detalle"}</button>
      </footer>
    </article>
  </dialog>;
}

function DetailRow({label, value, wide = false}: {label: string; value: string | null; wide?: boolean}) {
  if (!value?.trim()) return null;
  return <div className={wide ? "record-detail-field--wide" : undefined}><dt>{label}</dt><dd>{value}</dd></div>;
}

export function buildRecordCitation(event: AccessEvent) {
  const source = event.sources?.[0];
  const audiencias = event.audiencia ? [event.audiencia] : event.fused_audiencias ?? [];
  const lines = [
    `${event.audiencia ? "Audiencia" : recordLabel(event)}: ${visitDescription(event)}`,
    `Lugar: ${placeDescription(event)}`,
    `Persona: ${titleCase(event.canonical_name)}`,
    event.document_number ? `Documento: ${documentDescription(event)}` : null,
    event.purpose ? `Motivo: ${event.purpose}` : null,
    event.activity ? `Actividad: ${event.activity}` : null,
    event.authorized_by ? `Autorizó: ${event.authorized_by}` : null,
    event.access_status ? `Estado: ${event.access_status}` : null,
    event.raw_text?.trim() ? `Observaciones: ${event.raw_text.trim()}` : null,
    ...audiencias.map((item) => `${audienciaStatusLabel(item.status)}: ${titleCase(item.official_name)}${item.official_cargo ? `, ${item.official_cargo}` : ""}${item.lugar ? ` (${item.lugar})` : ""}`),
    `Fuente: ${source ? sourceDescription(event) : "Registro de Audiencias de Gestión de Intereses"}`,
    source ? `Archivo: ${source.path}, página ${source.page}${isPublicUrl(source.url) ? ` — ${source.url}#page=${source.page}` : ""}` : null,
  ];
  return lines.filter(Boolean).join("\n");
}

function visitDescription(event: AccessEvent) {
  const date = primaryDate(event);
  if (!date) return "Sin fecha informada";
  const parts = [formatDate(date)];
  if (event.entered_at && event.exited_at) parts.push(`de ${formatTime(event.entered_at)} a ${formatTime(event.exited_at)}`);
  else if (event.entered_at) parts.push(`a las ${formatTime(event.entered_at)}`);
  else if (event.exited_at) parts.push(`salida a las ${formatTime(event.exited_at)}`);
  else if (event.occurred_at) parts.push(`a las ${formatTime(event.occurred_at)}`);
  return parts.join(" ");
}

function placeDescription(event: AccessEvent) {
  return [locationLabel(event.location), event.destination].filter(Boolean).join(" · ");
}

function documentDescription(event: AccessEvent) {
  return event.document_number ? `${event.document_type ?? "Documento"} ${event.document_number}` : "No informado";
}

function sourceDescription(event: AccessEvent) {
  const date = primaryDate(event);
  const year = date && !Number.isNaN(new Date(date).getTime()) ? new Date(date).getFullYear() : null;
  return `Accesos a ${locationLabel(event.location)}${year ? ` ${year}` : ""}, respuesta oficial a un pedido de acceso a la información realizado por Poder Ciudadano.`;
}

function audienciaStatusLabel(status: AudienciaDetail["status"]) {
  if (status === "confirmed") return "Audiencia confirmada en Casa Rosada";
  if (status === "likely") return "Audiencia probable en Casa Rosada";
  return "Audiencia en el registro, sin cruce con accesos";
}

function audienciaStatusExplanation(status: AudienciaDetail["status"]) {
  if (status === "confirmed") return "La misma persona ingresó a Casa Rosada el mismo día de esta audiencia, por lo que se confirma que se realizó allí.";
  if (status === "likely") return "El funcionario o el lugar de esta audiencia aparece confirmado en Casa Rosada en otros casos, por lo que es probable que también se haya realizado allí.";
  return "Figura en el Registro de Audiencias de Gestión de Intereses, pero no se pudo cruzar con un ingreso registrado a Casa Rosada.";
}

function primaryDate(event: AccessEvent) { return event.occurred_at ?? event.entered_at ?? event.exited_at; }
function formatDate(value: string) { return DATE_FORMATTER.format(new Date(value)); }
function formatTime(value: string) { return TIME_FORMATTER.format(new Date(value)); }
function recordLabel(event: AccessEvent) { if (event.record_type === "movement") return "Movimiento"; if (event.record_type === "vehicle") return "Vehículo"; return "Visita"; }
function isPublicUrl(value: string) { return /^https?:\/\//i.test(value); }
