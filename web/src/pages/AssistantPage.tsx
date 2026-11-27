import {
  ActionIcon,
  Alert,
  Box,
  Button,
  Group,
  NavLink,
  Paper,
  ScrollArea,
  Stack,
  Text,
  Tooltip,
} from "@mantine/core";
import { modals } from "@mantine/modals";
import { useQueryClient } from "@tanstack/react-query";
import { IconMessagePlus, IconTrash } from "@tabler/icons-react";
import { useEffect } from "react";
import { useLocation, useSearchParams } from "react-router";
import { useAiStatus } from "../features/ai/api";
import { assistantKeys, deleteConversation, useConversations } from "../features/assistant/api";
import { ChatView } from "../features/assistant/ChatView";
import { useChat } from "../features/assistant/useChat";
import { formatRelative } from "../lib/format";

/** Asistente a pantalla completa: conversaciones guardadas a la izquierda y el chat al centro. */
export function AssistantPage() {
  const status = useAiStatus();
  const location = useLocation();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const selected = params.get("c");
  const conversations = useConversations(status.data?.llm === true);
  const chat = useChat();
  const { open, conversationId } = chat;

  useEffect(() => {
    if (selected !== conversationId) void open(selected);
    // Solo al cambiar la conversación elegida en la URL.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  useEffect(() => {
    if (conversationId && conversationId !== selected)
      setParams({ c: conversationId }, { replace: true });
    // La URL sigue a la conversación nueva cuando el servidor la crea.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  if (status.data && !status.data.llm) {
    return <Alert color="gray">La IA no está disponible en este entorno.</Alert>;
  }

  return (
    <Group
      align="stretch"
      gap="md"
      wrap="nowrap"
      h="calc(100dvh - 60px - 2 * var(--mantine-spacing-lg))"
    >
      <Paper
        withBorder
        radius="md"
        w={270}
        p="xs"
        visibleFrom="sm"
        style={{ display: "flex", flexDirection: "column" }}
      >
        <Button
          leftSection={<IconMessagePlus size={16} />}
          variant="light"
          mb="xs"
          onClick={() => setParams({})}
        >
          Nueva conversación
        </Button>
        <ScrollArea style={{ flex: 1 }}>
          <Stack gap={2}>
            {conversations.data?.length === 0 && (
              <Text size="sm" c="dimmed" ta="center" py="md">
                Sin conversaciones
              </Text>
            )}
            {conversations.data?.map((c) => (
              <NavLink
                key={c.id}
                active={c.id === selected}
                label={
                  <Text size="sm" truncate="end">
                    {c.title}
                  </Text>
                }
                description={formatRelative(c.updated_at)}
                onClick={() => setParams({ c: c.id })}
                style={{ borderRadius: 8 }}
                rightSection={
                  <Tooltip label="Eliminar">
                    <ActionIcon
                      size="sm"
                      variant="subtle"
                      color="gray"
                      aria-label={`Eliminar ${c.title}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        modals.openConfirmModal({
                          title: "Eliminar conversación",
                          children: <Text size="sm">¿Eliminar «{c.title}»?</Text>,
                          labels: { confirm: "Eliminar", cancel: "Cancelar" },
                          confirmProps: { color: "red" },
                          onConfirm: () =>
                            void deleteConversation(c.id).then(() => {
                              void queryClient.invalidateQueries({
                                queryKey: assistantKeys.conversations,
                              });
                              if (c.id === selected) setParams({});
                            }),
                        });
                      }}
                    >
                      <IconTrash size={14} />
                    </ActionIcon>
                  </Tooltip>
                }
              />
            ))}
          </Stack>
        </ScrollArea>
      </Paper>
      <Paper
        withBorder
        radius="md"
        style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}
      >
        <Box maw={860} w="100%" mx="auto" style={{ flex: 1, minHeight: 0 }}>
          <ChatView key={selected ?? "new"} chat={chat} context={{ path: location.pathname }} />
        </Box>
      </Paper>
    </Group>
  );
}
