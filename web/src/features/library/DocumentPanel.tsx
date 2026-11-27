import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Center,
  Code,
  Drawer,
  Group,
  Loader,
  ScrollArea,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  Text,
  Timeline,
  Tooltip,
} from "@mantine/core";
import { modals } from "@mantine/modals";
import { notifications } from "@mantine/notifications";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  IconActivity,
  IconAdjustments,
  IconBan,
  IconDownload,
  IconEye,
  IconInfoCircle,
  IconLink,
  IconPencil,
  IconPoint,
  IconRefresh,
  IconShare,
  IconTrash,
  IconUpload,
  IconUsers,
} from "@tabler/icons-react";
import { type ReactNode, useEffect, useState } from "react";
import { api, problemMessage } from "../../api/client";
import { useAuth } from "../../auth/context";
import {
  AudienceBadge,
  ChannelLabel,
  ClassificationBadge,
  PermissionBadge,
  StatusBadge,
  WatermarkBadge,
} from "../../components/badges";
import { revealLink, type Share } from "../share/api";
import { EditShareModal } from "../share/EditShareModal";
import { LinkReveal } from "../share/LinkReveal";
import { formatDateTime, formatRelative } from "../../lib/format";
import { eventSummary } from "../../lib/events";
import { EVENT, EVENT_COLOR } from "../../lib/labels";
import {
  downloadDocument,
  fetchContent,
  type LibraryDocument,
  libraryKeys,
  useAccess,
  useActivity,
  type DocumentDetail,
  useDocumentDetail,
} from "./api";
import { fileKind, formatBytes } from "./files";
import { FileIcon } from "./icons";

function Preview({ id, mime, version }: { id: string; mime: string; version: number }) {
  const [url, setUrl] = useState<string | null>(null);
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const kind = fileKind(mime);
  const previewable = kind === "pdf" || kind === "image" || kind === "text";

  useEffect(() => {
    if (!previewable) return;
    let objectUrl: string | null = null;
    let cancelled = false;
    fetchContent(id, { version })
      .then(async (blob) => {
        if (cancelled) return;
        if (kind === "text") setText(await blob.text());
        else {
          objectUrl = URL.createObjectURL(blob);
          setUrl(objectUrl);
        }
      })
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [id, version, kind, previewable]);

  if (!previewable) {
    return (
      <Center h={300}>
        <Stack align="center" gap={6}>
          <FileIcon mime={mime} size={48} />
          <Text c="dimmed">Vista previa no disponible para este tipo de archivo.</Text>
        </Stack>
      </Center>
    );
  }
  if (error) return <Alert color="red">{error}</Alert>;
  if (!url && text === null) {
    return (
      <Center h={300}>
        <Loader />
      </Center>
    );
  }
  if (kind === "text") {
    return (
      <ScrollArea h="65vh">
        <Code block>{text}</Code>
      </ScrollArea>
    );
  }
  if (kind === "image") {
    return <img src={url!} alt="Vista previa" style={{ maxWidth: "100%", borderRadius: 8 }} />;
  }
  return (
    <iframe
      title="Vista previa del documento"
      src={url!}
      style={{ width: "100%", height: "68vh", border: 0, borderRadius: 8 }}
    />
  );
}

const AI_STATUS: Record<string, { label: string; color: string }> = {
  INDEXED: { label: "Indexado", color: "teal" },
  PENDING: { label: "En cola", color: "gray" },
  EMPTY: { label: "Sin texto", color: "yellow" },
  SKIPPED: { label: "Excluido", color: "orange" },
  FAILED: { label: "Error", color: "red" },
};

function AiIndexBadge({ status }: { status: NonNullable<DocumentDetail["ai"]> }) {
  const { label, color } = AI_STATUS[status.status] ?? { label: status.status, color: "gray" };
  return (
    <Group gap={6}>
      <Badge variant="light" color={color} size="sm">
        {label}
      </Badge>
      <Text size="xs" c="dimmed">
        {status.status === "INDEXED" ? `${status.chunk_count} fragmento(s)` : (status.error ?? "")}
      </Text>
    </Group>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <div>{children}</div>
    </div>
  );
}

export function DocumentPanel({
  documentId,
  onClose,
  onShare,
  onNewVersion,
  onEdit,
  onDelete,
  confirmDelete,
  canShare,
}: {
  documentId: string | null;
  onClose: () => void;
  onShare: (doc: LibraryDocument) => void;
  onNewVersion: (documentId: string) => void;
  onEdit: (doc: LibraryDocument) => void;

  onDelete: (doc: LibraryDocument) => boolean;
  confirmDelete: (doc: LibraryDocument) => void;
  canShare: boolean;
}) {
  const { user, hasRole } = useAuth();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<string | null>("preview");
  const detail = useDocumentDetail(documentId);
  const access = useAccess(tab === "access" ? documentId : null);
  const activity = useActivity(tab === "activity" ? documentId : null);
  const [previewVersion, setPreviewVersion] = useState<number | null>(null);

  const revoke = useMutation({
    mutationFn: async (shareId: string) => {
      const { data, error } = await api.POST("/api/v1/shares/{share_id}/revoke", {
        params: { path: { share_id: shareId } },
      });
      if (!data) throw new Error(problemMessage(error));
      return data;
    },
    onSuccess: () => {
      notifications.show({ color: "green", message: "Acceso revocado" });
      void queryClient.invalidateQueries({ queryKey: libraryKeys.all });
      void queryClient.invalidateQueries({ queryKey: ["shares"] });
    },
    onError: (e) => notifications.show({ color: "red", message: e.message }),
  });

  const [revealed, setRevealed] = useState<{ id: string; link: string } | null>(null);
  const [editingShare, setEditingShare] = useState<Share | null>(null);
  const reveal = useMutation({
    mutationFn: async (shareId: string) => ({ id: shareId, link: await revealLink(shareId) }),
    onSuccess: setRevealed,
    onError: (e) => notifications.show({ color: "red", message: e.message }),
  });
  const rotate = useMutation({
    mutationFn: async (shareId: string) => {
      const { data, error } = await api.POST("/api/v1/shares/{share_id}/link", {
        params: { path: { share_id: shareId } },
      });
      if (!data) throw new Error(problemMessage(error));
      return data;
    },
    onSuccess: (data) => {
      if (data.link) setRevealed({ id: data.id, link: data.link });
      notifications.show({ color: "green", message: "Nuevo enlace generado" });
    },
    onError: (e) => notifications.show({ color: "red", message: e.message }),
  });

  const doc = detail.data?.document;
  const version = previewVersion ?? doc?.version ?? 1;
  const download = (v?: number) =>
    doc &&
    downloadDocument(doc.id, doc.filename || `${doc.id}.pdf`, v).catch((e: Error) =>
      notifications.show({ color: "red", message: e.message }),
    );

  return (
    <Drawer
      opened={!!documentId}
      onClose={onClose}
      position="right"
      size="xl"
      title={
        doc ? (
          <Group gap="sm" wrap="nowrap">
            <FileIcon mime={doc.mime_type} />
            <Text fw={700} lineClamp={1}>
              {doc.title}
            </Text>
          </Group>
        ) : (
          "Documento"
        )
      }
    >
      {detail.isPending && <Loader />}
      {detail.isError && <Alert color="red">{detail.error.message}</Alert>}
      {doc && detail.data && (
        <Stack>
          <Group gap="xs">
            <ClassificationBadge value={doc.classification} />
            <Badge variant="light">v{doc.version}</Badge>
            {doc.active_shares > 0 && (
              <Badge color="teal" variant="light" leftSection={<IconUsers size={12} />}>
                Compartido · {doc.active_shares}
              </Badge>
            )}
          </Group>
          <Group gap="xs">
            {canShare && (
              <Button leftSection={<IconShare size={16} />} onClick={() => onShare(doc)}>
                Compartir
              </Button>
            )}
            <Button
              variant="default"
              leftSection={<IconDownload size={16} />}
              onClick={() => download()}
            >
              Descargar
            </Button>
            <Button
              variant="default"
              leftSection={<IconUpload size={16} />}
              onClick={() => onNewVersion(doc.id)}
            >
              Nueva versión
            </Button>
            <Button
              variant="default"
              leftSection={<IconPencil size={16} />}
              onClick={() => onEdit(doc)}
            >
              Editar
            </Button>
            {onDelete(doc) && (
              <Button
                variant="light"
                color="red"
                leftSection={<IconTrash size={16} />}
                onClick={() => confirmDelete(doc)}
              >
                Eliminar
              </Button>
            )}
          </Group>

          <Tabs value={tab} onChange={setTab} keepMounted={false}>
            <Tabs.List>
              <Tabs.Tab value="preview" leftSection={<IconEye size={14} />}>
                Vista previa
              </Tabs.Tab>
              <Tabs.Tab value="details" leftSection={<IconInfoCircle size={14} />}>
                Detalles
              </Tabs.Tab>
              <Tabs.Tab value="access" leftSection={<IconUsers size={14} />}>
                Acceso
              </Tabs.Tab>
              <Tabs.Tab value="activity" leftSection={<IconActivity size={14} />}>
                Actividad
              </Tabs.Tab>
            </Tabs.List>

            <Tabs.Panel value="preview" pt="md">
              {version !== doc.version && (
                <Alert color="yellow" mb="sm">
                  Estás viendo la versión {version} (no vigente).{" "}
                  <Button
                    size="compact-xs"
                    variant="subtle"
                    onClick={() => setPreviewVersion(null)}
                  >
                    Ver vigente
                  </Button>
                </Alert>
              )}
              <Preview
                key={`${doc.id}-${version}`}
                id={doc.id}
                mime={doc.mime_type}
                version={version}
              />
            </Tabs.Panel>

            <Tabs.Panel value="details" pt="md">
              <Stack>
                <SimpleGrid cols={2}>
                  <Field label="Archivo">
                    <Text size="sm">{doc.filename}</Text>
                  </Field>
                  <Field label="Ubicación">
                    <Text size="sm">
                      {[detail.data.library?.name, ...detail.data.breadcrumbs.map((b) => b.name)]
                        .filter(Boolean)
                        .join(" / ")}
                    </Text>
                  </Field>
                  <Field label="Responsable">
                    <Text size="sm">{doc.owner}</Text>
                  </Field>
                  <Field label="Modificado">
                    <Text size="sm">
                      {formatDateTime(doc.updated_at)} · {doc.created_by}
                    </Text>
                  </Field>
                  <Field label="Tamaño">
                    <Text size="sm">{formatBytes(doc.size_bytes)}</Text>
                  </Field>
                  <Field label="Identificador">
                    <Text size="sm" ff="monospace">
                      {doc.id}
                    </Text>
                  </Field>
                  {detail.data.ai && (
                    <Field label="Índice de IA">
                      <AiIndexBadge status={detail.data.ai} />
                    </Field>
                  )}
                </SimpleGrid>
                <Field label="Integridad (sha256)">
                  <Text size="xs" ff="monospace" c="dimmed" style={{ wordBreak: "break-all" }}>
                    {doc.sha256}
                  </Text>
                </Field>
                <Text fw={600} size="sm">
                  Historial de versiones
                </Text>
                <Table withTableBorder fz="sm">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Versión</Table.Th>
                      <Table.Th>Fecha</Table.Th>
                      <Table.Th>Autor</Table.Th>
                      <Table.Th>Comentario</Table.Th>
                      <Table.Th />
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {detail.data.versions.map((v) => (
                      <Table.Tr key={v.version}>
                        <Table.Td>
                          v{v.version}{" "}
                          {v.version === doc.version && (
                            <Badge size="xs" variant="light">
                              vigente
                            </Badge>
                          )}
                        </Table.Td>
                        <Table.Td>{formatDateTime(v.created_at)}</Table.Td>
                        <Table.Td>{v.created_by}</Table.Td>
                        <Table.Td>{v.comment || "—"}</Table.Td>
                        <Table.Td>
                          <Group gap={4} wrap="nowrap">
                            <Tooltip label="Ver">
                              <ActionIcon
                                variant="subtle"
                                aria-label={`Ver versión ${v.version}`}
                                onClick={() => {
                                  setPreviewVersion(v.version);
                                  setTab("preview");
                                }}
                              >
                                <IconEye size={16} />
                              </ActionIcon>
                            </Tooltip>
                            <Tooltip label="Descargar">
                              <ActionIcon
                                variant="subtle"
                                aria-label={`Descargar versión ${v.version}`}
                                onClick={() => download(v.version)}
                              >
                                <IconDownload size={16} />
                              </ActionIcon>
                            </Tooltip>
                          </Group>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Stack>
            </Tabs.Panel>

            <Tabs.Panel value="access" pt="md">
              <Stack>
                <Group justify="space-between">
                  <Text fw={600}>Personas con acceso</Text>
                  {canShare && (
                    <Button
                      size="xs"
                      leftSection={<IconShare size={14} />}
                      onClick={() => onShare(doc)}
                    >
                      Compartir
                    </Button>
                  )}
                </Group>
                {access.isPending && <Loader size="sm" />}
                {access.data?.length === 0 && (
                  <Text c="dimmed" size="sm">
                    Este archivo aún no se ha compartido.
                  </Text>
                )}
                {access.data?.map((s) => {
                  const canRevoke =
                    s.status === "ACTIVE" && (s.shared_by === user?.email || hasRole("ADMIN"));
                  const canManage =
                    (s.status === "ACTIVE" || s.status === "EXHAUSTED") &&
                    (s.shared_by === user?.email || hasRole("ADMIN"));
                  const who = s.recipient?.name ?? "Cualquier persona con el enlace";
                  return (
                    <Stack
                      key={s.id}
                      gap="xs"
                      p="sm"
                      style={{
                        border: "1px solid var(--mantine-color-default-border)",
                        borderRadius: 8,
                      }}
                    >
                      <Group justify="space-between" wrap="nowrap" align="flex-start">
                        <Stack gap={2}>
                          <Group gap={6}>
                            <Text size="sm" fw={600}>
                              {who}
                            </Text>
                            <StatusBadge status={s.status} />
                          </Group>
                          <Text size="xs" c="dimmed">
                            {s.recipient ? `${s.recipient.contact} · ` : ""}compartido por{" "}
                            {s.shared_by} · {formatRelative(s.created_at)}
                          </Text>
                          <Group gap={6}>
                            <PermissionBadge value={s.permission} />
                            <AudienceBadge value={s.audience} />
                            <WatermarkBadge value={s.watermark} />
                          </Group>
                          <Group gap="md">
                            <ChannelLabel channel={s.channel} />
                            <Text size="xs" c="dimmed">
                              {s.access_count}/{s.max_accesses} accesos · vence{" "}
                              {formatRelative(s.expires_at)}
                            </Text>
                          </Group>
                        </Stack>
                        <Stack gap={6} align="flex-end">
                          {canManage && revealed?.id !== s.id && (
                            <Button
                              size="xs"
                              variant="light"
                              leftSection={<IconLink size={14} />}
                              loading={reveal.isPending && reveal.variables === s.id}
                              onClick={() => reveal.mutate(s.id)}
                            >
                              Ver enlace
                            </Button>
                          )}
                          {canManage && (
                            <Button
                              size="xs"
                              variant="light"
                              leftSection={<IconAdjustments size={14} />}
                              onClick={() => setEditingShare(s)}
                            >
                              Editar acceso
                            </Button>
                          )}
                          {canRevoke && s.channel === "LINK" && (
                            <Button
                              size="xs"
                              variant="light"
                              leftSection={<IconRefresh size={14} />}
                              loading={rotate.isPending && rotate.variables === s.id}
                              onClick={() =>
                                modals.openConfirmModal({
                                  title: "Generar nuevo enlace",
                                  zIndex: 400,
                                  children: (
                                    <Text size="sm">
                                      El enlace actual dejará de funcionar de inmediato.
                                    </Text>
                                  ),
                                  labels: { confirm: "Generar", cancel: "Cancelar" },
                                  onConfirm: () => rotate.mutate(s.id),
                                })
                              }
                            >
                              Nuevo enlace
                            </Button>
                          )}
                          {canRevoke && (
                            <Button
                              size="xs"
                              color="red"
                              variant="light"
                              leftSection={<IconBan size={14} />}
                              loading={revoke.isPending && revoke.variables === s.id}
                              onClick={() =>
                                modals.openConfirmModal({
                                  title: "Revocar acceso",
                                  children: (
                                    <Text size="sm">
                                      {who} dejará de poder abrir el enlace de inmediato.
                                    </Text>
                                  ),
                                  labels: { confirm: "Revocar", cancel: "Cancelar" },
                                  confirmProps: { color: "red" },
                                  onConfirm: () => revoke.mutate(s.id),
                                })
                              }
                            >
                              Revocar
                            </Button>
                          )}
                        </Stack>
                      </Group>
                      {revealed?.id === s.id && <LinkReveal link={revealed.link} />}
                    </Stack>
                  );
                })}
              </Stack>
            </Tabs.Panel>

            <Tabs.Panel value="activity" pt="md">
              {activity.isPending ? (
                <Loader size="sm" />
              ) : (
                <Timeline bulletSize={18} lineWidth={2}>
                  {activity.data?.map((e) => (
                    <Timeline.Item
                      key={e.id}
                      bullet={<IconPoint size={12} />}
                      color={EVENT_COLOR[e.event_type] ?? "blue"}
                      title={
                        <Text size="sm" fw={600}>
                          {EVENT[e.event_type] ?? e.event_type}
                        </Text>
                      }
                    >
                      {eventSummary(e) && <Text size="xs">{eventSummary(e)}</Text>}
                      <Text size="xs" c="dimmed">
                        {formatDateTime(e.occurred_at)} · {e.actor ?? e.actor_type}
                        {e.channel ? ` · ${e.channel}` : ""}
                      </Text>
                    </Timeline.Item>
                  ))}
                </Timeline>
              )}
            </Tabs.Panel>
          </Tabs>
        </Stack>
      )}
      <EditShareModal share={editingShare} onClose={() => setEditingShare(null)} />
    </Drawer>
  );
}
