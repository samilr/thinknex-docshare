import {
  ActionIcon,
  Alert,
  Box,
  Button,
  Center,
  Group,
  Loader,
  Modal,
  Paper,
  Skeleton,
  Stack,
  Text,
  Textarea,
  ThemeIcon,
  Title,
  Tooltip,
  UnstyledButton,
} from "@mantine/core";
import { Dropzone } from "@mantine/dropzone";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  IconDownload,
  IconFileText,
  IconFileUpload,
  IconUpload,
  IconZoomIn,
  IconZoomOut,
} from "@tabler/icons-react";
import { type ReactNode, useEffect, useState } from "react";
import { PermissionBadge, WatermarkBadge } from "../../components/badges";
import { FINDING } from "../../lib/labels";
import { ACCEPT, formatBytes, MAX_UPLOAD_BYTES } from "../library/files";
import {
  AccessError,
  type AccessSession,
  accessApi,
  type DocumentView,
  saveBlob,
} from "./accessApi";

const ZOOM_STEPS = [50, 75, 100, 125, 150, 200];
const PAGE_WIDTH = 860;
const blockCopy = {
  onContextMenu: (e: React.MouseEvent) => e.preventDefault(),
  onDragStart: (e: React.DragEvent) => e.preventDefault(),
  style: { userSelect: "none" as const, WebkitUserSelect: "none" as const },
};

function ProtectedPage({
  token,
  session,
  version,
  number,
  zoom,
}: {
  token: string;
  session: string;
  version: number;
  number: number;
  zoom: number;
}) {
  const page = useQuery({
    queryKey: ["access", token, "page", version, number, session],
    queryFn: async () => URL.createObjectURL(await accessApi.page(token, session, number)),
    gcTime: 0,
    staleTime: Infinity,
    retry: false,
  });
  const url = page.data;
  useEffect(() => () => (url ? URL.revokeObjectURL(url) : undefined), [url]);

  return (
    <Paper
      shadow="md"
      radius={2}
      mx="auto"
      data-page={number}
      w={zoom <= 100 ? `min(100%, ${(PAGE_WIDTH * zoom) / 100}px)` : (PAGE_WIDTH * zoom) / 100}
      bg="white"
      {...blockCopy}
      style={{ ...blockCopy.style, overflow: "hidden" }}
    >
      {url ? (
        <img
          src={url}
          alt={`Página ${number}`}
          draggable={false}
          style={{ display: "block", width: "100%", height: "auto", pointerEvents: "none" }}
        />
      ) : page.isError ? (
        <Center h={240}>
          <Text c="red" size="sm">
            No se pudo cargar la página {number}
          </Text>
        </Center>
      ) : (
        <Skeleton h={(PAGE_WIDTH * zoom * 1.3) / 100} radius={0} />
      )}
    </Paper>
  );
}

function TextContent({
  token,
  session,
  version,
}: {
  token: string;
  session: string;
  version: number;
}) {
  const text = useQuery({
    queryKey: ["access", token, "text", version, session],
    queryFn: () => accessApi.text(token, session),
    gcTime: 0,
  });
  if (text.isPending) return <Loader />;
  if (text.isError) return <Alert color="red">{text.error.message}</Alert>;
  return (
    <Paper withBorder p="lg" {...blockCopy}>
      <Text component="pre" ff="monospace" size="sm" style={{ whiteSpace: "pre-wrap", margin: 0 }}>
        {text.data}
      </Text>
    </Paper>
  );
}

function UploadVersionModal({
  opened,
  onClose,
  token,
  session,
  view,
}: {
  opened: boolean;
  onClose: () => void;
  token: string;
  session: string;
  view: DocumentView;
}) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [comment, setComment] = useState("");
  const [rejected, setRejected] = useState<string | null>(null);
  const upload = useMutation({
    mutationFn: () => accessApi.uploadVersion(token, session, file!, comment),
    onSuccess: (result) => {
      notifications.show({
        color: "green",
        message: `Versión ${result.version} publicada.`,
      });
      if (result.findings.length > 0) {
        notifications.show({
          color: "orange",
          message: `La versión contiene datos personales: ${result.findings
            .map((f) => FINDING[f.type] ?? f.type)
            .join(", ")}.`,
        });
      }
      void queryClient.invalidateQueries({ queryKey: ["access", token, "document"] });
      setFile(null);
      setComment("");
      onClose();
    },
  });

  return (
    <Modal opened={opened} onClose={onClose} title={<Text fw={700}>Subir nueva versión</Text>}>
      <Stack>
        <Text size="sm" c="dimmed">
          Se publicará como versión {view.version + 1}.
        </Text>
        <Dropzone
          onDrop={(files) => {
            setFile(files[0] ?? null);
            setRejected(null);
          }}
          onReject={() => setRejected("Tipo de archivo no permitido o supera los 20 MB")}
          accept={ACCEPT}
          maxSize={MAX_UPLOAD_BYTES}
          multiple={false}
        >
          <Group justify="center" gap="sm" mih={90} style={{ pointerEvents: "none" }}>
            <IconFileUpload size={32} color="var(--mantine-color-blue-6)" />
            <div>
              <Text size="sm" fw={500}>
                {file ? file.name : "Arrastra el archivo o haz clic para elegirlo"}
              </Text>
              <Text size="xs" c="dimmed">
                {file ? formatBytes(file.size) : "PDF, imagen, texto, Word o Excel · hasta 20 MB"}
              </Text>
            </div>
          </Group>
        </Dropzone>
        {rejected && <Alert color="red">{rejected}</Alert>}
        {upload.error && <Alert color="red">{upload.error.message}</Alert>}
        <Textarea
          label="Comentario de la versión"
          placeholder="Qué cambió"
          maxLength={500}
          value={comment}
          onChange={(e) => setComment(e.currentTarget.value)}
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            leftSection={<IconUpload size={16} />}
            disabled={!file}
            loading={upload.isPending}
            onClick={() => upload.mutate()}
          >
            Publicar versión
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

export function DocumentViewer({
  token,
  session,
  onEnded,
}: {
  token: string;
  session: AccessSession;
  onEnded: () => void;
}) {
  const access = session.access_token;
  const [zoom, setZoom] = useState(100);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [current, setCurrent] = useState(1);
  const view = useQuery({
    queryKey: ["access", token, "document", access],
    queryFn: () => accessApi.document(token, access),
    retry: false,
  });
  const download = useMutation({
    mutationFn: () => accessApi.download(token, access),
    onSuccess: ({ blob, filename }) => saveBlob(blob, filename),
    onError: (e) => notifications.show({ color: "red", message: e.message }),
  });

  const pageCount = view.data?.page_count ?? 0;
  useEffect(() => {
    if (!pageCount || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible) setCurrent(Number((visible.target as HTMLElement).dataset.page));
      },
      { threshold: [0.25, 0.5, 0.75] },
    );
    document.querySelectorAll("[data-page]").forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [pageCount, zoom]);

  const shell = (content: ReactNode) => (
    <Box mih="100vh" bg="var(--viewer-bg)">
      {content}
    </Box>
  );

  if (view.isPending) {
    return shell(
      <Center mih="100vh">
        <Loader />
      </Center>,
    );
  }
  if (view.isError) {
    const ended = view.error instanceof AccessError && view.error.unavailable;
    return shell(
      <Center mih="100vh" p="md">
        <Paper withBorder p="xl" radius="md" maw={420} w="100%">
          <Stack align="flex-start" gap="sm">
            <Title order={4}>{ended ? "Tu sesión terminó" : "No se pudo abrir el documento"}</Title>
            <Text size="sm" c="dimmed">
              {ended ? "Vuelve a abrir el enlace para continuar." : view.error.message}
            </Text>
            <Button variant="light" onClick={onEnded}>
              Volver a abrir
            </Button>
          </Stack>
        </Paper>
      </Center>,
    );
  }

  const doc = view.data;
  const zoomIndex = ZOOM_STEPS.indexOf(zoom);
  const paged = doc.kind === "pdf" || doc.kind === "image";

  return shell(
    <>
      <Box
        component="header"
        pos="sticky"
        top={0}
        px="md"
        bg="var(--mantine-color-body)"
        style={{ zIndex: 10, borderBottom: "1px solid var(--mantine-color-default-border)" }}
      >
        <Group justify="space-between" wrap="nowrap" h={60} gap="md">
          <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
            <ThemeIcon variant="filled" radius="md" size="lg">
              <IconFileText size={20} />
            </ThemeIcon>
            <Stack gap={0} style={{ minWidth: 0 }}>
              <Text fw={600} truncate="end">
                {doc.title}
              </Text>
              <Text size="xs" c="dimmed" truncate="end">
                ThinkNex Docs · v{doc.version}
                {doc.live ? " vigente" : ""} · {doc.viewer_label}
              </Text>
            </Stack>
            <Group gap={6} wrap="nowrap" style={{ flexShrink: 0 }}>
              <PermissionBadge value={doc.permission} />
              <WatermarkBadge value={doc.watermark} />
            </Group>
          </Group>
          <Group gap="xs" wrap="nowrap">
            {paged && (
              <Group gap={4} wrap="nowrap" visibleFrom="xs">
                <Text size="sm" c="dimmed" miw={56} ta="center" aria-live="polite">
                  {current} / {doc.page_count}
                </Text>
                <Tooltip label="Alejar">
                  <ActionIcon
                    variant="subtle"
                    color="gray"
                    aria-label="Alejar"
                    disabled={zoomIndex <= 0}
                    onClick={() => setZoom(ZOOM_STEPS[zoomIndex - 1]!)}
                  >
                    <IconZoomOut size={18} />
                  </ActionIcon>
                </Tooltip>
                <UnstyledButton onClick={() => setZoom(100)} aria-label="Ajustar al ancho">
                  <Text size="sm" w={48} ta="center">
                    {zoom}%
                  </Text>
                </UnstyledButton>
                <Tooltip label="Acercar">
                  <ActionIcon
                    variant="subtle"
                    color="gray"
                    aria-label="Acercar"
                    disabled={zoomIndex >= ZOOM_STEPS.length - 1}
                    onClick={() => setZoom(ZOOM_STEPS[zoomIndex + 1]!)}
                  >
                    <IconZoomIn size={18} />
                  </ActionIcon>
                </Tooltip>
              </Group>
            )}
            {doc.can_download && (
              <Button
                variant="default"
                leftSection={<IconDownload size={16} />}
                loading={download.isPending}
                onClick={() => download.mutate()}
              >
                Descargar
              </Button>
            )}
            {doc.can_edit && (
              <Button leftSection={<IconUpload size={16} />} onClick={() => setUploadOpen(true)}>
                Subir versión
              </Button>
            )}
          </Group>
        </Group>
      </Box>

      <Box py="xl" px="md" style={{ overflowX: "auto" }}>
        {paged ? (
          <Stack gap="lg">
            {Array.from({ length: doc.page_count }, (_, i) => (
              <ProtectedPage
                key={i}
                token={token}
                session={access}
                version={doc.version}
                number={i + 1}
                zoom={zoom}
              />
            ))}
          </Stack>
        ) : doc.kind === "text" ? (
          <Box maw={PAGE_WIDTH} mx="auto">
            <TextContent token={token} session={access} version={doc.version} />
          </Box>
        ) : (
          <Paper withBorder p="xl" radius="md" maw={480} mx="auto" ta="center">
            <Text fw={600}>Vista previa no disponible</Text>
            <Text size="sm" c="dimmed" mt={4}>
              Este tipo de archivo no se puede mostrar en el visor.
            </Text>
          </Paper>
        )}
        <Text ta="center" size="xs" c="dimmed" mt="xl">
          Prototipo de prueba técnica · datos ficticios · no es un servicio oficial de ThinkNex.
        </Text>
      </Box>

      {doc.can_edit && (
        <UploadVersionModal
          opened={uploadOpen}
          onClose={() => setUploadOpen(false)}
          token={token}
          session={access}
          view={doc}
        />
      )}
    </>,
  );
}
