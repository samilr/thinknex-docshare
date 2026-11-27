import { Button, Center, Stack, Text, Title } from "@mantine/core";
import { Link } from "react-router";

export function NotFoundPage() {
  return (
    <Center mih="60vh">
      <Stack align="center" gap="xs">
        <Title order={2}>Página no encontrada</Title>
        <Text c="dimmed">La dirección no existe o fue movida.</Text>
        <Button component={Link} to="/" variant="light">
          Ir al resumen
        </Button>
      </Stack>
    </Center>
  );
}
