/**
 * Recuperación ante despliegues nuevos.
 *
 * Cada build genera nombres de archivo con hash. Si una pestaña quedó abierta con la versión
 * anterior, al navegar pide un chunk que ya no existe (404) y la carga diferida falla. La solución
 * estándar es recargar UNA vez para obtener el index.html vigente (que se sirve sin caché).
 * Se guarda una marca de tiempo en sessionStorage para no entrar en un bucle de recargas.
 */

const KEY = "thinknex:chunk-reload-at";
const WINDOW_MS = 10_000;

const CHUNK_ERROR =
  /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|Unable to preload CSS/i;

export function isChunkLoadError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error ?? "");
  return CHUNK_ERROR.test(message);
}

/** Recarga la página si no se recargó hace poco. Devuelve true si va a recargar. */
export function reloadOnceForNewVersion(storage: Storage = window.sessionStorage): boolean {
  const last = Number(storage.getItem(KEY) ?? 0);
  if (Date.now() - last < WINDOW_MS) return false;
  storage.setItem(KEY, String(Date.now()));
  window.location.reload();
  return true;
}

/** Vite emite `vite:preloadError` cuando falla la precarga de un chunk. */
export function installStaleChunkRecovery(): void {
  window.addEventListener("vite:preloadError", (event) => {
    if (reloadOnceForNewVersion()) event.preventDefault();
  });
}
