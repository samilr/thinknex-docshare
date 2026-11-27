import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Center,
  Group,
  Loader,
  Modal,
  Paper,
  ScrollArea,
  Skeleton,
  Stack,
  Text,
  Textarea,
  Title,
  Tooltip,
} from "@mantine/core";
import { Dropzone } from "@mantine/dropzone";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  IconDownload,
  IconEyeOff,
  IconFileUpload,
  IconUpload,
  IconZoomIn,
  IconZoomOut,
} from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { PermissionBadge } from "../../components/badges";
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
    gcTime: 0, // la URL se libera al desmontar: no se reutiliza desde la caché
    staleTime: Infinity,
    retry: false,
  });
  const url = page.data;
  useEffect(() => () => (url ? URL.revokeObjectURL(url) : undefined), [url]);

  return (
    <Paper
      shadow="sm"
      withBorder
      mx="auto"
      w={`${zoom}%`}
      maw={zoom > 100 ? "none" : 900}
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
        <Skeleton h={600} radius={0} />
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
        message: `Versión ${result.version} publicada. Quien te compartió el archivo ya la ve.`,
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
          Se publicará como versión {view.version + 1} de “{view.title}” en la biblioteca de quien
          te lo compartió. Queda registrado a tu nombre.
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

  if (view.isPending) {
    return (
      <Center py="xl">
        <Loader />
      </Center>
    );
  }
  if (view.isError) {
    const ended = view.error instanceof AccessError && view.error.unavailable;
    return (
      <Alert color={ended ? "yellow" : "red"} title={ended ? "Tu sesión terminó" : "Error"}>
        <Stack gap="xs" align="flex-start">
          <Text size="sm">
            {ended
              ? "La sesión de acceso dura 30 minutos o el enlace dejó de estar disponible."
              : view.error.message}
          </Text>
          <Button size="xs" variant="light" onClick={onEnded}>
            Volver a abrir
          </Button>
        </Stack>
      </Alert>
    );
  }

  const doc = view.data;
  const zoomIndex = ZOOM_STEPS.indexOf(zoom);
  const paged = doc.kind === "pdf" || doc.kind === "image";

  return (
    <Stack>
      <Paper withBorder p="md" radius="md">
        <Group justify="space-between" wrap="wrap" gap="sm">
          <div>
            <Title order={4}>{doc.title}</Title>
            <Group gap={6} mt={4}>
              <PermissionBadge value={doc.permission} />
              <Badge variant="outline" size="sm" color={doc.live ? "teal" : "gray"}>
                {doc.live
                  ? `Versión vigente · v${doc.version}`
                  : `Copia compartida · v${doc.version}`}
              </Badge>
              {paged && (
                <Text size="xs" c="dimmed">
                  {doc.page_count} página(s) · viendo como {doc.viewer_label}
                </Text>
              )}
            </Group>
          </div>
          <Group gap="xs">
            {paged && (
              <Group gap={4}>
                <Tooltip label="Alejar">
                  <ActionIcon
                    variant="default"
                    aria-label="Alejar"
                    disabled={zoomIndex <= 0}
                    onClick={() => setZoom(ZOOM_STEPS[zoomIndex - 1]!)}
                  >
                    <IconZoomOut size={16} />
                  </ActionIcon>
                </Tooltip>
                <Text size="sm" w={44} ta="center">
                  {zoom}%
                </Text>
                <Tooltip label="Acercar">
                  <ActionIcon
                    variant="default"
                    aria-label="Acercar"
                    disabled={zoomIndex >= ZOOM_STEPS.length - 1}
                    onClick={() => setZoom(ZOOM_STEPS[zoomIndex + 1]!)}
                  >
                    <IconZoomIn size={16} />
                  </ActionIcon>
                </Tooltip>
              </Group>
            )}
            {doc.can_download && (
              <Button
                variant="light"
                leftSection={<IconDownload size={16} />}
                loading={download.isPending}
                onClick={() => download.mutate()}
              >
                Descargar
              </Button>
            )}
            {doc.can_edit && (
              <Button leftSection={<IconUpload size={16} />} onClick={() => setUploadOpen(true)}>
                Subir nueva versión
              </Button>
            )}
          </Group>
        </Group>
        {!doc.can_download && (
          <Group gap={6} mt="sm">
            <IconEyeOff size={14} color="var(--mantine-color-dimmed)" />
            <Text size="xs" c="dimmed">
              Solo lectura: quien te compartió este documento no permite descargarlo.
            </Text>
          </Group>
        )}
      </Paper>

      {paged ? (
        <ScrollArea.Autosize mah="calc(100vh - 260px)" type="auto" offsetScrollbars>
          <Stack gap="md" p={4}>
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
        </ScrollArea.Autosize>
      ) : doc.kind === "text" ? (
        <TextContent token={token} session={access} version={doc.version} />
      ) : (
        <Alert color="gray" title="Vista previa no disponible">
          Este tipo de archivo ({doc.mime_type}) no se puede mostrar en el visor.
          {doc.can_download ? " Puedes descargarlo con el botón Descargar." : ""}
        </Alert>
      )}

      {doc.can_edit && (
        <UploadVersionModal
          opened={uploadOpen}
          onClose={() => setUploadOpen(false)}
          token={token}
          session={access}
          view={doc}
        />
      )}
    </Stack>
  );
}
