import { useQuery } from "@tanstack/react-query";
import {
  api,
  getAccessToken,
  type Problem,
  problemMessage,
  refreshSession,
  unwrap,
} from "../../api/client";

export interface ChatSource {
  n: number;
  document_id: string;
  title: string;
  library_id: string | null;
  folder_id: string | null;
  page_from: number;
  page_to: number;
}

export interface Proposal {
  id: string;
  kind: "share" | "revoke" | "update_share";
  summary: string;
  data: Record<string, unknown>;
  status?: "confirmed" | "dismissed" | "failed";
}

export interface AssistantDisplay {
  parts: { text: string; cites: number[] }[];
  sources: ChatSource[];
  steps: string[];
  proposals: Proposal[];
}

export type ChatMessage =
  | { id: string; role: "user"; text: string }
  | {
      id: string;
      role: "assistant";
      display: AssistantDisplay;
      streaming?: boolean;
      error?: string;
    };

export interface ScreenContext {
  path?: string;
  document_id?: string;
  library_id?: string;
  document_title?: string;
}

export const assistantKeys = {
  conversations: ["assistant", "conversations"] as const,
  conversation: (id: string) => ["assistant", "conversation", id] as const,
};

export function useConversations(enabled = true) {
  return useQuery({
    queryKey: assistantKeys.conversations,
    enabled,
    queryFn: async () => unwrap(await api.GET("/api/v1/ai/conversations")),
  });
}

export async function loadConversation(id: string): Promise<ChatMessage[]> {
  const detail = unwrap(
    await api.GET("/api/v1/ai/conversations/{conversation_id}", {
      params: { path: { conversation_id: id } },
    }),
  );
  return detail.messages.map((m) =>
    m.role === "user"
      ? { id: String(m.id), role: "user", text: String(m.display.text ?? "") }
      : { id: String(m.id), role: "assistant", display: m.display as unknown as AssistantDisplay },
  );
}

export async function deleteConversation(id: string): Promise<void> {
  await api.DELETE("/api/v1/ai/conversations/{conversation_id}", {
    params: { path: { conversation_id: id } },
  });
}

export async function reportOutcome(
  conversationId: string,
  proposalId: string,
  status: "confirmed" | "dismissed" | "failed",
  summary: string,
): Promise<void> {
  await api.POST("/api/v1/ai/conversations/{conversation_id}/proposals/{proposal_id}", {
    params: { path: { conversation_id: conversationId, proposal_id: proposalId } },
    body: { status, summary },
  });
}

export interface ServerEvent {
  event: string;
  data: Record<string, unknown>;
}

/** POST con respuesta Server-Sent Events: llama a `onEvent` por cada evento recibido. */
export async function streamPost(
  path: string,
  body: unknown,
  onEvent: (event: ServerEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
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
  if (!response.ok || !response.body) {
    const problem = (await response.json().catch(() => undefined)) as Problem | undefined;
    throw new Error(problemMessage(problem, "No fue posible contactar al asistente"));
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
      if (data) onEvent({ event: name, data: JSON.parse(data) as Record<string, unknown> });
    }
  }
}
