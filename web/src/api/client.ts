/**
 * Cliente HTTP tipado (generado desde el OpenAPI de share-api).
 *
 * Seguridad de la sesión:
 * - El access token vive SOLO en memoria (nunca en localStorage).
 * - El refresh token es una cookie httpOnly que JavaScript no puede leer.
 * - Ante un 401 se intenta UNA renovación (single-flight) y se reintenta la solicitud.
 */
import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type Session = Schemas["SessionOut"];
export type Me = Schemas["MeOut"];

type Listener = (session: Session | null) => void;

let accessToken: string | null = null;
let refreshing: Promise<Session | null> | null = null;
const listeners = new Set<Listener>();

const origin = () => (typeof window === "undefined" ? "" : window.location.origin);
const NO_RETRY = ["/api/v1/auth/login", "/api/v1/auth/refresh", "/api/v1/auth/token"];

export function onSessionChange(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function setSession(session: Session | null): void {
  accessToken = session?.access_token ?? null;
  listeners.forEach((listener) => listener(session));
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function refreshSession(): Promise<Session | null> {
  refreshing ??= fetch(`${origin()}/api/v1/auth/refresh`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-Requested-With": "fetch" },
  })
    .then(async (response) => (response.ok ? ((await response.json()) as Session) : null))
    .catch(() => null)
    .then((session) => {
      setSession(session);
      return session;
    })
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

function withAuth(request: Request): Request {
  if (accessToken) request.headers.set("Authorization", `Bearer ${accessToken}`);
  request.headers.set("X-Requested-With", "fetch");
  return request;
}

async function authFetch(input: Request): Promise<Response> {
  const retry = input.clone();
  const response = await fetch(withAuth(input));
  const path = new URL(input.url).pathname;
  if (response.status !== 401 || NO_RETRY.includes(path)) return response;
  const session = await refreshSession();
  return session ? fetch(withAuth(retry)) : response;
}

export const api = createClient<paths>({
  baseUrl: origin(),
  fetch: authFetch,
  credentials: "same-origin",
});

/** Respuesta de error de la API (RFC 7807 o validación de FastAPI). */
export interface Problem {
  title?: string;
  detail?: string | { msg: string; loc?: (string | number)[] }[];
  status?: number;
  report?: Schemas["SensitivityReport"];
  remaining_attempts?: number;
}

export function problemMessage(error: unknown, fallback = "Ocurrió un error inesperado"): string {
  const problem = error as Problem | undefined;
  if (!problem) return fallback;
  if (Array.isArray(problem.detail)) {
    return problem.detail.map((d) => d.msg.replace(/^Value error, /, "")).join(". ");
  }
  return problem.detail ?? problem.title ?? fallback;
}

/** Lanza un Error legible si la llamada de openapi-fetch falló (útil con TanStack Query). */
export function unwrap<T>(result: { data?: T; error?: unknown }): T {
  if (result.error !== undefined || result.data === undefined) {
    throw Object.assign(new Error(problemMessage(result.error)), { problem: result.error });
  }
  return result.data;
}
