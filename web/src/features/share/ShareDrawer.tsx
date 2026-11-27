import {
  Alert,
  Badge,
  Button,
  Divider,
  Drawer,
  Group,
  Loader,
  SimpleGrid,
  Stack,
  Text,
  Timeline,
} from "@mantine/core";
import { modals } from "@mantine/modals";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { IconBan, IconPoint, IconRefresh } from "@tabler/icons-react";
import { type ReactNode, useState } from "react";
import { api, problemMessage, unwrap } from "../../api/client";
import { useAuth } from "../../auth/context";
import {
  AudienceBadge,
  ChannelLabel,
  ClassificationBadge,
  DecisionBadge,
  PermissionBadge,
  StatusBadge,
} from "../../components/badges";
import { formatDateTime } from "../../lib/format";
import { EVENT, EVENT_COLOR, FINDING } from "../../lib/labels";
import { LinkReveal } from "./LinkReveal";

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

export function ShareDrawer({ shareId, onClose }: { shareId: string | null; onClose: () => void }) {
  const { user, hasRole } = useAuth();
  const queryClient = useQueryClient();
  const share = useQuery({
    queryKey: ["shares", shareId],
    enabled: !!shareId,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/shares/{share_id}", { params: { path: { share_id: shareId! } } }),
      ),
  });
  const timeline = useQuery({
    queryKey: ["shares", shareId, "timeline"],
    enabled: !!shareId,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/shares/{share_id}/timeline", {
          params: { path: { share_id: shareId! } },
        }),
      ),
  });
  const [newLink, setNewLink] = useState<{ shareId: string; link: string } | null>(null);
  const rotate = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST("/api/v1/shares/{share_id}/link", {
          params: { path: { share_id: shareId! } },
        }),
      ),
    onSuccess: (data) => {
      if (data.link) setNewLink({ shareId: data.id, link: data.link });
      void queryClient.invalidateQueries({ queryKey: ["shares", shareId, "timeline"] });
    },
    onError: (e) => notifications.show({ color: "red", message: e.message }),
  });
  const revoke = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/api/v1/shares/{share_id}/revoke", {
        params: { path: { share_id: shareId! } },
      });
      if (!data) throw new Error(problemMessage(error));
      return data;
    },
    onSuccess: () => {
      notifications.show({
        color: "green",
        message: "Share revocado. El enlace dejó de funcionar.",
      });
      void queryClient.invalidateQueries({ queryKey: ["shares"] });
      void queryClient.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: (e) => notifications.show({ color: "red", message: e.message }),
  });

  const s = share.data;
  const canRevoke = s?.status === "ACTIVE" && (s.shared_by === user?.email || hasRole("ADMIN"));
  const canRotate = canRevoke && s?.channel === "LINK";
  const visibleLink = newLink && newLink.shareId === shareId ? newLink.link : null;
  const recipientName = s?.recipient?.name ?? "quien tenga el enlace";
  const report = s?.sensitivity_report as
    { findings?: { type: string; count: number }[] } | undefined;

  return (
    <Drawer
      opened={!!shareId}
      onClose={onClose}
      position="right"
      size="lg"
      title={<Text fw={700}>Detalle del envío</Text>}
    >
      {share.isPending && <Loader />}
      {share.isError && <Alert color="red">{share.error.message}</Alert>}
      {s && (
        <Stack>
          <Group justify="space-between">
            <Text fw={600} size="lg">
              {s.document.title}
            </Text>
            <StatusBadge status={s.status} />
          </Group>
          <SimpleGrid cols={2} spacing="md">
            <Field label="Destinatario">
              {s.recipient ? (
                <>
                  <Text size="sm">{s.recipient.name}</Text>
                  <Text size="xs" c="dimmed">
                    {s.recipient.contact} · {s.recipient.is_external ? "externo" : "interno"}
                  </Text>
                </>
              ) : (
                <Text size="sm">Cualquier persona con el enlace</Text>
              )}
            </Field>
            <Field label="Medio">
              <ChannelLabel channel={s.channel} />
            </Field>
            <Field label="Compartido por">
              <Text size="sm">{s.shared_by}</Text>
            </Field>
            <Field label="Fecha">
              <Text size="sm">{formatDateTime(s.created_at)}</Text>
            </Field>
            <Field label="Vence">
              <Text size="sm">{formatDateTime(s.expires_at)}</Text>
            </Field>
            <Field label="Permiso">
              <Group gap={6}>
                <PermissionBadge value={s.permission} />
                <AudienceBadge value={s.audience} />
              </Group>
            </Field>
            <Field label="Accesos">
              <Text size="sm">
                {s.access_count} de {s.max_accesses}
              </Text>
            </Field>
            <Field label="Clasificación">
              <ClassificationBadge value={s.document.classification} />
            </Field>
            <Field label="Evaluación">
              <DecisionBadge value={s.sensitivity_decision} />
            </Field>
          </SimpleGrid>
          <Field label="Motivo">
            <Text size="sm">{s.reason}</Text>
          </Field>
          {report?.findings && report.findings.length > 0 && (
            <Group gap={6}>
              {report.findings.map((f) => (
                <Badge key={f.type} variant="outline" color="orange">
                  {FINDING[f.type] ?? f.type}: {f.count}
                </Badge>
              ))}
            </Group>
          )}
          <Field label="Integridad">
            <Text size="xs" ff="monospace" c="dimmed" style={{ wordBreak: "break-all" }}>
              sha256 {s.document.sha256}
            </Text>
          </Field>
          {visibleLink && <LinkReveal link={visibleLink} />}
          {canRotate && (
            <Button
              variant="light"
              leftSection={<IconRefresh size={16} />}
              loading={rotate.isPending}
              onClick={() =>
                modals.openConfirmModal({
                  title: "Generar nuevo enlace",
                  zIndex: 400,
                  children: (
                    <Text size="sm">
                      Se creará un enlace nuevo y el actual dejará de funcionar de inmediato. Úsalo
                      si perdiste el enlace o si se compartió con quien no debía.
                    </Text>
                  ),
                  labels: { confirm: "Generar", cancel: "Cancelar" },
                  onConfirm: () => rotate.mutate(),
                })
              }
            >
              Generar nuevo enlace
            </Button>
          )}
          {canRevoke && (
            <Button
              color="red"
              variant="light"
              leftSection={<IconBan size={16} />}
              loading={revoke.isPending}
              onClick={() =>
                modals.openConfirmModal({
                  title: "Revocar envío",
                  children: (
                    <Text size="sm">
                      El enlace dejará de funcionar de inmediato para {recipientName}. Esta acción
                      queda auditada y no se puede deshacer.
                    </Text>
                  ),
                  labels: { confirm: "Revocar", cancel: "Cancelar" },
                  confirmProps: { color: "red" },
                  onConfirm: () => revoke.mutate(),
                })
              }
            >
              Revocar acceso
            </Button>
          )}
          <Divider label="Línea de tiempo" labelPosition="left" />
          {timeline.isPending ? (
            <Loader size="sm" />
          ) : (
            <Timeline bulletSize={18} lineWidth={2}>
              {timeline.data?.map((e) => (
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
                  <Text size="xs" c="dimmed">
                    {formatDateTime(e.occurred_at)} · {e.actor ?? e.actor_type}
                    {e.ip ? ` · IP ${e.ip}` : ""}
                  </Text>
                  {typeof e.metadata.reason === "string" && (
                    <Text size="xs">Causa: {e.metadata.reason}</Text>
                  )}
                </Timeline.Item>
              ))}
            </Timeline>
          )}
        </Stack>
      )}
    </Drawer>
  );
}
