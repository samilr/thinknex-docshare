import { BarChart, DonutChart } from "@mantine/charts";
import {
  Alert,
  Badge,
  Card,
  Group,
  SimpleGrid,
  Skeleton,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import {
  IconAlertTriangle,
  IconDownload,
  IconSend,
  IconShieldX,
  IconUsers,
} from "@tabler/icons-react";
import type { ComponentType } from "react";
import { api, unwrap } from "../api/client";
import { useAuth } from "../auth/context";
import { PageHeader } from "../components/PageHeader";
import { formatDay } from "../lib/format";
import { CHANNEL, labelOf, SHARE_STATUS } from "../lib/labels";

function Kpi({
  label,
  value,
  icon: Icon,
  color,
  hint,
}: {
  label: string;
  value: number | string;
  icon: ComponentType<{ size?: number }>;
  color: string;
  hint?: string;
}) {
  return (
    <Card withBorder radius="lg" padding="lg">
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Stack gap={2} style={{ minWidth: 0 }}>
          <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
            {label}
          </Text>
          <Text fz={30} fw={700} lh={1.1}>
            {value}
          </Text>
          {hint && (
            <Text size="xs" c="dimmed">
              {hint}
            </Text>
          )}
        </Stack>
        <ThemeIcon variant="light" color={color} size={40} radius="md" style={{ flexShrink: 0 }}>
          <Icon size={22} />
        </ThemeIcon>
      </Group>
    </Card>
  );
}

export function DashboardPage() {
  const { user } = useAuth();
  const stats = useQuery({
    queryKey: ["stats"],
    queryFn: async () => unwrap(await api.GET("/api/v1/stats")),
  });

  if (stats.isError) return <Alert color="red">{stats.error.message}</Alert>;
  const data = stats.data;
  const active = data?.shares_by_status.ACTIVE ?? 0;
  const accesses = data?.accesses_by_day.reduce((sum, d) => sum + d.count, 0) ?? 0;

  return (
    <>
      <PageHeader
        title={`Hola, ${user?.name.split(" ")[0] ?? ""}`}
        description={
          data?.scope === "all"
            ? "Indicadores de toda la plataforma."
            : "Indicadores de los documentos que has compartido."
        }
        actions={
          <Badge variant="light">{data?.scope === "all" ? "Vista global" : "Mis envíos"}</Badge>
        }
      />
      <Skeleton visible={stats.isPending} radius="lg">
        <SimpleGrid cols={{ base: 1, xs: 2, md: data?.users_active != null ? 5 : 4 }} mb="lg">
          <Kpi
            label="Envíos"
            value={data?.shares_total ?? 0}
            icon={IconSend}
            color="blue"
            hint={`${active} activos`}
          />
          <Kpi label="Descargas (7 días)" value={accesses} icon={IconDownload} color="green" />
          <Kpi
            label="Con datos sensibles"
            value={data?.sensitive_acknowledged ?? 0}
            icon={IconAlertTriangle}
            color="yellow"
            hint="confirmados al compartir"
          />
          <Kpi
            label="Bloqueos y denegaciones"
            value={(data?.blocked_attempts_30d ?? 0) + (data?.denied_accesses_30d ?? 0)}
            icon={IconShieldX}
            color="red"
            hint="últimos 30 días"
          />
          {data?.users_active != null && (
            <Kpi
              label="Usuarios activos"
              value={data.users_active}
              icon={IconUsers}
              color="grape"
            />
          )}
        </SimpleGrid>
      </Skeleton>

      <SimpleGrid cols={{ base: 1, lg: 3 }}>
        <Card withBorder radius="lg" padding="lg" style={{ gridColumn: "span 2" }}>
          <Title order={5} mb="md">
            Descargas por día
          </Title>
          <BarChart
            h={240}
            data={(data?.accesses_by_day ?? []).map((d) => ({
              day: formatDay(d.day),
              Descargas: d.count,
            }))}
            dataKey="day"
            series={[{ name: "Descargas", color: "blue.6" }]}
            tickLine="y"
            yAxisProps={{ allowDecimals: false }}
          />
        </Card>
        <Card withBorder radius="lg" padding="lg">
          <Title order={5} mb="md">
            Envíos por canal
          </Title>
          {data && Object.keys(data.shares_by_channel).length > 0 ? (
            <Stack align="center">
              <DonutChart
                size={170}
                thickness={26}
                withLabelsLine={false}
                data={Object.entries(data.shares_by_channel).map(([channel, value]) => ({
                  name: labelOf(CHANNEL, channel).label,
                  value,
                  color: `${labelOf(CHANNEL, channel).color}.6`,
                }))}
              />
              <Group gap="xs">
                {Object.entries(data.shares_by_status).map(([status, count]) => (
                  <Badge key={status} color={labelOf(SHARE_STATUS, status).color} variant="light">
                    {labelOf(SHARE_STATUS, status).label}: {count}
                  </Badge>
                ))}
              </Group>
            </Stack>
          ) : (
            <Text c="dimmed" size="sm">
              Aún no hay envíos.
            </Text>
          )}
        </Card>
      </SimpleGrid>

      <Card withBorder radius="lg" padding="lg" mt="lg">
        <Title order={5} mb="sm">
          Documentos más compartidos
        </Title>
        {data?.top_documents.length ? (
          <Table>
            <Table.Tbody>
              {data.top_documents.map((doc) => (
                <Table.Tr key={doc.source_id}>
                  <Table.Td w={90}>
                    <Text size="sm" c="dimmed" ff="monospace">
                      {doc.source_id}
                    </Text>
                  </Table.Td>
                  <Table.Td>{doc.title}</Table.Td>
                  <Table.Td ta="right">
                    <Badge variant="light">{doc.shares}</Badge>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        ) : (
          <Text c="dimmed" size="sm">
            Sin datos todavía.
          </Text>
        )}
      </Card>
    </>
  );
}
