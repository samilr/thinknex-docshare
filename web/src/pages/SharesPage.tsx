import {
  Alert,
  Card,
  Group,
  Pagination,
  SegmentedControl,
  Select,
  Skeleton,
  Table,
  Text,
  TextInput,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { useAuth } from "../auth/context";
import { ChannelLabel, StatusBadge } from "../components/badges";
import { PageHeader } from "../components/PageHeader";
import { ShareDrawer } from "../features/share/ShareDrawer";
import { formatDateTime, formatRelative } from "../lib/format";
import { CHANNEL, labelOf, PERMISSION, SHARE_STATUS } from "../lib/labels";

const PAGE_SIZE = 20;
type Scope = "mine" | "all";
type StatusValue = "ACTIVE" | "REVOKED" | "EXPIRED" | "LOCKED" | "EXHAUSTED";
type ChannelValue = "EMAIL" | "WHATSAPP" | "SMS";

export function SharesPage() {
  const { hasRole } = useAuth();
  const oversight = hasRole("ADMIN", "AUDITOR");
  const [scope, setScope] = useState<Scope>(oversight && !hasRole("SHARER") ? "all" : "mine");
  const [status, setStatus] = useState<StatusValue | null>(null);
  const [channel, setChannel] = useState<ChannelValue | null>(null);
  const [documentFilter, setDocumentFilter] = useState("");
  const [documentId] = useDebouncedValue(documentFilter.trim(), 300);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string | null>(null);

  const shares = useQuery({
    queryKey: ["shares", "list", scope, status, channel, documentId, page],
    placeholderData: keepPreviousData,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/shares", {
          params: {
            query: {
              scope,
              status: status ?? undefined,
              channel: channel ?? undefined,
              document_id: documentId || undefined,
              limit: PAGE_SIZE,
              offset: (page - 1) * PAGE_SIZE,
            },
          },
        }),
      ),
  });
  const totalPages = Math.max(1, Math.ceil((shares.data?.total ?? 0) / PAGE_SIZE));

  return (
    <>
      <PageHeader
        title="Envíos"
        actions={
          oversight && hasRole("SHARER") ? (
            <SegmentedControl
              value={scope}
              onChange={(v) => {
                setScope(v as Scope);
                setPage(1);
              }}
              data={[
                { value: "mine", label: "Míos" },
                { value: "all", label: "Todos" },
              ]}
            />
          ) : undefined
        }
      />
      <Group mb="md" gap="sm" wrap="wrap">
        <Select
          placeholder="Estado"
          clearable
          w={170}
          value={status}
          onChange={(v) => {
            setStatus(v as StatusValue | null);
            setPage(1);
          }}
          data={Object.entries(SHARE_STATUS).map(([value, { label }]) => ({ value, label }))}
        />
        <Select
          placeholder="Medio"
          clearable
          w={160}
          value={channel}
          onChange={(v) => {
            setChannel(v as ChannelValue | null);
            setPage(1);
          }}
          data={Object.entries(CHANNEL).map(([value, { label }]) => ({ value, label }))}
        />
        <TextInput
          placeholder="ID de documento (ej: doc-003)"
          w={240}
          value={documentFilter}
          onChange={(e) => {
            setDocumentFilter(e.currentTarget.value);
            setPage(1);
          }}
        />
      </Group>
      {shares.isError && <Alert color="red">{shares.error.message}</Alert>}
      <Card withBorder radius="lg" p={0}>
        <Skeleton visible={shares.isPending}>
          <Table.ScrollContainer minWidth={860}>
            <Table highlightOnHover verticalSpacing="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Documento</Table.Th>
                  <Table.Th>Destinatario</Table.Th>
                  <Table.Th>Medio</Table.Th>
                  <Table.Th>Estado</Table.Th>
                  <Table.Th>Descargas</Table.Th>
                  <Table.Th>Vence</Table.Th>
                  {scope === "all" && <Table.Th>Compartido por</Table.Th>}
                  <Table.Th>Creado</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {shares.data?.items.map((s) => (
                  <Table.Tr
                    key={s.id}
                    style={{ cursor: "pointer" }}
                    onClick={() => setSelected(s.id)}
                  >
                    <Table.Td>
                      <Text size="sm" fw={500} lineClamp={1}>
                        {s.document.title}
                      </Text>
                      <Text size="xs" c="dimmed" ff="monospace">
                        {s.document.source_id}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{s.recipient?.name ?? "Cualquiera con el enlace"}</Text>
                      <Text size="xs" c="dimmed">
                        {s.recipient?.contact ?? labelOf(PERMISSION, s.permission).label}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <ChannelLabel channel={s.channel} />
                    </Table.Td>
                    <Table.Td>
                      <StatusBadge status={s.status} />
                    </Table.Td>
                    <Table.Td>
                      {s.access_count}/{s.max_accesses}
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{formatRelative(s.expires_at)}</Text>
                    </Table.Td>
                    {scope === "all" && (
                      <Table.Td>
                        <Text size="sm">{s.shared_by}</Text>
                      </Table.Td>
                    )}
                    <Table.Td>
                      <Text size="sm">{formatDateTime(s.created_at)}</Text>
                    </Table.Td>
                  </Table.Tr>
                ))}
                {shares.data?.items.length === 0 && (
                  <Table.Tr>
                    <Table.Td colSpan={8}>
                      <Text c="dimmed" ta="center" py="lg">
                        No hay envíos con estos filtros.
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                )}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Skeleton>
      </Card>
      <Group justify="space-between" mt="md">
        <Text size="sm" c="dimmed">
          {shares.data?.total ?? 0} envío(s)
        </Text>
        <Pagination total={totalPages} value={page} onChange={setPage} />
      </Group>
      <ShareDrawer shareId={selected} onClose={() => setSelected(null)} />
    </>
  );
}
