import {
  Alert,
  Badge,
  Button,
  Card,
  CopyButton,
  Group,
  Skeleton,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { useQuery } from "@tanstack/react-query";
import { IconExternalLink, IconSearch } from "@tabler/icons-react";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { ChannelLabel } from "../components/badges";
import { PageHeader } from "../components/PageHeader";
import { formatDateTime } from "../lib/format";

const LINK_RE = /https?:\/\/\S+\/s\/[A-Za-z0-9_-]+/;
const OTP_RE = /\b(\d{6})\b/;

export function InboxPage() {
  const [search, setSearch] = useState("");
  const [to] = useDebouncedValue(search.trim(), 300);
  const inbox = useQuery({
    queryKey: ["inbox", to],
    refetchInterval: 5000,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/admin/inbox", {
          params: { query: { to: to || undefined, limit: 50 } },
        }),
      ),
  });

  return (
    <>
      <PageHeader title="Bandeja simulada" />
      <TextInput
        placeholder="Filtrar por destinatario…"
        leftSection={<IconSearch size={16} />}
        value={search}
        onChange={(e) => setSearch(e.currentTarget.value)}
        mb="md"
        maw={420}
      />
      {inbox.isError && <Alert color="red">{inbox.error.message}</Alert>}
      <Skeleton visible={inbox.isPending}>
        <Stack>
          {inbox.data?.items.length === 0 && <Text c="dimmed">No hay mensajes todavía.</Text>}
          {inbox.data?.items.map((m) => {
            const link = m.kind === "LINK" ? LINK_RE.exec(m.body)?.[0] : undefined;
            const otp = m.kind === "OTP" ? OTP_RE.exec(m.body)?.[1] : undefined;
            return (
              <Card key={m.id} withBorder radius="lg" padding="md">
                <Group justify="space-between" mb={6} wrap="wrap">
                  <Group gap="sm">
                    <ChannelLabel channel={m.channel} />
                    <Text size="sm" fw={600}>
                      {m.to_address}
                    </Text>
                    <Badge size="sm" variant="light" color={m.kind === "OTP" ? "orange" : "blue"}>
                      {m.kind === "OTP" ? "Código" : "Enlace"}
                    </Badge>
                    {m.delivered_real && (
                      <Badge size="sm" color="green" variant="outline">
                        entregado por el proveedor
                      </Badge>
                    )}
                  </Group>
                  <Text size="xs" c="dimmed">
                    {formatDateTime(m.created_at)}
                  </Text>
                </Group>
                <Text size="sm" fw={500}>
                  {m.subject}
                </Text>
                <Text size="sm" c="dimmed" style={{ whiteSpace: "pre-wrap" }}>
                  {m.body}
                </Text>
                {(link || otp) && (
                  <Group mt="sm">
                    {link && (
                      <Button
                        component="a"
                        href={link}
                        target="_blank"
                        rel="noopener noreferrer"
                        size="xs"
                        leftSection={<IconExternalLink size={14} />}
                      >
                        Abrir como destinatario
                      </Button>
                    )}
                    {otp && (
                      <CopyButton value={otp}>
                        {({ copied, copy }) => (
                          <Button
                            size="xs"
                            variant="light"
                            color={copied ? "teal" : "orange"}
                            onClick={copy}
                          >
                            {copied ? "Código copiado" : `Copiar código ${otp}`}
                          </Button>
                        )}
                      </CopyButton>
                    )}
                  </Group>
                )}
              </Card>
            );
          })}
        </Stack>
      </Skeleton>
    </>
  );
}
