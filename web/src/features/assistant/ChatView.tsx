import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Box,
  Button,
  Card,
  Center,
  Group,
  Loader,
  Paper,
  ScrollArea,
  Stack,
  Text,
  Textarea,
  ThemeIcon,
  Tooltip,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useQueryClient } from "@tanstack/react-query";
import {
  IconArrowUp,
  IconCheck,
  IconFileText,
  IconListCheck,
  IconPlayerStopFilled,
  IconSparkles,
  IconX,
} from "@tabler/icons-react";
import { Fragment, type ReactNode, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { api, problemMessage } from "../../api/client";
import { useAuth } from "../../auth/context";
import {
  type AssistantDisplay,
  type ChatSource,
  type Proposal,
  reportOutcome,
  type ScreenContext,
} from "./api";
import { useAssistant } from "./context";
import { sourceUrl, suggestionsFor } from "./helpers";
import type { useChat } from "./useChat";

type Chat = ReturnType<typeof useChat>;

const TOOL_LABEL: Record<string, string> = {
  buscar_documentos: "Buscando en los documentos…",
  leer_documento: "Leyendo el documento…",
  listar_documentos: "Revisando la biblioteca…",
  ver_documento: "Consultando el documento…",
  listar_envios: "Revisando los envíos…",
  revisar_politica: "Revisando la política…",
  consultar_auditoria: "Consultando la auditoría…",
};

function inline(text: string): ReactNode[] {
  const normalized = text.replace(/^(\s*)[-*] /gm, "$1• ");
  return normalized
    .split(/(\*\*[^*]+\*\*)/g)
    .map((piece, i) =>
      piece.startsWith("**") && piece.endsWith("**") ? (
        <b key={i}>{piece.slice(2, -2)}</b>
      ) : (
        <Fragment key={i}>{piece}</Fragment>
      ),
    );
}

const pageLabel = (s: ChatSource) =>
  s.page_from === s.page_to ? `p. ${s.page_from}` : `pp. ${s.page_from}-${s.page_to}`;

function ProposalCard({ proposal, chat }: { proposal: Proposal; chat: Chat }) {
  const queryClient = useQueryClient();
  const { reviewShare } = useAssistant();
  const [busy, setBusy] = useState(false);
  const done = proposal.status;

  const finish = async (status: "confirmed" | "dismissed" | "failed", summary: string) => {
    chat.markProposal(proposal.id, status);
    if (chat.conversationId)
      await reportOutcome(chat.conversationId, proposal.id, status, summary).catch(() => undefined);
  };

  const confirm = async () => {
    if (proposal.kind === "share") {
      reviewShare(proposal, (ok, summary) => void finish(ok ? "confirmed" : "dismissed", summary));
      return;
    }
    setBusy(true);
    const shareId = String(proposal.data.share_id);
    const { error } =
      proposal.kind === "revoke"
        ? await api.POST("/api/v1/shares/{share_id}/revoke", {
            params: { path: { share_id: shareId } },
          })
        : await api.PATCH("/api/v1/shares/{share_id}", {
            params: { path: { share_id: shareId } },
            body: proposal.data.changes as Record<string, unknown>,
          });
    setBusy(false);
    if (error) {
      const message = problemMessage(error);
      notifications.show({ color: "red", message });
      await finish("failed", message);
      return;
    }
    notifications.show({ color: "green", message: "Listo. El cambio quedó registrado." });
    void queryClient.invalidateQueries({ queryKey: ["shares"] });
    await finish("confirmed", proposal.summary);
  };

  return (
    <Card withBorder radius="md" padding="sm" bg="var(--mantine-color-default-hover)">
      <Group gap={6} mb={6} wrap="nowrap">
        <IconListCheck size={16} color="var(--mantine-color-violet-6)" style={{ flexShrink: 0 }} />
        <Text size="xs" c="dimmed" fw={600} tt="uppercase">
          Propuesta para confirmar
        </Text>
      </Group>
      <Text size="sm" mb="sm">
        {proposal.summary}
      </Text>
      {done ? (
        <Badge
          color={done === "confirmed" ? "green" : done === "failed" ? "red" : "gray"}
          variant="light"
          leftSection={done === "confirmed" ? <IconCheck size={12} /> : <IconX size={12} />}
        >
          {done === "confirmed"
            ? "Confirmada"
            : done === "failed"
              ? "No se pudo aplicar"
              : "Descartada"}
        </Badge>
      ) : (
        <Group gap="xs">
          <Button size="xs" loading={busy} onClick={() => void confirm()}>
            {proposal.kind === "share"
              ? "Revisar y compartir"
              : proposal.kind === "revoke"
                ? "Revocar"
                : "Aplicar cambio"}
          </Button>
          <Button
            size="xs"
            variant="default"
            onClick={() => void finish("dismissed", proposal.summary)}
          >
            Descartar
          </Button>
        </Group>
      )}
    </Card>
  );
}

function AssistantMessage({
  display,
  chat,
  streaming,
  error,
  thinking,
  onOpenSource,
}: {
  display: AssistantDisplay;
  chat: Chat;
  streaming?: boolean;
  error?: string;
  thinking: string | null;
  onOpenSource: (s: ChatSource) => void;
}) {
  const bySource = new Map(display.sources.map((s) => [s.n, s]));
  const hasText = display.parts.some((p) => p.text);
  return (
    <Group align="flex-start" gap="sm" wrap="nowrap">
      <ThemeIcon variant="light" color="violet" radius="xl" size="md" style={{ flexShrink: 0 }}>
        <IconSparkles size={16} />
      </ThemeIcon>
      <Stack gap="xs" style={{ minWidth: 0, flex: 1 }}>
        {display.steps.length > 0 && (
          <Group gap={4}>
            {display.steps.map((step, i) => (
              <Badge key={i} size="xs" variant="outline" color="gray" tt="none" fw={500}>
                {step}
              </Badge>
            ))}
          </Group>
        )}
        {streaming && !hasText && (
          <Group gap={6}>
            <Loader size={12} type="dots" />
            <Text size="sm" c="dimmed">
              {(thinking && TOOL_LABEL[thinking]) ?? "Pensando…"}
            </Text>
          </Group>
        )}
        {hasText && (
          <Text size="sm" style={{ whiteSpace: "pre-wrap", lineHeight: 1.65 }}>
            {display.parts.map((part, i) => (
              <Fragment key={i}>
                {inline(part.text)}
                {part.cites.map((n) => {
                  const source = bySource.get(n);
                  return (
                    <Tooltip
                      key={n}
                      label={source ? `${source.title} · ${pageLabel(source)}` : `Fuente ${n}`}
                      withArrow
                    >
                      <Anchor
                        component="button"
                        type="button"
                        size="xs"
                        fw={700}
                        mx={2}
                        aria-label={`Fuente ${n}`}
                        onClick={() => source && onOpenSource(source)}
                        style={{ verticalAlign: "super" }}
                      >
                        [{n}]
                      </Anchor>
                    </Tooltip>
                  );
                })}
              </Fragment>
            ))}
          </Text>
        )}
        {error && (
          <Alert color="red" variant="light" py={6}>
            {error}
          </Alert>
        )}
        {display.sources.length > 0 && (
          <Group gap={6}>
            {display.sources.map((s) => (
              <Button
                key={s.n}
                size="compact-xs"
                variant="light"
                color="gray"
                leftSection={<IconFileText size={12} />}
                onClick={() => onOpenSource(s)}
                aria-label={`Abrir fuente ${s.n}: ${s.title}`}
                styles={{ label: { maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis" } }}
              >
                {s.n}. {s.title} · {pageLabel(s)}
              </Button>
            ))}
          </Group>
        )}
        {display.proposals.map((p) => (
          <ProposalCard key={p.id} proposal={p} chat={chat} />
        ))}
      </Stack>
    </Group>
  );
}

/** Chat con el asistente: mensajes, citas, pasos, propuestas y caja de texto. */
export function ChatView({
  chat,
  context,
  emptyTitle = "¿En qué te ayudo?",
  onNavigate,
}: {
  chat: Chat;
  context: ScreenContext;
  emptyTitle?: string;
  onNavigate?: () => void;
}) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const viewport = useRef<HTMLDivElement>(null);
  const suggestions = suggestionsFor(context, user?.roles ?? []);

  useEffect(() => {
    const el = viewport.current;
    if (el && typeof el.scrollTo === "function") {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
  }, [chat.messages]);

  const submit = (value: string) => {
    if (!value.trim() || chat.streaming) return;
    setText("");
    void chat.send(value, context);
  };
  const openSource = (s: ChatSource) => {
    onNavigate?.();
    navigate(sourceUrl(s));
  };

  return (
    <Stack h="100%" gap={0}>
      <ScrollArea style={{ flex: 1 }} viewportRef={viewport} type="auto" offsetScrollbars>
        {chat.loading ? (
          <Center py="xl">
            <Loader />
          </Center>
        ) : chat.messages.length === 0 ? (
          <Stack align="center" gap="md" py="xl" px="md">
            <ThemeIcon size={48} radius="xl" variant="light" color="violet">
              <IconSparkles size={26} />
            </ThemeIcon>
            <Text fw={600} size="lg" ta="center">
              {emptyTitle}
            </Text>
            {context.document_title && (
              <Badge variant="light" leftSection={<IconFileText size={12} />} tt="none">
                {context.document_title}
              </Badge>
            )}
            <Stack gap={6} w="100%" maw={420}>
              {suggestions.map((s) => (
                <Button
                  key={s}
                  variant="default"
                  radius="xl"
                  fw={400}
                  justify="flex-start"
                  onClick={() => submit(s)}
                >
                  {s}
                </Button>
              ))}
            </Stack>
          </Stack>
        ) : (
          <Stack gap="lg" p="md">
            {chat.messages.map((m, i) =>
              m.role === "user" ? (
                <Group key={m.id} justify="flex-end">
                  <Paper
                    radius="lg"
                    px="md"
                    py="xs"
                    maw="85%"
                    bg="var(--mantine-color-default-hover)"
                  >
                    <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>
                      {m.text}
                    </Text>
                  </Paper>
                </Group>
              ) : (
                <AssistantMessage
                  key={m.id}
                  display={m.display}
                  chat={chat}
                  streaming={m.streaming}
                  error={m.error}
                  thinking={i === chat.messages.length - 1 ? chat.thinking : null}
                  onOpenSource={openSource}
                />
              ),
            )}
          </Stack>
        )}
      </ScrollArea>
      <Box p="sm" pt={6}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit(text);
          }}
        >
          <Paper withBorder radius="xl" p={6} pl="md">
            <Group gap="xs" wrap="nowrap" align="flex-end">
              <Textarea
                variant="unstyled"
                autosize
                minRows={1}
                maxRows={6}
                style={{ flex: 1 }}
                placeholder="Escribe tu mensaje…"
                aria-label="Mensaje para el asistente"
                value={text}
                maxLength={4000}
                onChange={(e) => setText(e.currentTarget.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    submit(text);
                  }
                }}
              />
              {chat.streaming ? (
                <ActionIcon
                  size="lg"
                  radius="xl"
                  variant="light"
                  aria-label="Detener"
                  onClick={chat.stop}
                >
                  <IconPlayerStopFilled size={16} />
                </ActionIcon>
              ) : (
                <ActionIcon
                  size="lg"
                  radius="xl"
                  type="submit"
                  aria-label="Enviar"
                  disabled={!text.trim()}
                >
                  <IconArrowUp size={18} />
                </ActionIcon>
              )}
            </Group>
          </Paper>
        </form>
        <Text size="10px" c="dimmed" ta="center" mt={4}>
          La IA puede equivocarse. Revisa las fuentes citadas.
        </Text>
      </Box>
    </Stack>
  );
}
