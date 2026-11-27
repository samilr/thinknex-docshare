const KEY = "thinknex:chunk-reload-at";
const WINDOW_MS = 10_000;

const CHUNK_ERROR =
  /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|Unable to preload CSS/i;

export function isChunkLoadError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error ?? "");
  return CHUNK_ERROR.test(message);
}

export function reloadOnceForNewVersion(storage: Storage = window.sessionStorage): boolean {
  const last = Number(storage.getItem(KEY) ?? 0);
  if (Date.now() - last < WINDOW_MS) return false;
  storage.setItem(KEY, String(Date.now()));
  window.location.reload();
  return true;
}

export function installStaleChunkRecovery(): void {
  window.addEventListener("vite:preloadError", (event) => {
    if (reloadOnceForNewVersion()) event.preventDefault();
  });
}
