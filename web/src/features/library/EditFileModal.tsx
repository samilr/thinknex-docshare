import { Alert, Button, Group, Modal, Select, Stack, Text, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useAuth } from "../../auth/context";
import { CLASSIFICATION } from "../../lib/labels";
import { type Classification, type LibraryDocument, libraryKeys, updateDocument } from "./api";

const extensionOf = (filename: string) => {
  const dot = filename.lastIndexOf(".");
  return dot > 0 ? filename.slice(dot) : "";
};

const stemOf = (filename: string) => {
  const ext = extensionOf(filename);
  return ext ? filename.slice(0, -ext.length) : filename;
};

const CLASSIFICATION_OPTIONS = Object.entries(CLASSIFICATION).map(([value, { label }]) => ({
  value,
  label,
}));

/**
 * Edita un archivo: nombre (la extensión la define el tipo real del contenido) y, solo un ADMIN,
 * la clasificación. Cada cambio queda en la auditoría con el valor anterior y quién lo hizo.
 */
export function EditFileModal({
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
      title={<Text fw={700}>Editar archivo</Text>}
    >
      {document && <EditForm key={document.id} document={document} onClose={onClose} />}
    </Modal>
  );
}

function EditForm({ document, onClose }: { document: LibraryDocument; onClose: () => void }) {
  const { hasRole } = useAuth();
  const isAdmin = hasRole("ADMIN");
  const queryClient = useQueryClient();
  const extension = extensionOf(document.filename);
  const [name, setName] = useState(stemOf(document.filename) || document.title);
  const [classification, setClassification] = useState<Classification>(document.classification);
  const trimmed = name.trim();
  const nameChanged = `${trimmed}${extension}` !== document.filename;
  const classChanged = classification !== document.classification;
  const invalid = /[<>:"/\\|?*]/.test(trimmed);

  const save = useMutation({
    mutationFn: () =>
      updateDocument(document.id, {
        name: nameChanged ? trimmed : undefined,
        classification: classChanged ? classification : undefined,
      }),
    onSuccess: () => {
      notifications.show({
        color: "green",
        message: "Archivo actualizado. El cambio quedó registrado en la auditoría.",
      });
      void queryClient.invalidateQueries({ queryKey: libraryKeys.all });
      onClose();
    },
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if ((nameChanged || classChanged) && !invalid && trimmed) save.mutate();
      }}
    >
      <Stack>
        <TextInput
          label="Nombre"
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
        <Select
          label="Clasificación"
          description={
            isAdmin
              ? "Define qué reglas de la política aplican al compartir"
              : "Solo un administrador puede cambiarla"
          }
          data={CLASSIFICATION_OPTIONS}
          value={classification}
          onChange={(value) => value && setClassification(value as Classification)}
          allowDeselect={false}
          disabled={!isAdmin}
          comboboxProps={{ zIndex: 500 }}
        />
        <Text size="xs" c="dimmed">
          Nombre actual: {document.filename}. Editar no crea una versión ni cambia lo que ya se
          compartió: cada envío conserva el nombre y la clasificación con que se compartió.
        </Text>
        {save.error && <Alert color="red">{save.error.message}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            type="submit"
            loading={save.isPending}
            disabled={!trimmed || invalid || (!nameChanged && !classChanged)}
          >
            Guardar
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
