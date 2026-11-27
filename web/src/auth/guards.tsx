import { Button, Center, Loader, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { IconLock } from "@tabler/icons-react";
import type { ReactNode } from "react";
import { Link, Navigate, useLocation } from "react-router";
import { type Role, useAuth } from "./context";

export const CHANGE_PASSWORD_PATH = "/cuenta/clave";

/** Exige sesión. Si la contraseña es temporal, obliga a cambiarla antes de continuar. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { status, user, loggedOut } = useAuth();
  const location = useLocation();
  if (status === "loading") {
    return (
      <Center h="100vh">
        <Loader aria-label="Cargando sesión" />
      </Center>
    );
  }
  if (status === "anonymous" || !user) {
    return <Navigate to="/login" replace state={loggedOut ? null : { from: location.pathname }} />;
  }
  if (user.must_change_password && location.pathname !== CHANGE_PASSWORD_PATH) {
    return <Navigate to={CHANGE_PASSWORD_PATH} replace />;
  }
  return <>{children}</>;
}

/** Oculta contenido según rol. La API vuelve a validar: esto es solo experiencia de usuario. */
export function RequireRoles({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { hasRole } = useAuth();
  if (hasRole(...roles)) return <>{children}</>;
  return (
    <Center mih="60vh">
      <Stack align="center" gap="xs">
        <ThemeIcon size={56} radius="xl" variant="light" color="gray">
          <IconLock size={30} />
        </ThemeIcon>
        <Title order={3}>Sin acceso</Title>
        <Text c="dimmed">Esta sección requiere el rol {roles.join(" o ")}.</Text>
        <Button component={Link} to="/" variant="light">
          Volver al inicio
        </Button>
      </Stack>
    </Center>
  );
}
