type Label = { label: string; color: string };

export const SHARE_STATUS: Record<string, Label> = {
  ACTIVE: { label: "Activo", color: "green" },
  REVOKED: { label: "Revocado", color: "gray" },
  EXPIRED: { label: "Vencido", color: "yellow" },
  LOCKED: { label: "Bloqueado", color: "red" },
  EXHAUSTED: { label: "Agotado", color: "blue" },
};

export const CLASSIFICATION: Record<string, Label> = {
  PUBLIC: { label: "Pública", color: "teal" },
  INTERNAL: { label: "Interna", color: "blue" },
  CONFIDENTIAL: { label: "Confidencial", color: "orange" },
  RESTRICTED: { label: "Restringida", color: "red" },
};

export const DECISION: Record<string, Label> = {
  ALLOW: { label: "Permitido", color: "green" },
  WARN: { label: "Requiere confirmación", color: "yellow" },
  BLOCK: { label: "Bloqueado por política", color: "red" },
};

export const CHANNEL: Record<string, Label> = {
  LINK: { label: "Enlace ThinkNex Docs", color: "violet" },
  EMAIL: { label: "Email", color: "indigo" },
  WHATSAPP: { label: "WhatsApp", color: "green" },
  SMS: { label: "SMS", color: "cyan" },
};

export const PERMISSION: Record<string, Label> = {
  VIEW: { label: "Solo ver", color: "gray" },
  DOWNLOAD: { label: "Ver y descargar", color: "blue" },
  EDIT: { label: "Editar", color: "grape" },
};

export const AUDIENCE: Record<string, Label> = {
  SPECIFIC: { label: "Persona específica", color: "teal" },
  ANYONE: { label: "Cualquiera con el enlace", color: "orange" },
};

export const ROLE: Record<string, Label> = {
  ADMIN: { label: "Administrador", color: "grape" },
  SHARER: { label: "Emisor", color: "blue" },
  AUDITOR: { label: "Auditor", color: "teal" },
};

export const FINDING: Record<string, string> = {
  RUT: "RUT",
  EMAIL: "Correo electrónico",
  PHONE: "Teléfono",
  CARD: "Tarjeta de pago",
  BANK_ACCOUNT: "Cuenta bancaria",
};

export const EVENT: Record<string, string> = {
  SENSITIVITY_CHECKED: "Sensibilidad evaluada",
  SHARE_BLOCKED: "Intento bloqueado",
  SHARE_CREATED: "Documento compartido",
  NOTIFICATION_SENT: "Notificación enviada",
  NOTIFICATION_FAILED: "Notificación fallida",
  LINK_OPENED: "Enlace abierto",
  OTP_SENT: "Código enviado",
  OTP_VERIFIED: "Código verificado",
  OTP_FAILED: "Código incorrecto",
  DOCUMENT_ACCESSED: "Documento descargado",
  ACCESS_GRANTED: "Enlace abierto sin código",
  SHARE_LINK_ROTATED: "Enlace regenerado",
  ACCESS_DENIED: "Acceso denegado",
  SHARE_REVOKED: "Share revocado",
  SHARE_EXPIRED: "Share vencido",
  SHARE_LOCKED: "Share bloqueado",
  SNAPSHOT_PURGED: "Copia eliminada (retención)",
  USER_LOGIN: "Inicio de sesión",
  USER_LOGIN_FAILED: "Inicio de sesión fallido",
  USER_LOCKED: "Usuario bloqueado",
  USER_LOGOUT: "Cierre de sesión",
  USER_CREATED: "Usuario creado",
  USER_UPDATED: "Usuario modificado",
  USER_DISABLED: "Usuario desactivado",
  USER_ENABLED: "Usuario activado",
  PASSWORD_CHANGED: "Contraseña cambiada",
  PASSWORD_RESET: "Contraseña reiniciada",
  TOKEN_REUSE_DETECTED: "Reutilización de sesión detectada",
  IMPERSONATION_STARTED: "Inicio de actuación como usuario",
  IMPERSONATION_ENDED: "Fin de actuación como usuario",
  DOCUMENT_UPLOADED: "Archivo subido",
  DOCUMENT_VERSION_UPLOADED: "Nueva versión subida",
  DOCUMENT_RENAMED: "Archivo renombrado",
  DOCUMENT_RECLASSIFIED: "Archivo reclasificado",
  DOCUMENT_DELETED: "Archivo eliminado",
  POLICY_CREATED: "Regla de política creada",
  POLICY_UPDATED: "Regla de política modificada",
  POLICY_DELETED: "Regla de política eliminada",
  DOCUMENT_VIEWED: "Documento visualizado",
  FOLDER_CREATED: "Carpeta creada",
};

export const EVENT_COLOR: Record<string, string> = {
  SHARE_BLOCKED: "red",
  ACCESS_DENIED: "red",
  OTP_FAILED: "orange",
  USER_LOGIN_FAILED: "orange",
  USER_LOCKED: "red",
  TOKEN_REUSE_DETECTED: "red",
  IMPERSONATION_STARTED: "orange",
  IMPERSONATION_ENDED: "orange",
  SHARE_REVOKED: "gray",
  DOCUMENT_ACCESSED: "green",
  SHARE_CREATED: "blue",
  DOCUMENT_UPLOADED: "teal",
  DOCUMENT_VERSION_UPLOADED: "teal",
  DOCUMENT_RENAMED: "violet",
  DOCUMENT_RECLASSIFIED: "orange",
  DOCUMENT_DELETED: "red",
  POLICY_CREATED: "grape",
  POLICY_UPDATED: "grape",
  POLICY_DELETED: "red",
  DOCUMENT_VIEWED: "gray",
  ACCESS_GRANTED: "green",
  SHARE_LINK_ROTATED: "yellow",
};

export const labelOf = (map: Record<string, Label>, key: string): Label =>
  map[key] ?? { label: key, color: "gray" };
