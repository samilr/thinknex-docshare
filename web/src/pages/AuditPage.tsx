import {
  Alert,
  Badge,
  Button,
  Card,
  Code,
  Group,
  Modal,
  Pagination,
  Select,
  Skeleton,
  Table,
  Text,
  TextInput,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { IconDownload, IconShieldCheck, IconShieldX } from "@tabler/icons-react";
import { useState } from "react";
import { useSearchParams } from "react-router";
import { api, type Schemas, unwrap } from "../api/client";
import type { paths } from "../api/schema";
import { ChannelLabel } from "../components/badges";
import { PageHeader } from "../components/PageHeader";
import { downloadText, formatDateTime, toCsv } from "../lib/format";
import { eventSummary } from "../lib/events";
import { CHANNEL, EVENT, EVENT_COLOR } from "../lib/labels";

const PAGE_SIZE = 50;
type AuditQuery = NonNullable<paths["/api/v1/audit"]["get"]["parameters"]["query"]>;
type Event = Schemas["AuditEventOut"];

function IntegrityBanner() {
  const verify = useQuery({
    queryKey: ["audit", "verify"],
    queryFn: async () => unwrap(await api.GET("/api/v1/audit/verify")),
  });
  if (verify.isPending) return <Skeleton h={52} radius="md" mb="md" />;
  if (verify.isError)
    return (
      <Alert color="red" mb="md">
        {verify.error.message}
      </Alert>
    );
  const v = verify.data;
  return v.valid ? (
    <Alert
      color="green"
      icon={<IconShieldCheck size={20} />}
      mb="md"
      title="Cadena de auditoría íntegra"
    >
      {v.events_checked} eventos verificados. Último hash <Code>{v.last_hash.slice(0, 16)}…</Code>
    </Alert>
  ) : (
    <Alert color="red" icon={<IconShieldX size={20} />} mb="md" title="Se detectó una alteración">
      La cadena se rompe en el evento #{v.first_broken_event_id}. Revise el acceso a la base de
      datos.
    </Alert>
  );
}

export function AuditPage() {
  const [params] = useSearchParams();
  const [documentFilter, setDocumentFilter] = useState(params.get("documento") ?? "");
  const [documentId] = useDebouncedValue(documentFilter.trim(), 300);
  const [eventType, setEventType] = useState<string | null>(params.get("evento"));
  const [channel, setChannel] = useState<string | null>(null);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const [detail, setDetail] = useState<Event | null>(null);
  const [exporting, setExporting] = useState(false);

  const query: AuditQuery = {
    document_id: documentId || undefined,
    event_type: (eventType ?? undefined) as AuditQuery["event_type"],
    channel: (channel ?? undefined) as AuditQuery["channel"],
    from: from ? new Date(`${from}T00:00:00`).toISOString() : undefined,
    to: to ? new Date(`${to}T23:59:59`).toISOString() : undefined,
  };
  const events = useQuery({
    queryKey: ["audit", query, page],
    placeholderData: keepPreviousData,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/audit", {
          params: { query: { ...query, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE } },
        }),
      ),
  });

  const exportCsv = async () => {
    setExporting(true);
    try {
      const data = unwrap(
        await api.GET("/api/v1/audit", { params: { query: { ...query, limit: 500 } } }),
      );
      const rows = data.items.map((e) => ({
        id: e.id,
        fecha: e.occurred_at,
        evento: e.event_type,
        actor: e.actor ?? e.actor_type,
        canal: e.channel,
        share_id: e.share_id,
        ip: e.ip,
        metadata: e.metadata,
        hash: e.hash,
      }));
      downloadText(`auditoria-${new Date().toISOString().slice(0, 10)}.csv`, toCsv(rows));
      if (data.total > 500)
        notifications.show({ message: "Se exportaron los 500 eventos más recientes." });
    } catch (e) {
      notifications.show({ color: "red", message: (e as Error).message });
    } finally {
      setExporting(false);
    }
  };

  const totalPages = Math.max(1, Math.ceil((events.data?.total ?? 0) / PAGE_SIZE));
  const resetPage =
    <T,>(setter: (v: T) => void) =>
    (v: T) => {
      setter(v);
      setPage(1);
    };

  return (
    <>
      <PageHeader
        title="Auditoría"
        actions={
          <Button
            variant="default"
            leftSection={<IconDownload size={16} />}
            loading={exporting}
            onClick={exportCsv}
          >
            Exportar CSV
          </Button>
        }
      />
      <IntegrityBanner />
      <Group mb="md" gap="sm" wrap="wrap" align="flex-end">
        <TextInput
          label="Documento"
          placeholder="doc-003"
          w={150}
          value={documentFilter}
          onChange={(e) => resetPage(setDocumentFilter)(e.currentTarget.value)}
        />
        <Select
          label="Evento"
          placeholder="Todos"
          clearable
          searchable
          w={230}
          value={eventType}
          onChange={resetPage(setEventType)}
          data={Object.entries(EVENT).map(([value, label]) => ({ value, label }))}
        />
        <Select
          label="Medio"
          placeholder="Todos"
          clearable
          w={140}
          value={channel}
          onChange={resetPage(setChannel)}
          data={Object.entries(CHANNEL).map(([value, { label }]) => ({ value, label }))}
        />
        <TextInput
          label="Desde"
          type="date"
          value={from}
          onChange={(e) => resetPage(setFrom)(e.currentTarget.value)}
        />
        <TextInput
          label="Hasta"
          type="date"
          value={to}
          onChange={(e) => resetPage(setTo)(e.currentTarget.value)}
        />
      </Group>
      {events.isError && <Alert color="red">{events.error.message}</Alert>}
      <Card withBorder radius="lg" p={0}>
        <Skeleton visible={events.isPending}>
          <Table.ScrollContainer minWidth={900}>
            <Table highlightOnHover verticalSpacing="xs" fz="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>#</Table.Th>
                  <Table.Th>Fecha</Table.Th>
                  <Table.Th>Evento</Table.Th>
                  <Table.Th>Quién</Table.Th>
                  <Table.Th>Medio</Table.Th>
                  <Table.Th>IP</Table.Th>
                  <Table.Th>Detalle</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {events.data?.items.map((e) => (
                  <Table.Tr key={e.id} style={{ cursor: "pointer" }} onClick={() => setDetail(e)}>
                    <Table.Td c="dimmed">{e.id}</Table.Td>
                    <Table.Td style={{ whiteSpace: "nowrap" }}>
                      {formatDateTime(e.occurred_at)}
                    </Table.Td>
                    <Table.Td>
                      <Badge
                        variant="light"
                        color={EVENT_COLOR[e.event_type] ?? "blue"}
                        miw="max-content"
                      >
                        {EVENT[e.event_type] ?? e.event_type}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      {e.actor ?? e.actor_type}
                      {typeof e.metadata.impersonated_by === "string" && (
                        <Text size="xs" c="orange">
                          vía {e.metadata.impersonated_by}
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>{e.channel ? <ChannelLabel channel={e.channel} /> : "—"}</Table.Td>
                    <Table.Td ff="monospace">{e.ip ?? "—"}</Table.Td>
                    <Table.Td>
                      <Text size="xs" c="dimmed" lineClamp={1} maw={260}>
                        {eventSummary(e)}
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Skeleton>
      </Card>
      <Group justify="space-between" mt="md">
        <Text size="sm" c="dimmed">
          {events.data?.total ?? 0} evento(s)
        </Text>
        <Pagination total={totalPages} value={page} onChange={setPage} />
      </Group>
      <Modal
        opened={!!detail}
        onClose={() => setDetail(null)}
        size="lg"
        title={`Evento #${detail?.id ?? ""}`}
      >
        {detail && (
          <Code block style={{ whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
            {JSON.stringify(detail, null, 2)}
          </Code>
        )}
      </Modal>
    </>
  );
}
