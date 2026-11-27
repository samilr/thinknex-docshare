import { ActionIcon, CopyButton, Group, TextInput, Tooltip } from "@mantine/core";
import { IconCheck, IconCopy, IconLink } from "@tabler/icons-react";

export function LinkReveal({ link }: { link: string }) {
  return (
    <Group gap={6} wrap="nowrap" w="100%">
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
  );
}
