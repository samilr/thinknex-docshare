import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Card,
  Code,
  CopyButton,
  Group,
  Menu,
  Modal,
  MultiSelect,
  Skeleton,
  Stack,
  Table,
  Text,
  TextInput,
} from "@mantine/core";
import { isEmail, isNotEmpty, useForm } from "@mantine/form";
import { useDebouncedValue } from "@mantine/hooks";
import { useNavigate } from "react-router";
import { modals } from "@mantine/modals";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  IconDots,
  IconKey,
  IconPencil,
  IconPlus,
  IconSearch,
  IconUserCheck,
  IconUserOff,
  IconUserShare,
} from "@tabler/icons-react";
import { useState } from "react";
import { api, problemMessage, type Schemas, unwrap } from "../api/client";
import { useAuth } from "../auth/context";
import { RoleBadge } from "../components/badges";
import { PageHeader } from "../components/PageHeader";
import { formatRelative } from "../lib/format";
import { ROLE } from "../lib/labels";

type User = Schemas["UserOut"];
type Role = Schemas["UserCreate"]["roles"][number];
const ROLE_OPTIONS = Object.entries(ROLE).map(([value, { label }]) => ({ value, label }));

function TemporaryPasswordModal({
  data,
  onClose,
}: {
  data: Schemas["TemporaryPasswordOut"] | null;
  onClose: () => void;
}) {
  return (
    <Modal opened={!!data} onClose={onClose} title="Contraseña temporal">
      {data && (
        <Stack>
          <Text size="sm">
            Entrega esta contraseña a <b>{data.user.email}</b> por un canal seguro. Se muestra{" "}
            <b>una sola vez</b> y deberá cambiarla en su primer ingreso.
          </Text>
          <Group>
            <Code fz="lg" style={{ flex: 1 }}>
              {data.temporary_password}
            </Code>
            <CopyButton value={data.temporary_password}>
              {({ copied, copy }) => (
                <Button
                  variant={copied ? "filled" : "light"}
                  color={copied ? "teal" : "blue"}
                  onClick={copy}
                >
                  {copied ? "Copiada" : "Copiar"}
                </Button>
              )}
            </CopyButton>
          </Group>
          <Button onClick={onClose}>Listo</Button>
        </Stack>
      )}
    </Modal>
  );
}

function UserFormModal({
  user,
  opened,
  onClose,
  onCreated,
}: {
  user: User | null;
  opened: boolean;
  onClose: () => void;
  onCreated: (data: Schemas["TemporaryPasswordOut"]) => void;
}) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const form = useForm({
    initialValues: {
      email: user?.email ?? "",
      name: user?.name ?? "",
      roles: (user?.roles ?? ["SHARER"]) as string[],
    },
    validate: {
      email: user ? undefined : isEmail("Email inválido"),
      name: isNotEmpty("Ingrese el nombre"),
      roles: (v) => (v.length === 0 ? "Seleccione al menos un rol" : null),
    },
  });
  const save = useMutation({
    mutationFn: async (values: typeof form.values) => {
      const roles = values.roles as Role[];
      if (user) {
        const { data, error } = await api.PATCH("/api/v1/admin/users/{user_id}", {
          params: { path: { user_id: user.id } },
          body: { name: values.name, roles },
        });
        if (!data) throw new Error(problemMessage(error));
        return null;
      }
      const { data, error } = await api.POST("/api/v1/admin/users", {
        body: { email: values.email, name: values.name, roles },
      });
      if (!data) throw new Error(problemMessage(error));
      return data;
    },
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
      notifications.show({
        color: "green",
        message: user ? "Usuario actualizado" : "Usuario creado",
      });
      onClose();
      if (created) onCreated(created);
    },
    onError: (e) => setError(e.message),
  });

  return (
    <Modal opened={opened} onClose={onClose} title={user ? "Editar usuario" : "Nuevo usuario"}>
      <form onSubmit={form.onSubmit((v) => save.mutate(v))} noValidate>
        <Stack>
          {error && <Alert color="red">{error}</Alert>}
          <TextInput label="Email" disabled={!!user} {...form.getInputProps("email")} />
          <TextInput label="Nombre" {...form.getInputProps("name")} />
          <MultiSelect label="Roles" data={ROLE_OPTIONS} {...form.getInputProps("roles")} />
          <Text size="xs" c="dimmed">
            Emisor: comparte documentos. Auditor: consulta la auditoría. Administrador: gestiona
            usuarios y la plataforma.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancelar
            </Button>
            <Button type="submit" loading={save.isPending}>
              Guardar
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}

export function UsersPage() {
  const { user: me, impersonate } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [q] = useDebouncedValue(search, 300);
  const [editing, setEditing] = useState<User | null | undefined>(undefined);
  const [temporary, setTemporary] = useState<Schemas["TemporaryPasswordOut"] | null>(null);

  const users = useQuery({
    queryKey: ["users", q],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/admin/users", {
          params: { query: { q: q || undefined, limit: 100 } },
        }),
      ),
  });

  const toggleActive = useMutation({
    mutationFn: async (u: User) => {
      const { data, error } = await api.PATCH("/api/v1/admin/users/{user_id}", {
        params: { path: { user_id: u.id } },
        body: { is_active: !u.is_active },
      });
      if (!data) throw new Error(problemMessage(error));
      return data;
    },
    onSuccess: (u) => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
      notifications.show({
        color: "green",
        message: u.is_active ? "Usuario activado" : "Usuario desactivado y sesiones cerradas",
      });
    },
    onError: (e) => notifications.show({ color: "red", message: e.message }),
  });

  const resetPassword = useMutation({
    mutationFn: async (u: User) => {
      const { data, error } = await api.POST("/api/v1/admin/users/{user_id}/reset-password", {
        params: { path: { user_id: u.id } },
      });
      if (!data) throw new Error(problemMessage(error));
      return data;
    },
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
      setTemporary(data);
    },
    onError: (e) => notifications.show({ color: "red", message: e.message }),
  });

  const stateBadge = (u: User) => {
    if (!u.is_active) return <Badge color="gray">Inactivo</Badge>;
    if (u.locked_until && new Date(u.locked_until) > new Date())
      return <Badge color="red">Bloqueado</Badge>;
    if (u.must_change_password) return <Badge color="yellow">Clave temporal</Badge>;
    return <Badge color="green">Activo</Badge>;
  };

  return (
    <>
      <PageHeader
        title="Usuarios"
        actions={
          <Button leftSection={<IconPlus size={16} />} onClick={() => setEditing(null)}>
            Nuevo usuario
          </Button>
        }
      />
      <TextInput
        placeholder="Buscar por nombre o email…"
        leftSection={<IconSearch size={16} />}
        value={search}
        onChange={(e) => setSearch(e.currentTarget.value)}
        mb="md"
        maw={420}
      />
      {users.isError && <Alert color="red">{users.error.message}</Alert>}
      <Card withBorder radius="lg" p={0}>
        <Skeleton visible={users.isPending}>
          <Table.ScrollContainer minWidth={760}>
            <Table highlightOnHover verticalSpacing="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Nombre</Table.Th>
                  <Table.Th>Roles</Table.Th>
                  <Table.Th>Estado</Table.Th>
                  <Table.Th>Último acceso</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {users.data?.items.map((u) => (
                  <Table.Tr key={u.id}>
                    <Table.Td>
                      <Text size="sm" fw={500}>
                        {u.name}{" "}
                        {u.id === me?.id && (
                          <Badge size="xs" variant="outline">
                            tú
                          </Badge>
                        )}
                      </Text>
                      <Text size="xs" c="dimmed">
                        {u.email}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Group gap={4}>
                        {u.roles.map((r) => (
                          <RoleBadge key={r} role={r} />
                        ))}
                      </Group>
                    </Table.Td>
                    <Table.Td>{stateBadge(u)}</Table.Td>
                    <Table.Td>
                      <Text size="sm">{formatRelative(u.last_login_at)}</Text>
                    </Table.Td>
                    <Table.Td ta="right">
                      <Menu position="bottom-end" withinPortal>
                        <Menu.Target>
                          <ActionIcon variant="subtle" aria-label={`Acciones para ${u.email}`}>
                            <IconDots size={18} />
                          </ActionIcon>
                        </Menu.Target>
                        <Menu.Dropdown>
                          <Menu.Item
                            leftSection={<IconPencil size={16} />}
                            onClick={() => setEditing(u)}
                          >
                            Editar nombre y roles
                          </Menu.Item>
                          <Menu.Item
                            leftSection={<IconKey size={16} />}
                            onClick={() =>
                              modals.openConfirmModal({
                                title: "Reiniciar contraseña",
                                children: (
                                  <Text size="sm">
                                    Se generará una contraseña temporal y se cerrarán las sesiones
                                    de {u.email}.
                                  </Text>
                                ),
                                labels: { confirm: "Reiniciar", cancel: "Cancelar" },
                                onConfirm: () => resetPassword.mutate(u),
                              })
                            }
                          >
                            Reiniciar contraseña
                          </Menu.Item>
                          {u.id !== me?.id && u.is_active && !u.roles.includes("ADMIN") && (
                            <Menu.Item
                              leftSection={<IconUserShare size={16} />}
                              onClick={() =>
                                modals.openConfirmModal({
                                  title: "Actuar como este usuario",
                                  children: (
                                    <Text size="sm">
                                      Verás la plataforma como {u.name} ({u.email}). Las acciones
                                      quedan registradas a su nombre y al tuyo.
                                    </Text>
                                  ),
                                  labels: { confirm: "Actuar como", cancel: "Cancelar" },
                                  onConfirm: () =>
                                    void impersonate(u.id)
                                      .then(() => navigate("/"))
                                      .catch((e: Error) =>
                                        notifications.show({ color: "red", message: e.message }),
                                      ),
                                })
                              }
                            >
                              Actuar como este usuario
                            </Menu.Item>
                          )}
                          {u.id !== me?.id && (
                            <Menu.Item
                              color={u.is_active ? "red" : "green"}
                              leftSection={
                                u.is_active ? (
                                  <IconUserOff size={16} />
                                ) : (
                                  <IconUserCheck size={16} />
                                )
                              }
                              onClick={() => toggleActive.mutate(u)}
                            >
                              {u.is_active ? "Desactivar" : "Activar"}
                            </Menu.Item>
                          )}
                        </Menu.Dropdown>
                      </Menu>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Skeleton>
      </Card>
      {editing !== undefined && (
        <UserFormModal
          key={editing?.id ?? "new"}
          user={editing}
          opened
          onClose={() => setEditing(undefined)}
          onCreated={setTemporary}
        />
      )}
      <TemporaryPasswordModal data={temporary} onClose={() => setTemporary(null)} />
    </>
  );
}
