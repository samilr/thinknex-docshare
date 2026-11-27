import {
  Alert,
  Anchor,
  Box,
  Button,
  Center,
  Container,
  Group,
  Loader,
  Paper,
  PinInput,
  Stack,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  IconFileText,
  IconLinkOff,
  IconLock,
  IconMailForward,
  IconShieldCheck,
} from "@tabler/icons-react";
import { type ReactNode, useState } from "react";
import { useParams } from "react-router";
import { AudienceBadge, PermissionBadge } from "../../components/badges";
import { formatDateTime } from "../../lib/format";
import { AccessError, type AccessInfo, accessApi, type AccessSession } from "./accessApi";
import { DocumentViewer } from "./DocumentViewer";

export function PublicShell({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  return (
    <Box mih="100vh" bg="var(--mantine-color-gray-0)">
      <Box
        component="header"
        px="lg"
        py="sm"
        bg="white"
        style={{ borderBottom: "1px solid var(--mantine-color-default-border)" }}
      >
        <Group gap="xs">
          <ThemeIcon variant="filled" radius="md" size="md">
            <IconFileText size={18} />
          </ThemeIcon>
          <Text fw={700}>ThinkNex Docs</Text>
          <Text size="sm" c="dimmed">
            · documento compartido contigo
          </Text>
        </Group>
      </Box>
      <Container size={wide ? "lg" : 460} py="xl">
        {children}
      </Container>
      <Text ta="center" size="xs" c="dimmed" pb="md">
        Prototipo de prueba técnica · datos ficticios · no es un servicio oficial de ThinkNex.
      </Text>
    </Box>
  );
}

function Unavailable() {
  return (
    <PublicShell>
      <Paper withBorder p="xl" radius="md">
        <Stack align="center" ta="center">
          <ThemeIcon size={56} radius="xl" color="gray" variant="light">
            <IconLinkOff size={30} />
          </ThemeIcon>
          <Title order={3}>Enlace no disponible</Title>
          <Text c="dimmed" size="sm">
            El enlace no existe, venció o fue revocado.
          </Text>
        </Stack>
      </Paper>
    </PublicShell>
  );
}

function CodeStep({
  token,
  info,
  onSession,
}: {
  token: string;
  info: AccessInfo;
  onSession: (s: AccessSession) => void;
}) {
  const [code, setCode] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const send = useMutation({
    mutationFn: () => accessApi.requestCode(token),
    onSuccess: (r) => {
      setSentTo(r.sent_to);
      setError(null);
    },
    onError: (e) => setError(e.message),
  });
  const verify = useMutation({
    mutationFn: (value: string) => accessApi.verify(token, value),
    onSuccess: onSession,
    onError: (e) => {
      setCode("");
      const remaining = e instanceof AccessError ? e.problem?.remaining_attempts : undefined;
      setError(
        remaining !== undefined
          ? `Código incorrecto. Te quedan ${remaining} intento(s).`
          : e.message,
      );
    },
  });
  const locked = verify.error instanceof AccessError && verify.error.unavailable;
  if (locked) return <Unavailable />;

  return (
    <Stack>
      <Text size="sm">
        Te enviaremos un código a <b>{sentTo ?? info.destination}</b>.
      </Text>
      {error && (
        <Alert color="red" variant="light">
          {error}
        </Alert>
      )}
      {sentTo ? (
        <Stack align="center">
          <PinInput
            length={6}
            type="number"
            oneTimeCode
            value={code}
            onChange={setCode}
            onComplete={(value) => verify.mutate(value)}
            aria-label="Código de acceso"
            disabled={verify.isPending}
          />
          <Button
            fullWidth
            loading={verify.isPending}
            disabled={code.length !== 6}
            onClick={() => verify.mutate(code)}
          >
            Verificar y abrir
          </Button>
          <Anchor component="button" size="sm" onClick={() => send.mutate()}>
            Reenviar código
          </Anchor>
        </Stack>
      ) : (
        <Button
          leftSection={<IconMailForward size={16} />}
          loading={send.isPending}
          onClick={() => send.mutate()}
        >
          Enviarme el código
        </Button>
      )}
    </Stack>
  );
}

export function RecipientPage() {
  const { token = "" } = useParams();
  const [session, setSession] = useState<AccessSession | null>(null);
  const info = useQuery({
    queryKey: ["access", token],
    queryFn: () => accessApi.info(token),
    retry: false,
    staleTime: Infinity,
  });
  const open = useMutation({
    mutationFn: () => accessApi.open(token),
    onSuccess: setSession,
  });

  if (info.isPending) {
    return (
      <PublicShell>
        <Center py="xl">
          <Loader />
        </Center>
      </PublicShell>
    );
  }
  if (info.isError || (open.error instanceof AccessError && open.error.unavailable)) {
    return <Unavailable />;
  }

  if (session) {
    return (
      <PublicShell wide>
        <DocumentViewer token={token} session={session} onEnded={() => setSession(null)} />
      </PublicShell>
    );
  }

  const data = info.data;
  return (
    <PublicShell>
      <Paper withBorder p="xl" radius="md">
        <Stack>
          <Group gap="sm" wrap="nowrap">
            <ThemeIcon size={44} radius="xl" variant="light">
              {data.requires_code ? <IconLock size={24} /> : <IconShieldCheck size={24} />}
            </ThemeIcon>
            <div>
              <Text fw={700}>{data.shared_by} compartió un documento contigo</Text>
              {data.document_title && (
                <Text size="sm" c="dimmed">
                  {data.document_title}
                </Text>
              )}
            </div>
          </Group>
          <Group gap={6}>
            <PermissionBadge value={data.permission} />
            <AudienceBadge value={data.audience} />
          </Group>
          <Text size="xs" c="dimmed">
            Disponible hasta el {formatDateTime(data.expires_at)}.
          </Text>
          {data.requires_code ? (
            <CodeStep token={token} info={data} onSession={setSession} />
          ) : (
            <>
              {open.error && <Alert color="red">{open.error.message}</Alert>}
              <Button loading={open.isPending} onClick={() => open.mutate()}>
                Abrir documento
              </Button>
            </>
          )}
        </Stack>
      </Paper>
    </PublicShell>
  );
}
