import {
  Alert,
  Anchor,
  Button,
  Center,
  Code,
  Paper,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { isEmail, isNotEmpty, useForm } from "@mantine/form";
import { IconAlertCircle, IconShieldLock } from "@tabler/icons-react";
import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { useAuth } from "../auth/context";

const DEMO_ACCOUNTS = [
  ["admin@demo-corp.example", "Administrador"],
  ["ana@demo-corp.example", "Emisora"],
  ["carla@demo-corp.example", "Auditora"],
] as const;

export function LoginPage() {
  const { login, status } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const from = (location.state as { from?: string } | null)?.from ?? "/";
  const form = useForm({
    initialValues: { email: "", password: "" },
    validate: {
      email: isEmail("Ingrese un email válido"),
      password: isNotEmpty("Ingrese su contraseña"),
    },
  });

  if (status === "authenticated") return <Navigate to={from} replace />;

  const submit = form.onSubmit(async ({ email, password }) => {
    setError(null);
    setSubmitting(true);
    try {
      const user = await login(email, password);
      navigate(user.must_change_password ? "/cuenta/clave" : from, { replace: true });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  });

  return (
    <Center mih="100vh" p="md" bg="var(--mantine-color-gray-light)">
      <Stack w="100%" maw={420} gap="lg">
        <Stack align="center" gap={6}>
          <ThemeIcon size={56} radius="xl" variant="light">
            <IconShieldLock size={32} />
          </ThemeIcon>
          <Title order={2}>Documentos Seguros</Title>
          <Text c="dimmed" size="sm" ta="center">
            Comparte documentos con trazabilidad completa: quién, cuándo y por qué medio.
          </Text>
        </Stack>
        <Paper withBorder shadow="sm" p="xl" radius="lg">
          <form onSubmit={submit} noValidate>
            <Stack>
              {error && (
                <Alert
                  color="red"
                  icon={<IconAlertCircle size={18} />}
                  title="No pudimos iniciar sesión"
                >
                  {error}
                </Alert>
              )}
              <TextInput
                label="Email"
                placeholder="usuario@empresa.cl"
                autoComplete="username"
                autoFocus
                {...form.getInputProps("email")}
              />
              <PasswordInput
                label="Contraseña"
                autoComplete="current-password"
                {...form.getInputProps("password")}
              />
              <Button type="submit" loading={submitting} fullWidth>
                Ingresar
              </Button>
            </Stack>
          </form>
        </Paper>
        {import.meta.env.VITE_SHOW_DEMO_ACCOUNTS === "true" && (
          <Paper withBorder p="md" radius="lg">
            <Text size="sm" fw={600} mb={6}>
              Cuentas de demostración (datos ficticios)
            </Text>
            <Stack gap={4}>
              {DEMO_ACCOUNTS.map(([email, role]) => (
                <Text size="sm" key={email}>
                  <Anchor
                    component="button"
                    type="button"
                    onClick={() => form.setFieldValue("email", email)}
                  >
                    {email}
                  </Anchor>{" "}
                  <Text span c="dimmed" size="xs">
                    · {role}
                  </Text>
                </Text>
              ))}
            </Stack>
            <Text size="xs" c="dimmed" mt={6}>
              Las contraseñas están en la documentación de la entrega (<Code>README</Code>).
            </Text>
          </Paper>
        )}
      </Stack>
    </Center>
  );
}
