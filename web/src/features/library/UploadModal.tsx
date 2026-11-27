import {
  Alert,
  Badge,
  Button,
  Group,
  Modal,
  Select,
  Stack,
  Text,
  Textarea,
  ThemeIcon,
} from "@mantine/core";
import { Dropzone } from "@mantine/dropzone";
import { useQueryClient } from "@tanstack/react-query";
import {
  IconAlertTriangle,
  IconCheck,
  IconFileUpload,
  IconUpload,
  IconX,
} from "@tabler/icons-react";
import { useState } from "react";
import { CLASSIFICATION, FINDING } from "../../lib/labels";
import {
  type Classification,
  libraryKeys,
  type UploadResult,
  uploadDocument,
  uploadVersion,
} from "./api";
import { ACCEPT, formatBytes, MAX_UPLOAD_BYTES } from "./files";
import { FileIcon } from "./icons";

type Row =
  | { file: File; state: "pending" }
  | { file: File; state: "uploading" }
  | { file: File; state: "done"; result: UploadResult }
  | { file: File; state: "conflict"; documentId: string }
  | { file: File; state: "error"; message: string };

function FindingsNote({ result }: { result: UploadResult }) {
  if (result.findings.length === 0) return null;
  return (
    <Text size="xs" c="orange.7">
      Contiene datos personales:{" "}
      {result.findings.map((f) => `${FINDING[f.type] ?? f.type} (${f.count})`).join(", ")}. Se
      pedirá confirmación al compartir externamente.
    </Text>
  );
}

export function UploadModal({
  opened,
  onClose,
  libraryId,
  folderId,
  locationLabel,
}: {
  opened: boolean;
  onClose: () => void;
  libraryId: string;
  folderId: string | null;
  locationLabel: string;
}) {
  const queryClient = useQueryClient();
  const [classification, setClassification] = useState<Classification>("INTERNAL");
  const [rows, setRows] = useState<Row[]>([]);
  const [rejected, setRejected] = useState<string | null>(null);
  const busy = rows.some((r) => r.state === "uploading");

  const update = (index: number, row: Row) =>
    setRows((current) => current.map((r, i) => (i === index ? row : r)));

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: libraryKeys.all });
    void queryClient.invalidateQueries({ queryKey: ["stats"] });
  };

  const uploadAll = async () => {
    for (const [index, row] of rows.entries()) {
      if (row.state !== "pending") continue;
      update(index, { file: row.file, state: "uploading" });
      try {
        const outcome = await uploadDocument({
          file: row.file,
          libraryId,
          folderId,
          classification,
        });
        update(
          index,
          outcome.kind === "ok"
            ? { file: row.file, state: "done", result: outcome.result }
            : { file: row.file, state: "conflict", documentId: outcome.documentId },
        );
      } catch (e) {
        update(index, { file: row.file, state: "error", message: (e as Error).message });
      }
    }
    refresh();
  };

  const asNewVersion = async (index: number, row: Extract<Row, { state: "conflict" }>) => {
    update(index, { file: row.file, state: "uploading" });
    try {
      const result = await uploadVersion(row.documentId, row.file, "Subida desde el explorador");
      update(index, { file: row.file, state: "done", result });
      refresh();
    } catch (e) {
      update(index, { file: row.file, state: "error", message: (e as Error).message });
    }
  };

  const close = () => {
    if (busy) return;
    if (rows.some((r) => r.state === "done")) refresh();
    setRows([]);
    setRejected(null);
    onClose();
  };

  return (
    <Modal opened={opened} onClose={close} size="lg" title={<Text fw={700}>Subir archivos</Text>}>
      <Stack>
        <Text size="sm" c="dimmed">
          Destino: <b>{locationLabel}</b>
        </Text>
        <Select
          label="Clasificación"
          data={Object.entries(CLASSIFICATION).map(([value, { label }]) => ({ value, label }))}
          value={classification}
          onChange={(v) => v && setClassification(v as Classification)}
          allowDeselect={false}
        />
        <Dropzone
          onDrop={(files) => {
            setRejected(null);
            setRows((current) => [
              ...current,
              ...files.map((file) => ({ file, state: "pending" as const })),
            ]);
          }}
          onReject={(files) =>
            setRejected(
              `${files.length} archivo(s) rechazado(s): solo PDF, imágenes, TXT, DOCX o XLSX de hasta 20 MB.`,
            )
          }
          maxSize={MAX_UPLOAD_BYTES}
          accept={ACCEPT}
          disabled={busy}
        >
          <Group justify="center" gap="md" mih={120} style={{ pointerEvents: "none" }}>
            <Dropzone.Accept>
              <IconUpload size={42} color="var(--mantine-color-blue-6)" />
            </Dropzone.Accept>
            <Dropzone.Reject>
              <IconX size={42} color="var(--mantine-color-red-6)" />
            </Dropzone.Reject>
            <Dropzone.Idle>
              <IconFileUpload size={42} color="var(--mantine-color-dimmed)" />
            </Dropzone.Idle>
            <div>
              <Text size="lg">Arrastra archivos aquí o haz clic para elegir</Text>
              <Text size="sm" c="dimmed">
                PDF, PNG, JPG, TXT, DOCX o XLSX · máximo 20 MB por archivo
              </Text>
            </div>
          </Group>
        </Dropzone>
        {rejected && <Alert color="red">{rejected}</Alert>}

        {rows.map((row, index) => (
          <Group
            key={`${row.file.name}-${index}`}
            justify="space-between"
            wrap="nowrap"
            align="flex-start"
          >
            <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
              <FileIcon mime={row.file.type} />
              <Stack gap={2} style={{ minWidth: 0 }}>
                <Text size="sm" fw={500} lineClamp={1}>
                  {row.file.name}
                </Text>
                <Text size="xs" c="dimmed">
                  {formatBytes(row.file.size)}
                </Text>
                {row.state === "done" && <FindingsNote result={row.result} />}
                {row.state === "error" && (
                  <Text size="xs" c="red">
                    {row.message}
                  </Text>
                )}
                {row.state === "conflict" && (
                  <Text size="xs" c="orange.7">
                    Ya existe un archivo con ese nombre en esta ubicación.
                  </Text>
                )}
              </Stack>
            </Group>
            {row.state === "pending" && <Badge variant="light">Listo para subir</Badge>}
            {row.state === "uploading" && <Badge variant="light">Subiendo…</Badge>}
            {row.state === "done" && (
              <ThemeIcon color="green" variant="light" radius="xl">
                <IconCheck size={16} />
              </ThemeIcon>
            )}
            {row.state === "error" && (
              <ThemeIcon color="red" variant="light" radius="xl">
                <IconAlertTriangle size={16} />
              </ThemeIcon>
            )}
            {row.state === "conflict" && (
              <Button size="xs" variant="light" onClick={() => void asNewVersion(index, row)}>
                Subir como nueva versión
              </Button>
            )}
          </Group>
        ))}

        <Group justify="flex-end">
          <Button variant="default" onClick={close} disabled={busy}>
            Cerrar
          </Button>
          <Button
            onClick={() => void uploadAll()}
            loading={busy}
            disabled={!rows.some((r) => r.state === "pending")}
            leftSection={<IconUpload size={16} />}
          >
            Subir
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

export function NewVersionModal({
  documentId,
  onClose,
}: {
  documentId: string | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);

  const close = () => {
    if (result) void queryClient.invalidateQueries({ queryKey: libraryKeys.all });
    setFile(null);
    setComment("");
    setError(null);
    setResult(null);
    onClose();
  };

  const submit = async () => {
    if (!file || !documentId) return;
    setSaving(true);
    setError(null);
    try {
      setResult(await uploadVersion(documentId, file, comment));
      void queryClient.invalidateQueries({ queryKey: libraryKeys.all });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      opened={!!documentId}
      onClose={close}
      zIndex={400}
      title={<Text fw={700}>Nueva versión</Text>}
    >
      <Stack>
        {result ? (
          <>
            <Alert color="green" title={`Versión ${result.document.version} publicada`} />
            <FindingsNote result={result} />
            <Button onClick={close}>Listo</Button>
          </>
        ) : (
          <>
            <Dropzone
              onDrop={(files) => setFile(files[0] ?? null)}
              onReject={() => setError("Archivo no permitido o mayor a 20 MB")}
              maxFiles={1}
              maxSize={MAX_UPLOAD_BYTES}
              accept={ACCEPT}
            >
              <Group justify="center" mih={80} style={{ pointerEvents: "none" }}>
                <IconFileUpload size={32} color="var(--mantine-color-dimmed)" />
                <Text>{file ? file.name : "Arrastra el archivo o haz clic para elegir"}</Text>
              </Group>
            </Dropzone>
            <Textarea
              label="Comentario"
              placeholder="¿Qué cambió en esta versión?"
              value={comment}
              onChange={(e) => setComment(e.currentTarget.value)}
              maxLength={500}
            />
            {error && <Alert color="red">{error}</Alert>}
            <Group justify="flex-end">
              <Button variant="default" onClick={close}>
                Cancelar
              </Button>
              <Button disabled={!file} loading={saving} onClick={() => void submit()}>
                Publicar versión
              </Button>
            </Group>
          </>
        )}
      </Stack>
    </Modal>
  );
}
