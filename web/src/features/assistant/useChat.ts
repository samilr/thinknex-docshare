import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import {
  type AssistantDisplay,
  assistantKeys,
  type ChatMessage,
  type ChatSource,
  loadConversation,
  type Proposal,
  type ScreenContext,
  streamPost,
} from "./api";

const emptyDisplay = (): AssistantDisplay => ({
  parts: [{ text: "", cites: [] }],
  sources: [],
  steps: [],
  proposals: [],
});

let counter = 0;
const localId = () => `local-${++counter}`;

/** Estado de una conversación con el asistente: historial, envío y streaming de la respuesta. */
export function useChat(initialConversationId: string | null = null) {
  const queryClient = useQueryClient();
  const [conversationId, setConversationId] = useState<string | null>(initialConversationId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [loading, setLoading] = useState(false);
  const [thinking, setThinking] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  const updateLast = (fn: (d: AssistantDisplay) => AssistantDisplay) =>
    setMessages((current) => {
      const next = current.slice();
      const last = next[next.length - 1];
      if (last?.role === "assistant")
        next[next.length - 1] = { ...last, display: fn(last.display) };
      return next;
    });

  const open = useCallback(async (id: string | null) => {
    abort.current?.abort();
    setConversationId(id);
    setMessages([]);
    if (!id) return;
    setLoading(true);
    try {
      setMessages(await loadConversation(id));
    } finally {
      setLoading(false);
    }
  }, []);

  const send = useCallback(
    async (text: string, context?: ScreenContext) => {
      const message = text.trim();
      if (!message || streaming) return;
      const controller = new AbortController();
      abort.current = controller;
      setMessages((current) => [
        ...current,
        { id: localId(), role: "user", text: message },
        { id: localId(), role: "assistant", display: emptyDisplay(), streaming: true },
      ]);
      setStreaming(true);
      try {
        await streamPost(
          "/api/v1/ai/chat",
          {
            message,
            conversation_id: conversationId,
            context: context
              ? {
                  path: context.path ?? null,
                  document_id: context.document_id ?? null,
                  library_id: context.library_id ?? null,
                }
              : null,
          },
          ({ event, data }) => {
            if (event === "conversation") {
              setConversationId(String(data.id));
            } else if (event === "text") {
              setThinking(null);
              updateLast((d) => {
                const parts = d.parts.slice();
                const last = parts[parts.length - 1]!;
                parts[parts.length - 1] = { ...last, text: last.text + String(data.text) };
                return { ...d, parts };
              });
            } else if (event === "citation") {
              const source = data.source as ChatSource;
              updateLast((d) => {
                const parts = d.parts.slice();
                const last = parts[parts.length - 1]!;
                parts[parts.length - 1] = { ...last, cites: [...last.cites, source.n] };
                const sources = d.sources.some((s) => s.n === source.n)
                  ? d.sources
                  : [...d.sources, source];
                return { ...d, parts, sources };
              });
            } else if (event === "block_end") {
              updateLast((d) =>
                d.parts[d.parts.length - 1]!.text
                  ? { ...d, parts: [...d.parts, { text: "", cites: [] }] }
                  : d,
              );
            } else if (event === "thinking") {
              setThinking(String(data.tool));
            } else if (event === "step") {
              setThinking(null);
              updateLast((d) => ({ ...d, steps: [...d.steps, String(data.label)] }));
            } else if (event === "proposal") {
              updateLast((d) => ({
                ...d,
                proposals: [...d.proposals, data as unknown as Proposal],
              }));
            } else if (event === "error") {
              setMessages((current) => {
                const next = current.slice();
                const last = next[next.length - 1];
                if (last?.role === "assistant")
                  next[next.length - 1] = { ...last, error: String(data.message) };
                return next;
              });
            }
          },
          controller.signal,
        );
      } catch (e) {
        if ((e as Error).name !== "AbortError")
          setMessages((current) => {
            const next = current.slice();
            const last = next[next.length - 1];
            if (last?.role === "assistant")
              next[next.length - 1] = { ...last, error: (e as Error).message };
            return next;
          });
      } finally {
        setStreaming(false);
        setThinking(null);
        setMessages((current) =>
          current.map((m) =>
            m.role === "assistant" && m.streaming ? { ...m, streaming: false } : m,
          ),
        );
        void queryClient.invalidateQueries({ queryKey: assistantKeys.conversations });
      }
    },
    [conversationId, streaming, queryClient],
  );

  const markProposal = useCallback(
    (proposalId: string, status: Proposal["status"]) =>
      setMessages((current) =>
        current.map((m) =>
          m.role === "assistant"
            ? {
                ...m,
                display: {
                  ...m.display,
                  proposals: m.display.proposals.map((p) =>
                    p.id === proposalId ? { ...p, status } : p,
                  ),
                },
              }
            : m,
        ),
      ),
    [],
  );

  return {
    conversationId,
    messages,
    streaming,
    loading,
    thinking,
    send,
    open,
    stop: () => abort.current?.abort(),
    markProposal,
  };
}
