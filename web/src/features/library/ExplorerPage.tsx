import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Breadcrumbs,
  Button,
  Card,
  Center,
  Grid,
  Group,
  Loader,
  Menu,
  Modal,
  NavLink,
  Paper,
  SegmentedControl,
  SimpleGrid,
  Skeleton,
  Stack,
  Table,
  Text,
  TextInput,
  Tooltip,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useQueryClient } from "@tanstack/react-query";
import {
  IconDots,
  IconDownload,
  IconEye,
  IconFolder,
  IconFolderPlus,
  IconLayoutGrid,
  IconList,
  IconSearch,
  IconPencil,
  IconTrash,
  IconShare,
  IconUpload,
  IconUsers,
} from "@tabler/icons-react";
import { modals } from "@mantine/modals";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useAuth } from "../../auth/context";
import { ClassificationBadge } from "../../components/badges";
import { PageHeader } from "../../components/PageHeader";
import { formatRelative } from "../../lib/format";
import { ShareWizard } from "../share/ShareWizard";
import {
  createFolder,
  deleteDocument,
  downloadDocument,
  type Folder,
  type LibraryDocument,
  libraryKeys,
  useItems,
  useLibraries,
} from "./api";
import { DocumentPanel } from "./DocumentPanel";
import { EditFileModal } from "./EditFileModal";
import { FileIcon, LibraryIcon } from "./icons";
import { NewVersionModal, UploadModal } from "./UploadModal";

type View = "list" | "grid";

function SharedBadge({ count }: { count: number }) {
  if (count === 0) return null;
  return (
    <Tooltip label="Personas externas con acceso vigente">
      <Badge size="sm" color="teal" variant="light" leftSection={<IconUsers size={11} />}>
        Compartido · {count}
      </Badge>
    </Tooltip>
  );
}

function NewFolderModal({
  opened,
  onClose,
  libraryId,
  parentId,
}: {
  opened: boolean;
  onClose: () => void;
  libraryId: string;
  parentId: string | null;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const close = () => {
    setName("");
    setError(null);
    onClose();
  };
  const submit = async () => {
    setSaving(true);
    setError(null);
    try {
      await createFolder(libraryId, parentId, name.trim());
      void queryClient.invalidateQueries({ queryKey: libraryKeys.all });
      close();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal opened={opened} onClose={close} title={<Text fw={700}>Nueva carpeta</Text>}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <Stack>
          <TextInput
            label="Nombre"
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
            maxLength={200}
            data-autofocus
            error={error}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>
              Cancelar
            </Button>
            <Button type="submit" loading={saving} disabled={!name.trim()}>
              Crear
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}

export function ExplorerPage() {
  const { libraryId, folderId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const libraries = useLibraries();
  const [view, setView] = useState<View>("list");

  const location = `${libraryId ?? ""}/${folderId ?? ""}`;
  const [searchState, setSearchState] = useState({ location, value: "" });
  const search = searchState.location === location ? searchState.value : "";
  const setSearch = (value: string) => setSearchState({ location, value });
  const [q] = useDebouncedValue(search.trim(), 300);
  const items = useItems(libraryId, folderId ?? null, q);
  const [selected, setSelected] = useState<string | null>(null);
  const [sharing, setSharing] = useState<LibraryDocument | null>(null);
  const [versionFor, setVersionFor] = useState<string | null>(null);
  const [editing, setEditing] = useState<LibraryDocument | null>(null);
  const { user, hasRole } = useAuth();
  const canShare = hasRole("SHARER");
  const canDelete = (doc: LibraryDocument) => hasRole("ADMIN") || doc.created_by === user?.email;
  const confirmDelete = (doc: LibraryDocument) =>
    modals.openConfirmModal({
      title: "Eliminar archivo",
      zIndex: 400,
      children: (
        <Text size="sm">
          ¿Eliminar «{doc.filename}»?
          {doc.active_shares > 0 ? ` ${doc.active_shares} envío(s) activo(s) se revocarán.` : ""}
        </Text>
      ),
      labels: { confirm: "Eliminar", cancel: "Cancelar" },
      confirmProps: { color: "red" },
      onConfirm: () =>
        void deleteDocument(doc.id)
          .then((revoked) => {
            notifications.show({
              color: "green",
              message: `Archivo eliminado${revoked ? ` y ${revoked} envío(s) revocado(s)` : ""}.`,
            });
            if (selected === doc.id) setSelected(null);
            void queryClient.invalidateQueries({ queryKey: libraryKeys.all });
            void queryClient.invalidateQueries({ queryKey: ["shares"] });
            void queryClient.invalidateQueries({ queryKey: ["stats"] });
          })
          .catch((e: Error) => notifications.show({ color: "red", message: e.message })),
    });
  const [uploadOpen, setUploadOpen] = useState(false);
  const [folderOpen, setFolderOpen] = useState(false);

  useEffect(() => {
    if (!libraryId && libraries.data?.[0]) {
      navigate(`/documentos/${libraries.data[0].id}`, { replace: true });
    }
  }, [libraryId, libraries.data, navigate]);

  const data = items.data;
  const locationLabel = [data?.library.name, ...(data?.breadcrumbs.map((b) => b.name) ?? [])]
    .filter(Boolean)
    .join(" / ");
  const openFolder = (folder: Folder) => navigate(`/documentos/${folder.library_id}/${folder.id}`);
  const download = (doc: LibraryDocument) =>
    downloadDocument(doc.id, doc.filename || `${doc.id}.pdf`).catch((e: Error) =>
      notifications.show({ color: "red", message: e.message }),
    );

  const docMenu = (doc: LibraryDocument) => (
    <Menu position="bottom-end" withinPortal>
      <Menu.Target>
        <ActionIcon
          variant="subtle"
          aria-label={`Acciones de ${doc.title}`}
          onClick={(e) => e.stopPropagation()}
        >
          <IconDots size={18} />
        </ActionIcon>
      </Menu.Target>
      <Menu.Dropdown onClick={(e) => e.stopPropagation()}>
        <Menu.Item leftSection={<IconEye size={16} />} onClick={() => setSelected(doc.id)}>
          Abrir
        </Menu.Item>
        {canShare && (
          <Menu.Item leftSection={<IconShare size={16} />} onClick={() => setSharing(doc)}>
            Compartir
          </Menu.Item>
        )}
        <Menu.Item leftSection={<IconPencil size={16} />} onClick={() => setEditing(doc)}>
          Editar
        </Menu.Item>
        <Menu.Item leftSection={<IconUpload size={16} />} onClick={() => setVersionFor(doc.id)}>
          Nueva versión
        </Menu.Item>
        <Menu.Item leftSection={<IconDownload size={16} />} onClick={() => void download(doc)}>
          Descargar
        </Menu.Item>
        {canDelete(doc) && (
          <>
            <Menu.Divider />
            <Menu.Item
              color="red"
              leftSection={<IconTrash size={16} />}
              onClick={() => confirmDelete(doc)}
            >
              Eliminar
            </Menu.Item>
          </>
        )}
      </Menu.Dropdown>
    </Menu>
  );

  const empty = data && data.folders.length === 0 && data.documents.length === 0;

  return (
    <>
      <PageHeader title="Documentos" />
      <Grid gap="lg">
        <Grid.Col span={{ base: 12, md: 3 }}>
          <Paper withBorder radius="lg" p="xs">
            <Text size="xs" c="dimmed" tt="uppercase" fw={600} px="sm" pt={4} pb={6}>
              Bibliotecas
            </Text>
            {libraries.isPending && <Skeleton h={180} />}
            {libraries.data?.map((lib) => (
              <NavLink
                key={lib.id}
                component={Link}
                to={`/documentos/${lib.id}`}
                label={lib.name}
                description={lib.description}
                leftSection={<LibraryIcon id={lib.id} />}
                rightSection={
                  <Badge size="xs" variant="light" color="gray">
                    {lib.document_count}
                  </Badge>
                }
                active={lib.id === libraryId}
                style={{ borderRadius: 8 }}
              />
            ))}
          </Paper>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 9 }}>
          <Stack gap="sm">
            <Group justify="space-between" wrap="wrap">
              <Breadcrumbs separatorMargin={6}>
                {data && (
                  <Anchor component={Link} to={`/documentos/${data.library.id}`} fw={600}>
                    {data.library.name}
                  </Anchor>
                )}
                {data?.breadcrumbs.map((crumb, i) =>
                  i === data.breadcrumbs.length - 1 ? (
                    <Text key={crumb.id} fw={600}>
                      {crumb.name}
                    </Text>
                  ) : (
                    <Anchor
                      key={crumb.id}
                      component={Link}
                      to={`/documentos/${crumb.library_id}/${crumb.id}`}
                    >
                      {crumb.name}
                    </Anchor>
                  ),
                )}
              </Breadcrumbs>
              <Group gap="xs">
                <Button
                  variant="default"
                  leftSection={<IconFolderPlus size={16} />}
                  onClick={() => setFolderOpen(true)}
                  disabled={!libraryId}
                >
                  Nueva carpeta
                </Button>
                <Button
                  leftSection={<IconUpload size={16} />}
                  onClick={() => setUploadOpen(true)}
                  disabled={!libraryId}
                >
                  Subir
                </Button>
              </Group>
            </Group>
            <Group justify="space-between">
              <TextInput
                placeholder="Buscar en esta biblioteca…"
                leftSection={<IconSearch size={16} />}
                value={search}
                onChange={(e) => setSearch(e.currentTarget.value)}
                w={320}
              />
              <SegmentedControl
                size="xs"
                value={view}
                onChange={(v) => setView(v as View)}
                data={[
                  { value: "list", label: <IconList size={16} aria-label="Lista" /> },
                  { value: "grid", label: <IconLayoutGrid size={16} aria-label="Cuadrícula" /> },
                ]}
              />
            </Group>

            {items.isError && <Alert color="red">{items.error.message}</Alert>}
            {items.isPending && libraryId && (
              <Center h={200}>
                <Loader />
              </Center>
            )}
            {empty && (
              <Paper withBorder radius="lg" p="xl">
                <Stack align="center" gap={6}>
                  <IconFolder size={40} color="var(--mantine-color-dimmed)" />
                  <Text fw={600}>{q ? "Sin resultados" : "Esta carpeta está vacía"}</Text>
                  {!q && (
                    <Text size="sm" c="dimmed">
                      Sube archivos o crea una carpeta para empezar.
                    </Text>
                  )}
                </Stack>
              </Paper>
            )}

            {data && !empty && view === "list" && (
              <Card withBorder radius="lg" p={0}>
                <Table.ScrollContainer minWidth={720}>
                  <Table highlightOnHover verticalSpacing="sm">
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Nombre</Table.Th>
                        <Table.Th>Clasificación</Table.Th>
                        <Table.Th>Modificado</Table.Th>
                        <Table.Th>Versión</Table.Th>
                        <Table.Th />
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {data.folders.map((folder) => (
                        <Table.Tr
                          key={folder.id}
                          style={{ cursor: "pointer" }}
                          onClick={() => openFolder(folder)}
                        >
                          <Table.Td>
                            <Group gap="sm" wrap="nowrap">
                              <IconFolder size={22} color="var(--mantine-color-yellow-6)" />
                              <Text size="sm" fw={500}>
                                {folder.name}
                              </Text>
                            </Group>
                          </Table.Td>
                          <Table.Td />
                          <Table.Td>
                            <Text size="sm" c="dimmed">
                              {formatRelative(folder.created_at)}
                            </Text>
                          </Table.Td>
                          <Table.Td />
                          <Table.Td />
                        </Table.Tr>
                      ))}
                      {data.documents.map((doc) => (
                        <Table.Tr
                          key={doc.id}
                          style={{ cursor: "pointer" }}
                          onClick={() => setSelected(doc.id)}
                        >
                          <Table.Td>
                            <Group gap="sm" wrap="nowrap">
                              <FileIcon mime={doc.mime_type} />
                              <Stack gap={0} style={{ minWidth: 0 }}>
                                <Text size="sm" fw={500} lineClamp={1}>
                                  {doc.title}
                                </Text>
                                <Group gap={6}>
                                  <Text size="xs" c="dimmed" lineClamp={1}>
                                    {doc.filename}
                                  </Text>
                                  <SharedBadge count={doc.active_shares} />
                                </Group>
                              </Stack>
                            </Group>
                          </Table.Td>
                          <Table.Td>
                            <ClassificationBadge value={doc.classification} />
                          </Table.Td>
                          <Table.Td>
                            <Text size="sm">{formatRelative(doc.updated_at)}</Text>
                            <Text size="xs" c="dimmed">
                              {doc.created_by}
                            </Text>
                          </Table.Td>
                          <Table.Td>v{doc.version}</Table.Td>
                          <Table.Td ta="right">{docMenu(doc)}</Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
              </Card>
            )}

            {data && !empty && view === "grid" && (
              <SimpleGrid cols={{ base: 2, sm: 3, lg: 4 }}>
                {data.folders.map((folder) => (
                  <Card
                    key={folder.id}
                    withBorder
                    radius="lg"
                    style={{ cursor: "pointer" }}
                    onClick={() => openFolder(folder)}
                  >
                    <Stack align="center" gap={6}>
                      <IconFolder size={44} color="var(--mantine-color-yellow-6)" />
                      <Text size="sm" fw={500} ta="center" lineClamp={2}>
                        {folder.name}
                      </Text>
                    </Stack>
                  </Card>
                ))}
                {data.documents.map((doc) => (
                  <Card
                    key={doc.id}
                    withBorder
                    radius="lg"
                    style={{ cursor: "pointer" }}
                    onClick={() => setSelected(doc.id)}
                  >
                    <Group justify="flex-end" mt={-8} mr={-8}>
                      {docMenu(doc)}
                    </Group>
                    <Stack align="center" gap={6}>
                      <FileIcon mime={doc.mime_type} size={44} />
                      <Text size="sm" fw={500} ta="center" lineClamp={2}>
                        {doc.title}
                      </Text>
                      <ClassificationBadge value={doc.classification} />
                      <SharedBadge count={doc.active_shares} />
                    </Stack>
                  </Card>
                ))}
              </SimpleGrid>
            )}
          </Stack>
        </Grid.Col>
      </Grid>

      <DocumentPanel
        key={selected ?? "none"}
        documentId={selected}
        onClose={() => setSelected(null)}
        onShare={setSharing}
        onNewVersion={setVersionFor}
        onEdit={setEditing}
        onDelete={canDelete}
        confirmDelete={confirmDelete}
        canShare={canShare}
      />
      <EditFileModal document={editing} onClose={() => setEditing(null)} />
      <ShareWizard
        document={sharing}
        opened={sharing !== null}
        onClose={() => {
          setSharing(null);
          void queryClient.invalidateQueries({ queryKey: libraryKeys.all });
        }}
      />
      <NewVersionModal documentId={versionFor} onClose={() => setVersionFor(null)} />
      {libraryId && (
        <>
          <UploadModal
            opened={uploadOpen}
            onClose={() => setUploadOpen(false)}
            libraryId={libraryId}
            folderId={folderId ?? null}
            locationLabel={locationLabel}
          />
          <NewFolderModal
            opened={folderOpen}
            onClose={() => setFolderOpen(false)}
            libraryId={libraryId}
            parentId={folderId ?? null}
          />
        </>
      )}
    </>
  );
}
