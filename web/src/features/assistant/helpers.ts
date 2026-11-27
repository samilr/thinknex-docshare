import type { ChatSource, ScreenContext } from "./api";

export function sourceUrl(s: ChatSource): string {
  const location = [s.library_id, s.folder_id].filter(Boolean).join("/");
  return `/documentos/${location}?doc=${encodeURIComponent(s.document_id)}&page=${s.page_from}`;
}

export function suggestionsFor(context: ScreenContext, roles: string[]): string[] {
  const library = roles.includes("SHARER") || roles.includes("ADMIN");
  const oversight = roles.includes("ADMIN") || roles.includes("AUDITOR");
  if (context.document_id && library)
    return [
      "Resume este documento",
      "¿Tiene datos personales o sensibles?",
      "¿Con quién lo he compartido?",
      "Prepara un enlace de solo lectura para compartirlo",
    ];
  const path = context.path ?? "/";
  if (path.startsWith("/envios"))
    return [
      "¿Cuáles de mis envíos siguen activos?",
      "¿Qué envíos vencen en los próximos días?",
      "¿Algún envío quedó bloqueado o agotado?",
    ];
  if (path.startsWith("/auditoria") && oversight)
    return [
      "¿Hubo intentos bloqueados o accesos denegados esta semana?",
      "Resume la actividad de hoy",
      "¿Se cambió alguna política recientemente?",
    ];
  if (path.startsWith("/documentos") && library)
    return [
      "¿Qué documentos hay en esta biblioteca?",
      "Busca contratos que tengan datos personales",
      "¿Cuál es el informe trimestral más reciente?",
    ];
  if (!library && oversight)
    return [
      "Resume la actividad reciente de la auditoría",
      "¿Qué envíos externos se hicieron esta semana?",
      "¿Hubo bloqueos de política?",
    ];
  return [
    "¿Qué puedes hacer por mí?",
    "Resume mis envíos activos",
    "¿Qué planes ofrece el catálogo de productos 2026?",
  ];
}
