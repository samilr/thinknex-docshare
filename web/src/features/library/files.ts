export function fileKind(mime: string): "pdf" | "image" | "text" | "word" | "excel" | "other" {
  if (mime === "application/pdf") return "pdf";
  if (mime.startsWith("image/")) return "image";
  if (mime === "text/plain") return "text";
  if (mime.includes("wordprocessingml")) return "word";
  if (mime.includes("spreadsheetml")) return "excel";
  return "other";
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Tipos aceptados al subir (deben coincidir con la validación del sistema documental). */
export const ACCEPT = {
  "application/pdf": [".pdf"],
  "image/png": [".png"],
  "image/jpeg": [".jpg", ".jpeg"],
  "text/plain": [".txt"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
};
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
