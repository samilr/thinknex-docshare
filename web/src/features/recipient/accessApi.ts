/**
 * Cliente de la API pública del destinatario (/api/v1/access/{token}).
 *
 * Es independiente del cliente interno: no envía cookies ni la sesión de un usuario de la
 * organización. La sesión de acceso (JWT de 30 min ligado al envío) vive solo en memoria.
 */
import type { Problem, Schemas } from "../../api/client";
import { problemMessage } from "../../api/client";

export type AccessInfo = Schemas["AccessInfoOut"];
export type AccessSession = Schemas["AccessSessionOut"];
export type DocumentView = Schemas["DocumentViewOut"];
export type VersionPublished = Schemas["VersionPublishedOut"];

/** Error de la API con el status HTTP y el problema (RFC 7807) para decidir qué mostrar. */
export class AccessError extends Error {
  constructor(
    readonly status: number,
    readonly problem: Problem | undefined,
  ) {
    super(problemMessage(problem, status === 404 ? "Enlace no disponible" : undefined));
  }
  /** 404 uniforme: el enlace no existe, venció, se revocó, se bloqueó o la sesión terminó. */
  get unavailable(): boolean {
    return this.status === 404;
  }
}

const base = (token: string) =>
  `${window.location.origin}/api/v1/access/${encodeURIComponent(token)}`;

async function call(
  token: string,
  path: string,
  init: RequestInit & { session?: string } = {},
): Promise<Response> {
  const { session, headers, ...rest } = init;
  const response = await fetch(`${base(token)}${path}`, {
    ...rest,
    credentials: "omit",
    cache: "no-store",
    referrerPolicy: "no-referrer",
    headers: { ...(session ? { Authorization: `Bearer ${session}` } : {}), ...headers },
  });
  if (!response.ok) {
    const problem = (await response.json().catch(() => undefined)) as Problem | undefined;
    throw new AccessError(response.status, problem);
  }
  return response;
}

const json = async <T>(response: Promise<Response>): Promise<T> => (await response).json() as T;

export const accessApi = {
  info: (token: string) => json<AccessInfo>(call(token, "")),
  requestCode: (token: string) =>
    json<Schemas["OtpSentResponse"]>(call(token, "/otp", { method: "POST" })),
  verify: (token: string, code: string) =>
    json<AccessSession>(
      call(token, "/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      }),
    ),
  open: (token: string) => json<AccessSession>(call(token, "/open", { method: "POST" })),
  document: (token: string, session: string) =>
    json<DocumentView>(call(token, "/document", { session })),
  page: async (token: string, session: string, n: number) =>
    (await call(token, `/pages/${n}`, { session })).blob(),
  text: async (token: string, session: string) => (await call(token, "/text", { session })).text(),
  download: async (token: string, session: string) => {
    const response = await call(token, "/download", { session });
    const disposition = response.headers.get("Content-Disposition") ?? "";
    const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "documento";
    return { blob: await response.blob(), filename };
  },
  uploadVersion: (token: string, session: string, file: File, comment: string) => {
    const form = new FormData();
    form.append("file", file);
    if (comment.trim()) form.append("comment", comment.trim());
    return json<VersionPublished>(
      call(token, "/versions", { method: "POST", session, body: form }),
    );
  },
};

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = Object.assign(document.createElement("a"), { href: url, download: filename });
  anchor.click();
  URL.revokeObjectURL(url);
}
