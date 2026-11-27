import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Group,
  List,
  Modal,
  NumberInput,
  SegmentedControl,
  Select,
  Stack,
  Stepper,
  Table,
  Text,
  Textarea,
  TextInput,
} from "@mantine/core";
import { hasLength, isNotEmpty, useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { IconCircleCheck, IconRobot, IconShieldCheck } from "@tabler/icons-react";
import { useState } from "react";
import { api, type Problem, problemMessage, type Schemas } from "../../api/client";
import { ClassificationBadge, DecisionBadge } from "../../components/badges";
import { formatDateTime } from "../../lib/format";
import { FINDING } from "../../lib/labels";

type Channel = Schemas["ShareRequest"]["channel"];
type Report = Schemas["SensitivityReport"];

interface FormValues {
  name: string;
  channel: Channel;
  email: string;
  phone: string;
  reason: string;
  expires: string;
  maxAccesses: number;
}

const EXPIRY_OPTIONS = [
  { value: "24", label: "24 horas" },
  { value: "72", label: "3 días" },
  { value: "168", label: "7 días (máximo)" },
];

function recipientOf(v: FormValues): Schemas["RecipientIn"] {
  return v.channel === "EMAIL"
    ? { name: v.name.trim(), email: v.email.trim() }
    : { name: v.name.trim(), phone: v.phone.trim() };
}

export function SensitivityReportView({ report }: { report: Report }) {
  return (
    <Stack gap="sm">
      <Group gap="xs">
        <DecisionBadge value={report.decision} />
        <ClassificationBadge value={report.classification} />
        <Badge variant="outline" color={report.recipient_external ? "orange" : "teal"}>
          {report.recipient_external ? "Destinatario externo" : "Destinatario interno"}
        </Badge>
      </Group>
      {report.reasons.length > 0 && (
        <List size="sm" spacing={4}>
          {report.reasons.map((reason) => (
            <List.Item key={reason}>{reason}</List.Item>
          ))}
        </List>
      )}
      {report.findings.length > 0 ? (
        <Table withTableBorder fz="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Dato detectado</Table.Th>
              <Table.Th>Cantidad</Table.Th>
              <Table.Th>Ejemplos (enmascarados)</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {report.findings.map((f) => (
              <Table.Tr key={f.type}>
                <Table.Td>{FINDING[f.type] ?? f.type}</Table.Td>
                <Table.Td>{f.count}</Table.Td>
                <Table.Td ff="monospace">{f.samples.join(", ")}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      ) : (
        <Text size="sm" c="dimmed">
          No se detectaron datos personales ni financieros.
        </Text>
      )}
      {report.llm && (
        <Alert
          variant="light"
          color="violet"
          icon={<IconRobot size={18} />}
          title={`Análisis asistido por IA: ${report.llm.sensitivity}`}
        >
          {report.llm.rationale}
        </Alert>
      )}
      <Text size="xs" c="dimmed">
        Motor: {report.engine}
        {report.llm_input_truncated ? " · el análisis de IA usó un extracto del documento" : ""}
      </Text>
    </Stack>
  );
}

export function ShareWizard({
  document,
  opened,
  onClose,
}: {
  document: Schemas["SourceDocument"] | null;
  opened: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [step, setStep] = useState(0);
  const [report, setReport] = useState<Report | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [result, setResult] = useState<Schemas["ShareOut"] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const form = useForm<FormValues>({
    initialValues: {
      name: "",
      channel: "EMAIL",
      email: "",
      phone: "",
      reason: "",
      expires: "72",
      maxAccesses: 3,
    },
    validate: {
      name: isNotEmpty("Ingrese el nombre del destinatario"),
      email: (value, v) =>
        v.channel === "EMAIL" && !/^\S+@\S+\.\S+$/.test(value) ? "Email inválido" : null,
      phone: (value, v) =>
        v.channel !== "EMAIL" && !/^\+?[0-9 ]{8,16}$/.test(value)
          ? "Teléfono inválido (ej: +56 9 1234 5678)"
          : null,
      reason: hasLength({ min: 3, max: 500 }, "Indique el motivo (mínimo 3 caracteres)"),
    },
  });

  const reset = () => {
    setStep(0);
    setReport(null);
    setAcknowledged(false);
    setResult(null);
    setError(null);
    form.reset();
  };
  const close = () => {
    reset();
    onClose();
  };

  const precheck = useMutation({
    mutationFn: async (values: FormValues) => {
      const { data, error } = await api.POST("/api/v1/shares/precheck", {
        body: { document_id: document!.id, recipient: recipientOf(values) },
      });
      if (!data) throw new Error(problemMessage(error));
      return data.report;
    },
    onSuccess: (r) => {
      setReport(r);
      setAcknowledged(false);
      setStep(1);
    },
    onError: (e) => setError(e.message),
  });

  const share = useMutation({
    mutationFn: async (values: FormValues) => {
      const { data, error } = await api.POST("/api/v1/shares", {
        body: {
          document_id: document!.id,
          recipient: recipientOf(values),
          channel: values.channel,
          reason: values.reason.trim(),
          expires_in_hours: Number(values.expires),
          max_accesses: values.maxAccesses,
          acknowledge_sensitive: acknowledged,
        },
      });
      if (!data) {
        const problem = error as Problem;
        if (problem?.report) setReport(problem.report);
        throw new Error(problemMessage(error));
      }
      return data;
    },
    onSuccess: (share) => {
      setResult(share);
      setStep(2);
      void queryClient.invalidateQueries({ queryKey: ["shares"] });
      void queryClient.invalidateQueries({ queryKey: ["stats"] });
      notifications.show({
        color: "green",
        message: "Documento compartido. El destinatario recibió el enlace.",
      });
    },
    onError: (e) => setError(e.message),
  });

  const blocked = report?.decision === "BLOCK";
  const needsAck = report?.decision === "WARN";

  return (
    <Modal
      opened={opened}
      onClose={close}
      size="lg"
      title={<Text fw={700}>Compartir: {document?.title}</Text>}
    >
      <Stepper active={step} size="sm" mb="md" allowNextStepsSelect={false}>
        <Stepper.Step label="Destinatario" />
        <Stepper.Step label="Revisión de seguridad" />
        <Stepper.Step label="Enviado" />
      </Stepper>
      {error && (
        <Alert color="red" mb="md" withCloseButton onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {step === 0 && (
        <form
          onSubmit={form.onSubmit((values) => {
            setError(null);
            precheck.mutate(values);
          })}
          noValidate
        >
          <Stack>
            <TextInput label="Nombre del destinatario" {...form.getInputProps("name")} />
            <div>
              <Text size="sm" fw={500} mb={4}>
                Medio de envío
              </Text>
              <SegmentedControl
                fullWidth
                data={[
                  { value: "EMAIL", label: "Email" },
                  { value: "WHATSAPP", label: "WhatsApp" },
                  { value: "SMS", label: "SMS" },
                ]}
                {...form.getInputProps("channel")}
              />
            </div>
            {form.values.channel === "EMAIL" ? (
              <TextInput
                label="Email del destinatario"
                type="email"
                {...form.getInputProps("email")}
              />
            ) : (
              <TextInput
                label="Teléfono del destinatario"
                placeholder="+56 9 1234 5678"
                {...form.getInputProps("phone")}
              />
            )}
            <Textarea
              label="Motivo"
              description="Queda registrado en la auditoría"
              autosize
              minRows={2}
              {...form.getInputProps("reason")}
            />
            <Group grow>
              <Select
                label="Vigencia del enlace"
                data={EXPIRY_OPTIONS}
                allowDeselect={false}
                {...form.getInputProps("expires")}
              />
              <NumberInput
                label="Descargas permitidas"
                min={1}
                max={20}
                {...form.getInputProps("maxAccesses")}
              />
            </Group>
            <Group justify="flex-end">
              <Button variant="default" onClick={close}>
                Cancelar
              </Button>
              <Button
                type="submit"
                loading={precheck.isPending}
                leftSection={<IconShieldCheck size={16} />}
              >
                Revisar seguridad
              </Button>
            </Group>
          </Stack>
        </form>
      )}

      {step === 1 && report && (
        <Stack>
          <SensitivityReportView report={report} />
          {blocked && (
            <Alert color="red" title="No es posible compartir">
              La política de la organización impide enviar este documento a este destinatario. El
              intento quedó registrado.
            </Alert>
          )}
          {needsAck && (
            <Checkbox
              checked={acknowledged}
              onChange={(e) => setAcknowledged(e.currentTarget.checked)}
              label="Revisé los hallazgos y confirmo que corresponde compartir este documento"
            />
          )}
          <Group justify="space-between">
            <Button variant="default" onClick={() => setStep(0)}>
              Volver
            </Button>
            <Button
              disabled={blocked || (needsAck && !acknowledged)}
              loading={share.isPending}
              onClick={() => {
                setError(null);
                share.mutate(form.values);
              }}
            >
              Compartir
            </Button>
          </Group>
        </Stack>
      )}

      {step === 2 && result && (
        <Stack align="center" ta="center" gap="xs">
          <IconCircleCheck size={48} color="var(--mantine-color-green-6)" />
          <Text fw={600}>
            Enlace enviado a {result.recipient.name} ({result.recipient.contact})
          </Text>
          <Text size="sm" c="dimmed">
            Vence el {formatDateTime(result.expires_at)} · {result.max_accesses} descarga(s) ·
            notificación {result.notification_status === "SENT" ? "entregada" : "con error"}
          </Text>
          <Text size="xs" c="dimmed" maw={420}>
            Por seguridad el enlace no se muestra aquí: solo lo recibe el destinatario, quien además
            deberá validar un código.
          </Text>
          <Button mt="sm" onClick={close}>
            Listo
          </Button>
        </Stack>
      )}
    </Modal>
  );
}
