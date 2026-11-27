import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  Paper,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  Tooltip,
} from "@mantine/core";
import { IconArrowUp, IconFileText, IconPlayerStopFilled, IconSparkles } from "@tabler/icons-react";
import { Fragment, type ReactNode, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { type AiSource, streamEvents } from "./api";

interface Part {
  text: string;
  cites: number[];
}

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

export function sourceUrl(source: AiSource): string {
  const location = [source.library_id, source.folder_id].filter(Boolean).join("/");
  return `/documentos/${location}?doc=${encodeURIComponent(source.document_id)}&page=${source.page_from}`;
}

function pageLabel(s: AiSource) {
  return s.page_from === s.page_to ? `p. ${s.page_from}` : `pp. ${s.page_from}-${s.page_to}`;
}

/**
 * Pregunta a los documentos con respuesta en streaming y citas. Sin `documentIds`, busca en todos
 * los documentos que el usuario puede ver (o en la biblioteca indicada).
 */
export function AskPanel({
  documentIds,
  libraryId,
  placeholder = "Pregunta algo sobre tus documentos…",
  onOpenSource,
}: {
  documentIds?: string[];
  libraryId?: string | null;
  placeholder?: string;
  onOpenSource?: (source: AiSource) => void;
}) {
  const navigate = useNavigate();
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState<string | null>(null);
  const [parts, setParts] = useState<Part[]>([]);
  const [sources, setSources] = useState<AiSource[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const open = onOpenSource ?? ((s: AiSource) => navigate(sourceUrl(s)));

  const ask = async () => {
    const q = question.trim();
    if (q.length < 3 || streaming) return;
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setAsked(q);
    setQuestion("");
    setParts([{ text: "", cites: [] }]);
    setSources([]);
    setError(null);
    setStreaming(true);
    try {
      await streamEvents(
        "/api/v1/ai/ask",
        { question: q, library_id: libraryId ?? null, document_ids: documentIds ?? [] },
        (event) => {
          if (event.event === "sources") setSources(event.data.sources);
          else if (event.event === "text")
            setParts((current) => {
              const next = current.slice();
              const last = next[next.length - 1]!;
              next[next.length - 1] = { ...last, text: last.text + event.data.text };
              return next;
            });
          else if (event.event === "citation")
            setParts((current) => {
              const next = current.slice();
              const last = next[next.length - 1]!;
              if (!last.cites.includes(event.data.n))
                next[next.length - 1] = { ...last, cites: [...last.cites, event.data.n] };
              return next;
            });
          else if (event.event === "block_end")
            setParts((current) =>
              current[current.length - 1]!.text ? [...current, { text: "", cites: [] }] : current,
            );
          else if (event.event === "error") setError(event.data.message);
        },
        controller.signal,
      );
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError((e as Error).message);
    } finally {
      setStreaming(false);
    }
  };

  const bySource = new Map(sources.map((s) => [s.n, s]));
  const cited = new Set(parts.flatMap((p) => p.cites));
  const hasAnswer = parts.some((p) => p.text);

  return (
    <Stack>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void ask();
        }}
      >
        <Paper withBorder radius="lg" p={6} pl="md">
          <Group gap="xs" wrap="nowrap" align="flex-end">
            <Textarea
              variant="unstyled"
              autosize
              minRows={1}
              maxRows={6}
              style={{ flex: 1 }}
              placeholder={placeholder}
              aria-label="Pregunta"
              value={question}
              maxLength={1000}
              onChange={(e) => setQuestion(e.currentTarget.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void ask();
                }
              }}
            />
            {streaming ? (
              <ActionIcon
                size="lg"
                radius="xl"
                variant="light"
                aria-label="Detener"
                onClick={() => abort.current?.abort()}
              >
                <IconPlayerStopFilled size={16} />
              </ActionIcon>
            ) : (
              <ActionIcon
                size="lg"
                radius="xl"
                type="submit"
                aria-label="Preguntar"
                disabled={question.trim().length < 3}
              >
                <IconArrowUp size={18} />
              </ActionIcon>
            )}
          </Group>
        </Paper>
      </form>

      {asked && (
        <Stack gap="sm">
          <Text fw={600}>{asked}</Text>
          <Paper withBorder radius="md" p="md">
            <Group gap={6} mb="xs">
              <IconSparkles size={16} color="var(--mantine-color-violet-6)" />
              <Text size="xs" c="dimmed">
                Respuesta generada con IA a partir de tus documentos
              </Text>
              {streaming && <Loader size={12} />}
            </Group>
            {error && (
              <Alert color="red" variant="light" mb="sm">
                {error}
              </Alert>
            )}
            {!hasAnswer && streaming && (
              <Text size="sm" c="dimmed">
                Buscando en los documentos…
              </Text>
            )}
            <Text size="sm" style={{ whiteSpace: "pre-wrap", lineHeight: 1.65 }}>
              {parts.map((part, i) => (
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
                          onClick={() => source && open(source)}
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
          </Paper>
          {sources.length > 0 && (
            <>
              <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
                Fuentes
              </Text>
              <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
                {sources
                  .filter((s) => cited.size === 0 || cited.has(s.n))
                  .map((s) => (
                    <Card
                      key={s.n}
                      withBorder
                      radius="md"
                      padding="sm"
                      className="clickable-card"
                      onClick={() => open(s)}
                      role="button"
                      aria-label={`Abrir fuente ${s.n}: ${s.title}`}
                    >
                      <Group gap={6} wrap="nowrap" mb={4}>
                        <Badge size="sm" variant="light" style={{ flexShrink: 0 }}>
                          {s.n}
                        </Badge>
                        <IconFileText size={14} style={{ flexShrink: 0 }} />
                        <Text size="sm" fw={600} truncate="end">
                          {s.title}
                        </Text>
                        <Text size="xs" c="dimmed" style={{ flexShrink: 0 }}>
                          {pageLabel(s)}
                        </Text>
                      </Group>
                      <Text size="xs" c="dimmed" lineClamp={2}>
                        {s.snippet}
                      </Text>
                    </Card>
                  ))}
              </SimpleGrid>
            </>
          )}
          {!streaming && (
            <Group>
              <Button
                variant="subtle"
                size="xs"
                onClick={() => {
                  setAsked(null);
                  setParts([]);
                  setSources([]);
                }}
              >
                Nueva pregunta
              </Button>
            </Group>
          )}
        </Stack>
      )}
    </Stack>
  );
}
