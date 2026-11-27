import { describe, expect, it, vi } from "vitest";
import { isChunkLoadError, reloadOnceForNewVersion } from "./staleChunks";

describe("recuperación ante versiones nuevas", () => {
  it("reconoce errores de carga de chunks", () => {
    expect(
      isChunkLoadError(
        new TypeError(
          "Failed to fetch dynamically imported module: https://x/assets/ExplorerPage-abc.js",
        ),
      ),
    ).toBe(true);
    expect(isChunkLoadError(new Error("Importing a module script failed."))).toBe(true);
    expect(isChunkLoadError(new Error("Cannot read properties of undefined"))).toBe(false);
  });

  it("recarga solo una vez dentro de la ventana de protección", () => {
    const reload = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...window.location, reload },
    });
    const storage = window.sessionStorage;
    storage.clear();
    expect(reloadOnceForNewVersion(storage)).toBe(true);
    expect(reloadOnceForNewVersion(storage)).toBe(false);
    expect(reload).toHaveBeenCalledTimes(1);
  });
});
