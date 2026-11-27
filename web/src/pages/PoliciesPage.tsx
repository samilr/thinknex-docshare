import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Group,
  Loader,
  Modal,
  MultiSelect,
  Paper,
  SegmentedControl,
  Stack,
  Switch,
  Table,
  Text,
  Textarea,
  TextInput,
  Tooltip,
} from "@mantine/core";
import { hasLength, useForm } from "@mantine/form";
import { modals } from "@mantine/modals";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { IconInfoCircle, IconPencil, IconPlus, IconTrash } from "@tabler/icons-react";
import { useState } from "react";
import { api, problemMessage, type Schemas, unwrap } from "../api/client";
import { useAuth } from "../auth/context";
import { PageHeader } from "../components/PageHeader";
import { formatRelative } from "../lib/format";
import { CHANNEL, CLASSIFICATION, FINDING, labelOf } from "../lib/labels";

type Rule = Schemas["PolicyRuleOut"];
type RuleIn = Schemas["PolicyRuleIn"];

const KEY = ["policies"] as const;
const option = (map: Record<string, { label: string }>) =>
  Object.entries(map).map(([value, { label }]) => ({ value, label }));
const CLASSIFICATION_OPTIONS = option(CLASSIFICATION);
const CHANNEL_OPTIONS = option(CHANNEL);
const FINDING_OPTIONS = Object.entries(FINDING).map(([value, label]) => ({ value, label }));
const RECIPIENT_LABEL: Record<string, string> = {
  ANY: "Cualquier destinatario",
  INTERNAL: "Destinatario interno",
  EXTERNAL: "Destinatario externo",
};
const EMPTY: RuleIn = {
  name: "",
  description: "",
  action: "WARN",
  message: "",
  classifications: [],
  recipient: "EXTERNAL",
  finding_types: [],
  channels: [],
  enabled: true,
};

function ActionBadge({ action }: { action: string }) {
  return action === "BLOCK" ? (
    <Badge color="red" miw="max-content" style={{ overflow: "visible" }}>
      Bloquear
    </Badge>
  ) : (
    <Badge color="yellow" miw="max-content" style={{ overflow: "visible" }}>
      Advertir
    </Badge>
  );
}

/** Resumen de las condiciones de una regla en lenguaje natural. */
function Conditions({ rule }: { rule: Rule }) {
  const parts = [
    rule.classifications.length
      ? `Clasificación ${rule.classifications.map((c) => labelOf(CLASSIFICATION, c).label).join(" o ")}`
      : "Cualquier clasificación",
    RECIPIENT_LABEL[rule.recipient],
    rule.finding_types.length
      ? `Contiene ${rule.finding_types.map((f) => FINDING[f] ?? f).join(", ")}`
      : null,
    rule.channels.length
      ? `Por ${rule.channels.map((c) => labelOf(CHANNEL, c).label).join(" o ")}`
      : null,
  ].filter(Boolean);
  return (
    <Text size="sm" c="dimmed">
      {parts.join(" · ")}
    </Text>
  );
}

function RuleModal({ rule, onClose }: { rule: Rule | "new" | null; onClose: () => void }) {
  return (
    <Modal
      opened={rule !== null}
      onClose={onClose}
      size="lg"
      title={<Text fw={700}>{rule === "new" ? "Nueva regla" : "Editar regla"}</Text>}
    >
      {rule !== null && (
        <RuleForm key={rule === "new" ? "new" : rule.id} rule={rule} onClose={onClose} />
      )}
    </Modal>
  );
}

function RuleForm({ rule, onClose }: { rule: Rule | "new"; onClose: () => void }) {
  const queryClient = useQueryClient();
  const initial: RuleIn =
    rule === "new"
      ? EMPTY
      : {
          name: rule.name,
          description: rule.description,
          action: rule.action,
          message: rule.message,
          classifications: rule.classifications,
          recipient: rule.recipient,
          finding_types: rule.finding_types,
          channels: rule.channels,
          enabled: rule.enabled,
        };
  const form = useForm<RuleIn>({
    initialValues: initial,
    validate: {
      name: hasLength({ min: 3, max: 120 }, "Entre 3 y 120 caracteres"),
      message: hasLength({ min: 3, max: 300 }, "Indique el motivo que verá quien comparte"),
    },
  });
  const save = useMutation({
    mutationFn: async (body: RuleIn) =>
      rule === "new"
        ? unwrap(await api.POST("/api/v1/admin/policies", { body }))
        : unwrap(
            await api.PUT("/api/v1/admin/policies/{rule_id}", {
              params: { path: { rule_id: rule.id } },
              body,
            }),
          ),
    onSuccess: () => {
      notifications.show({ color: "green", message: "Regla guardada. El cambio quedó auditado." });
      void queryClient.invalidateQueries({ queryKey: KEY });
      onClose();
    },
  });

  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values))} noValidate>
      <Stack>
        <TextInput label="Nombre" data-autofocus {...form.getInputProps("name")} />
        <div>
          <Text size="sm" fw={500} mb={4}>
            Acción
          </Text>
          <SegmentedControl
            fullWidth
            data={[
              { value: "WARN", label: "Advertir (pide confirmación)" },
              { value: "BLOCK", label: "Bloquear" },
            ]}
            {...form.getInputProps("action")}
          />
        </div>
        <Textarea
          label="Mensaje para quien comparte"
          autosize
          minRows={2}
          {...form.getInputProps("message")}
        />
        <Text size="sm" fw={600} mt="xs">
          Condiciones (vacío = cualquiera)
        </Text>
        <MultiSelect
          label="Clasificación del documento"
          placeholder="Cualquiera"
          data={CLASSIFICATION_OPTIONS}
          comboboxProps={{ zIndex: 500 }}
          {...form.getInputProps("classifications")}
        />
        <div>
          <Text size="sm" fw={500} mb={4}>
            Destinatario
          </Text>
          <SegmentedControl
            fullWidth
            data={[
              { value: "ANY", label: "Cualquiera" },
              { value: "INTERNAL", label: "Interno" },
              { value: "EXTERNAL", label: "Externo" },
            ]}
            {...form.getInputProps("recipient")}
          />
        </div>
        <MultiSelect
          label="Datos detectados en el documento"
          description="La regla aplica si contiene al menos uno de ellos"
          placeholder="No importa"
          data={FINDING_OPTIONS}
          comboboxProps={{ zIndex: 500 }}
          {...form.getInputProps("finding_types")}
        />
        <MultiSelect
          label="Medio de envío"
          placeholder="Cualquiera"
          data={CHANNEL_OPTIONS}
          comboboxProps={{ zIndex: 500 }}
          {...form.getInputProps("channels")}
        />
        <Textarea
          label="Descripción interna"
          autosize
          minRows={1}
          {...form.getInputProps("description")}
        />
        <Switch label="Regla activa" {...form.getInputProps("enabled", { type: "checkbox" })} />
        {save.error && <Alert color="red">{save.error.message}</Alert>}
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
  );
}

export function PoliciesPage() {
  const { hasRole } = useAuth();
  const canEdit = hasRole("ADMIN");
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<Rule | "new" | null>(null);
  const rules = useQuery({
    queryKey: KEY,
    queryFn: async () => unwrap(await api.GET("/api/v1/admin/policies")),
  });
  const toggle = useMutation({
    mutationFn: async (rule: Rule) => {
      const { id, created_at, created_by, updated_at, updated_by, ...body } = rule;
      void [created_at, created_by, updated_at, updated_by];
      return unwrap(
        await api.PUT("/api/v1/admin/policies/{rule_id}", {
          params: { path: { rule_id: id } },
          body: { ...body, enabled: !rule.enabled },
        }),
      );
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: KEY }),
    onError: (e) => notifications.show({ color: "red", message: e.message }),
  });
  const remove = useMutation({
    mutationFn: async (rule: Rule) => {
      const { error, response } = await api.DELETE("/api/v1/admin/policies/{rule_id}", {
        params: { path: { rule_id: rule.id } },
      });
      if (!response.ok) throw new Error(problemMessage(error));
    },
    onSuccess: () => {
      notifications.show({ color: "green", message: "Regla eliminada. Quedó en la auditoría." });
      void queryClient.invalidateQueries({ queryKey: KEY });
    },
    onError: (e) => notifications.show({ color: "red", message: e.message }),
  });

  return (
    <>
      <PageHeader
        title="Políticas de compartición"
        description="Reglas que se evalúan antes de cada envío. Cada cambio queda registrado en la auditoría con quién lo hizo y el valor anterior."
        actions={
          canEdit && (
            <Button leftSection={<IconPlus size={16} />} onClick={() => setEditing("new")}>
              Nueva regla
            </Button>
          )
        }
      />
      <Alert variant="light" icon={<IconInfoCircle size={18} />} mb="md">
        Se evalúan todas las reglas activas y gana la más restrictiva (Bloquear sobre Advertir). Si
        ninguna aplica, el envío se permite. Además, siempre: la IA (si está activa) solo puede
        advertir, un documento que no se pudo analizar pide confirmación y "cualquiera con el
        enlace" solo se permite si ninguna regla advierte ni bloquea.
      </Alert>
      {rules.isPending ? (
        <Loader />
      ) : rules.isError ? (
        <Alert color="red">{rules.error.message}</Alert>
      ) : rules.data.length === 0 ? (
        <Paper withBorder p="xl" ta="center">
          <Text c="dimmed">No hay reglas: todos los envíos se permiten sin confirmación.</Text>
        </Paper>
      ) : (
        <Paper withBorder>
          <Table verticalSpacing="sm" highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th w={70}>Activa</Table.Th>
                <Table.Th>Regla</Table.Th>
                <Table.Th w={110}>Acción</Table.Th>
                <Table.Th>Última modificación</Table.Th>
                {canEdit && <Table.Th w={90} />}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rules.data.map((rule) => (
                <Table.Tr key={rule.id} opacity={rule.enabled ? 1 : 0.55}>
                  <Table.Td>
                    <Switch
                      checked={rule.enabled}
                      disabled={!canEdit || toggle.isPending}
                      onChange={() => toggle.mutate(rule)}
                      aria-label={`Activar ${rule.name}`}
                    />
                  </Table.Td>
                  <Table.Td>
                    <Text fw={600} size="sm">
                      {rule.name}
                    </Text>
                    <Conditions rule={rule} />
                    <Text size="xs" c="dimmed" fs="italic">
                      «{rule.message}»
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <ActionBadge action={rule.action} />
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{formatRelative(rule.updated_at)}</Text>
                    <Text size="xs" c="dimmed">
                      {rule.updated_by}
                    </Text>
                  </Table.Td>
                  {canEdit && (
                    <Table.Td>
                      <Group gap={4} wrap="nowrap">
                        <Tooltip label="Editar">
                          <ActionIcon
                            variant="subtle"
                            aria-label={`Editar ${rule.name}`}
                            onClick={() => setEditing(rule)}
                          >
                            <IconPencil size={16} />
                          </ActionIcon>
                        </Tooltip>
                        <Tooltip label="Eliminar">
                          <ActionIcon
                            variant="subtle"
                            color="red"
                            aria-label={`Eliminar ${rule.name}`}
                            onClick={() =>
                              modals.openConfirmModal({
                                title: "Eliminar regla",
                                children: (
                                  <Text size="sm">
                                    «{rule.name}» dejará de aplicarse a los próximos envíos. Si solo
                                    quieres pausarla, desactívala.
                                  </Text>
                                ),
                                labels: { confirm: "Eliminar", cancel: "Cancelar" },
                                confirmProps: { color: "red" },
                                onConfirm: () => remove.mutate(rule),
                              })
                            }
                          >
                            <IconTrash size={16} />
                          </ActionIcon>
                        </Tooltip>
                      </Group>
                    </Table.Td>
                  )}
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Paper>
      )}
      <RuleModal rule={editing} onClose={() => setEditing(null)} />
    </>
  );
}
