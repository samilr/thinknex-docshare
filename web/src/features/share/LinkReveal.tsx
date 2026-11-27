import { ActionIcon, Alert, CopyButton, Group, Stack, TextInput, Tooltip } from "@mantine/core";
import { IconCheck, IconCopy, IconLink } from "@tabler/icons-react";

/** Muestra un enlace de ThinkNex Docs recién creado, con botón Copiar. Solo se ve una vez. */
export function LinkReveal({ link }: { link: string }) {
  return (
    <Stack gap="xs" w="100%">
      <Group gap={6} wrap="nowrap">
        <TextInput
          readOnly
          value={link}
          aria-label="Enlace para compartir"
          leftSection={<IconLink size={16} />}
          style={{ flex: 1 }}
          onFocus={(e) => e.currentTarget.select()}
        />
        <CopyButton value={link}>
          {({ copied, copy }) => (
            <Tooltip label={copied ? "Copiado" : "Copiar"} withArrow zIndex={500}>
              <ActionIcon
                size="lg"
                variant={copied ? "filled" : "light"}
                color={copied ? "teal" : "blue"}
                onClick={copy}
                aria-label="Copiar enlace"
              >
                {copied ? <IconCheck size={18} /> : <IconCopy size={18} />}
              </ActionIcon>
            </Tooltip>
          )}
        </CopyButton>
      </Group>
      <Alert variant="light" color="yellow" ta="left">
        Copia el enlace ahora: por seguridad solo se guarda su huella y no se puede volver a
        mostrar. Si lo pierdes, genera uno nuevo desde el envío (el anterior dejará de funcionar).
      </Alert>
    </Stack>
  );
}
