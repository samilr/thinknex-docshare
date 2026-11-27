import { Button, Center, Code, Group, Loader, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { isRouteErrorResponse, useRouteError } from "react-router";
import { isChunkLoadError, reloadOnceForNewVersion } from "../lib/staleChunks";

/** Pantalla de error de ruta: recupera solo las versiones viejas y explica el resto. */
export function RouteErrorPage() {
  const error = useRouteError();
  const staleVersion = isChunkLoadError(error);
  const [reloading] = useState(() => staleVersion && reloadOnceForNewVersion());

  useEffect(() => {
    if (!reloading) console.error(error);
  }, [error, reloading]);

  if (reloading) {
    return (
      <Center h="100vh">
        <Stack align="center" gap="xs">
          <Loader />
          <Text c="dimmed">Hay una versión nueva del portal. Actualizando…</Text>
        </Stack>
      </Center>
    );
  }

  const detail = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : null;

  return (
    <Center mih="100vh" p="md">
      <Stack align="center" gap="sm" maw={480} ta="center">
        <ThemeIcon size={56} radius="xl" variant="light" color="orange">
          <IconAlertTriangle size={30} />
        </ThemeIcon>
        <Title order={3}>
          {staleVersion ? "El portal se actualizó" : "Algo no salió como esperábamos"}
        </Title>
        <Text c="dimmed">
          {staleVersion
            ? "Se publicó una versión nueva mientras tenías esta pestaña abierta. Recarga para continuar."
            : "Recarga la página. Si el problema persiste, vuelve al inicio."}
        </Text>
        {detail && !staleVersion && (
          <Code block style={{ whiteSpace: "pre-wrap", maxWidth: "100%" }}>
            {detail}
          </Code>
        )}
        <Group>
          <Button onClick={() => window.location.reload()}>Recargar</Button>
          <Button variant="default" onClick={() => window.location.assign("/")}>
            Ir al inicio
          </Button>
        </Group>
      </Stack>
    </Center>
  );
}
