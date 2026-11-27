import {
  Alert,
  Button,
  Center,
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
          <Title order={2}>ThinkNex Docs</Title>
          <Text c="dimmed" size="sm" ta="center">
            Compartición segura de documentos
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
                placeholder="usuario@thinknex.example"
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
        <Text size="xs" c="dimmed" ta="center">
          Prototipo Técnico - Samir Gonzalez
        </Text>
      </Stack>
    </Center>
  );
}
