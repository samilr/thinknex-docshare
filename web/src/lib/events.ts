/** Resumen legible del detalle de un evento de auditoría (columna "Detalle" y actividad). */
export function eventSummary(event: {
  event_type: string;
  metadata: Record<string, unknown>;
}): string {
  const m = event.metadata;
  if (event.event_type === "DOCUMENT_RENAMED") {
    return `«${String(m.from_filename ?? m.from_title)}» → «${String(m.to_filename ?? m.to_title)}»`;
  }
  if (event.event_type === "DOCUMENT_VERSION_UPLOADED" && m.version) {
    return `Versión ${String(m.version)}${m.comment ? `: ${String(m.comment)}` : ""}`;
  }
  return String(m.reason ?? m.decision ?? m.destination ?? "");
}
