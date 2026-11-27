import {
  ActionIcon,
  Affix,
  Drawer,
  Group,
  Text,
  ThemeIcon,
  Tooltip,
  Transition,
} from "@mantine/core";
import { IconArrowsMaximize, IconMessagePlus, IconSparkles } from "@tabler/icons-react";
import { type ReactNode, useCallback, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { api, type Schemas, unwrap } from "../../api/client";
import { useAuth } from "../../auth/context";
import { useAiStatus } from "../ai/api";
import { type ShareFormValues, ShareWizard } from "../share/ShareWizard";
import type { Proposal, ScreenContext } from "./api";
import { ChatView } from "./ChatView";
import { AssistantContext, type OpenAssistantOptions } from "./context";
import { useChat } from "./useChat";

const EXPIRY = ["24", "72", "168"];

function wizardValues(data: Record<string, unknown>): Partial<ShareFormValues> {
  const recipient = (data.recipient ?? null) as {
    name?: string;
    email?: string | null;
    phone?: string | null;
  } | null;
  const hours = Number(data.expires_in_hours) || 72;
  return {
    channel: data.channel as ShareFormValues["channel"],
    audience: data.audience as ShareFormValues["audience"],
    permission: data.permission as ShareFormValues["permission"],
    reason: String(data.reason ?? ""),
    name: recipient?.name ?? "",
    email: recipient?.email ?? "",
    phone: recipient?.phone ?? "",
    codeVia: recipient?.email ? "EMAIL" : recipient?.phone ? "SMS" : "EMAIL",
    expires: EXPIRY.find((h) => Number(h) >= hours) ?? "168",
    ...(data.max_accesses ? { maxAccesses: Number(data.max_accesses) } : {}),
  };
}

/**
 * Asistente disponible en todo el portal: botón flotante, panel lateral con el chat y el
 * asistente de compartir para revisar y confirmar las propuestas.
 */
export function AssistantProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const status = useAiStatus();
  const location = useLocation();
  const navigate = useNavigate();
  const available = !!user && status.data?.llm === true;
  const chat = useChat();
  const [opened, setOpened] = useState(false);
  const [docContext, setDocContext] = useState<OpenAssistantOptions | null>(null);
  const [sharing, setSharing] = useState<{
    proposal: Proposal;
    document: Schemas["SourceDocument"];
  } | null>(null);
  const onShareDone = useRef<((ok: boolean, summary: string) => void) | null>(null);
  const sharedRef = useRef(false);

  const libraryFromPath = location.pathname.startsWith("/documentos/")
    ? location.pathname.split("/")[2]
    : undefined;
  const context: ScreenContext = {
    path: location.pathname,
    library_id: docContext?.libraryId ?? libraryFromPath,
    document_id: docContext?.documentId,
    document_title: docContext?.documentTitle,
  };

  const openAssistant = useCallback(
    (options?: OpenAssistantOptions) => {
      if (options?.documentId) {
        setDocContext(options);
        void chat.open(null);
      }
      setOpened(true);
      if (options?.prompt) {
        void chat.send(options.prompt, {
          path: location.pathname,
          document_id: options.documentId,
          library_id: options.libraryId,
        });
      }
    },
    [chat, location.pathname],
  );

  const reviewShare = useCallback(
    (proposal: Proposal, onDone: (ok: boolean, summary: string) => void) => {
      onShareDone.current = onDone;
      sharedRef.current = false;
      void api
        .GET("/api/v1/library/documents/{doc_id}", {
          params: { path: { doc_id: String(proposal.data.document_id) } },
        })
        .then((r) => setSharing({ proposal, document: unwrap(r).document }));
    },
    [],
  );

  const value = useMemo(
    () => ({ available, openAssistant, reviewShare }),
    [available, openAssistant, reviewShare],
  );
  const onAssistantPage = location.pathname.startsWith("/asistente");

  return (
    <AssistantContext.Provider value={value}>
      {children}
      {available && (
        <>
          <Affix position={{ bottom: 24, right: 24 }} zIndex={300}>
            <Transition transition="pop" mounted={!opened && !onAssistantPage}>
              {(styles) => (
                <Tooltip label="Asistente" position="left" withArrow>
                  <ActionIcon
                    style={{ ...styles, boxShadow: "var(--mantine-shadow-lg)" }}
                    size={56}
                    radius="xl"
                    variant="gradient"
                    gradient={{ from: "violet", to: "blue", deg: 135 }}
                    aria-label="Abrir asistente"
                    onClick={() => openAssistant()}
                  >
                    <IconSparkles size={26} />
                  </ActionIcon>
                </Tooltip>
              )}
            </Transition>
          </Affix>
          <Drawer
            opened={opened}
            onClose={() => setOpened(false)}
            position="right"
            size={460}
            zIndex={350}
            padding={0}
            withOverlay={false}
            lockScroll={false}
            shadow="xl"
            styles={{
              content: { display: "flex", flexDirection: "column" },
              body: { flex: 1, minHeight: 0, display: "flex", flexDirection: "column" },
            }}
            title={
              <Group gap="xs">
                <ThemeIcon variant="light" color="violet" radius="xl" size="md">
                  <IconSparkles size={16} />
                </ThemeIcon>
                <Text fw={700}>Asistente</Text>
              </Group>
            }
          >
            <Group gap={4} px="md" pb={6} justify="flex-end">
              <Tooltip label="Nueva conversación">
                <ActionIcon
                  variant="subtle"
                  color="gray"
                  aria-label="Nueva conversación"
                  onClick={() => {
                    setDocContext(null);
                    void chat.open(null);
                  }}
                >
                  <IconMessagePlus size={18} />
                </ActionIcon>
              </Tooltip>
              <Tooltip label="Abrir en pantalla completa">
                <ActionIcon
                  variant="subtle"
                  color="gray"
                  aria-label="Abrir en pantalla completa"
                  onClick={() => {
                    setOpened(false);
                    navigate(
                      chat.conversationId ? `/asistente?c=${chat.conversationId}` : "/asistente",
                    );
                  }}
                >
                  <IconArrowsMaximize size={18} />
                </ActionIcon>
              </Tooltip>
            </Group>
            <div style={{ flex: 1, minHeight: 0 }}>
              <ChatView chat={chat} context={context} />
            </div>
          </Drawer>
        </>
      )}
      {sharing && (
        <ShareWizard
          key={sharing.proposal.id}
          document={sharing.document}
          opened
          initial={wizardValues(sharing.proposal.data)}
          onShared={(share) => {
            sharedRef.current = true;
            onShareDone.current?.(true, `Compartido (envío ${share.id})`);
          }}
          onClose={() => {
            if (!sharedRef.current) onShareDone.current?.(false, "El usuario no completó el envío");
            setSharing(null);
          }}
        />
      )}
    </AssistantContext.Provider>
  );
}
