import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./server";

// Las páginas se cargan de forma diferida (code splitting): bajo carga, 1 s por defecto es poco.
configure({ asyncUtilTimeout: 5000 });

// Polyfills que Mantine necesita en jsdom.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver;
window.HTMLElement.prototype.scrollIntoView = () => {};
URL.createObjectURL = () => "blob:mock";
URL.revokeObjectURL = () => {};
Object.defineProperty(document, "fonts", {
  value: { addEventListener: () => {}, removeEventListener: () => {}, ready: Promise.resolve() },
});

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
