export function eventSummary(event: {
  event_type: string;
  metadata: Record<string, unknown>;
}): string {
  const m = event.metadata;
  if (event.event_type === "DOCUMENT_RENAMED") {
    return `«${String(m.from_filename ?? m.from_title)}» → «${String(m.to_filename ?? m.to_title)}»`;
  }
  if (event.event_type.startsWith("IMPERSONATION_")) {
    return `Como ${String(m.target_email)}`;
  }
  if (event.event_type === "DOCUMENT_RECLASSIFIED") {
    return `${String(m.from_classification)} → ${String(m.to_classification)}`;
  }
  if (event.event_type === "DOCUMENT_DELETED") {
    const revoked = Number(m.revoked_shares ?? 0);
    return `«${String(m.filename)}»${revoked ? ` · ${revoked} envío(s) revocado(s)` : ""}`;
  }
  if (event.event_type.startsWith("POLICY_")) {
    const name = (m.name ?? (m.after as Record<string, unknown> | undefined)?.name) as string;
    const changed = Array.isArray(m.changed) ? ` (${(m.changed as string[]).join(", ")})` : "";
    return `«${name}»${changed}`;
  }
  if (event.event_type === "DOCUMENT_VERSION_UPLOADED" && m.version) {
    return `Versión ${String(m.version)}${m.comment ? `: ${String(m.comment)}` : ""}`;
  }
  return String(m.reason ?? m.decision ?? m.destination ?? "");
}
