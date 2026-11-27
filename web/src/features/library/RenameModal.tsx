import { Alert, Button, Group, Modal, Stack, Text, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { type LibraryDocument, libraryKeys, renameDocument } from "./api";

const extensionOf = (filename: string) => {
  const dot = filename.lastIndexOf(".");
  return dot > 0 ? filename.slice(dot) : "";
};

const stemOf = (filename: string) => {
  const ext = extensionOf(filename);
  return ext ? filename.slice(0, -ext.length) : filename;
};

/**
 * Renombra un archivo. La extensión no se edita (la define el tipo real del contenido). El cambio
 * queda en la auditoría con el nombre anterior, el nuevo y quién lo hizo.
 */
export function RenameModal({
  document,
  onClose,
}: {
  document: LibraryDocument | null;
  onClose: () => void;
}) {
  return (
    <Modal
      zIndex={400} // por encima del panel lateral del explorador
      opened={document !== null}
      onClose={onClose}
      title={<Text fw={700}>Renombrar archivo</Text>}
    >
      {document && <RenameForm key={document.id} document={document} onClose={onClose} />}
    </Modal>
  );
}

function RenameForm({ document, onClose }: { document: LibraryDocument; onClose: () => void }) {
  const queryClient = useQueryClient();
  const extension = extensionOf(document.filename);
  const [name, setName] = useState(stemOf(document.filename) || document.title);
  const trimmed = name.trim();
  const unchanged = `${trimmed}${extension}` === document.filename;
  const invalid = /[<>:"/\\|?*]/.test(trimmed);

  const rename = useMutation({
    mutationFn: () => renameDocument(document.id, trimmed),
    onSuccess: (renamed) => {
      notifications.show({
        color: "green",
        message: `Archivo renombrado a «${renamed.filename}». El cambio quedó en la auditoría.`,
      });
      void queryClient.invalidateQueries({ queryKey: libraryKeys.all });
      onClose();
    },
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!unchanged && !invalid && trimmed) rename.mutate();
      }}
    >
      <Stack>
        <TextInput
          label="Nuevo nombre"
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
          maxLength={150}
          data-autofocus
          rightSection={
            extension ? (
              <Text size="sm" c="dimmed">
                {extension}
              </Text>
            ) : undefined
          }
          rightSectionWidth={extension ? 56 : undefined}
          error={invalid ? 'No se permiten los caracteres < > : " / \\ | ? *' : undefined}
        />
        <Text size="xs" c="dimmed">
          Nombre actual: {document.filename}. Renombrar no crea una versión ni cambia lo que ya se
          compartió: cada envío conserva el nombre con que se compartió.
        </Text>
        {rename.error && <Alert color="red">{rename.error.message}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            type="submit"
            loading={rename.isPending}
            disabled={!trimmed || unchanged || invalid}
          >
            Renombrar
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
