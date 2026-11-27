import { useQuery } from "@tanstack/react-query";
import {
  api,
  getAccessToken,
  type Problem,
  problemMessage,
  refreshSession,
  type Schemas,
  unwrap,
} from "../../api/client";

export type AiSource = Schemas["SourceOut"];

export function useAiStatus() {
  return useQuery({
    queryKey: ["ai", "status"],
    staleTime: 5 * 60_000,
    queryFn: async () => unwrap(await api.GET("/api/v1/ai/status")),
  });
}

export type AskEvent =
  | { event: "sources"; data: { sources: AiSource[] } }
  | { event: "text"; data: { text: string } }
  | { event: "citation"; data: { n: number; document_id: string; page_from: number } }
  | { event: "block_end"; data: Record<string, never> }
  | { event: "done"; data: { usage: { model: string } | null } }
  | { event: "error"; data: { message: string } };

async function post(path: string, body: unknown, signal?: AbortSignal): Promise<Response> {
  const send = () =>
    fetch(`${window.location.origin}${path}`, {
      method: "POST",
      credentials: "same-origin",
      signal,
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "fetch",
        ...(getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {}),
      },
      body: JSON.stringify(body),
    });
  let response = await send();
  if (response.status === 401 && (await refreshSession())) response = await send();
  return response;
}

/** POST con respuesta en streaming (Server-Sent Events): llama a `onEvent` por cada evento. */
export async function streamEvents(
  path: string,
  body: unknown,
  onEvent: (event: AskEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await post(path, body, signal);
  if (!response.ok || !response.body) {
    const problem = (await response.json().catch(() => undefined)) as Problem | undefined;
    throw new Error(problemMessage(problem, "No fue posible consultar a la IA"));
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      let name = "message";
      let data = "";
      for (const line of chunk.split("\n")) {
        if (line.startsWith("event: ")) name = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (data) onEvent({ event: name, data: JSON.parse(data) } as AskEvent);
    }
  }
}
