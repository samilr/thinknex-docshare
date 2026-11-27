import { Alert, Button, Paper, PasswordInput, Stack, Text } from "@mantine/core";
import { hasLength, isNotEmpty, matchesField, useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { IconInfoCircle } from "@tabler/icons-react";
import { useState } from "react";
import { useNavigate } from "react-router";
import { api, problemMessage } from "../api/client";
import { useAuth } from "../auth/context";
import { PageHeader } from "../components/PageHeader";

export function ChangePasswordPage() {
  const { user, applySession } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const form = useForm({
    initialValues: { current: "", next: "", confirm: "" },
    validate: {
      current: isNotEmpty("Ingrese su contraseña actual"),
      next: hasLength({ min: 10 }, "Use al menos 10 caracteres"),
      confirm: matchesField("next", "Las contraseñas no coinciden"),
    },
  });

  const submit = form.onSubmit(async (values) => {
    setError(null);
    setSaving(true);
    const { data, error: apiError } = await api.POST("/api/v1/auth/change-password", {
      body: { current_password: values.current, new_password: values.next },
    });
    setSaving(false);
    if (!data) return setError(problemMessage(apiError));
    applySession(data);
    notifications.show({
      color: "green",
      message: "Contraseña actualizada. Se cerraron tus otras sesiones.",
    });
    navigate("/", { replace: true });
  });

  return (
    <>
      <PageHeader
        title="Cambiar contraseña"
        description="Las sesiones abiertas en otros dispositivos se cerrarán."
      />
      <Paper withBorder p="xl" radius="lg" maw={480}>
        <form onSubmit={submit} noValidate>
          <Stack>
            {user?.must_change_password && (
              <Alert color="yellow" icon={<IconInfoCircle size={18} />} title="Contraseña temporal">
                Debes definir una contraseña personal antes de continuar.
              </Alert>
            )}
            {error && <Alert color="red">{error}</Alert>}
            <PasswordInput
              label="Contraseña actual"
              autoComplete="current-password"
              {...form.getInputProps("current")}
            />
            <PasswordInput
              label="Nueva contraseña"
              autoComplete="new-password"
              {...form.getInputProps("next")}
            />
            <PasswordInput
              label="Repetir nueva contraseña"
              autoComplete="new-password"
              {...form.getInputProps("confirm")}
            />
            <Text size="xs" c="dimmed">
              Mínimo 10 caracteres, combinando letras con números o símbolos. No puede ser tu
              usuario.
            </Text>
            <Button type="submit" loading={saving}>
              Guardar
            </Button>
          </Stack>
        </form>
      </Paper>
    </>
  );
}
