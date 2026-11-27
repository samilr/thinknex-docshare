import {
  Alert,
  Button,
  Group,
  Modal,
  NumberInput,
  SegmentedControl,
  Select,
  Stack,
  Switch,
  Text,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Schemas, unwrap } from "../../api/client";
import { formatDateTime } from "../../lib/format";
import { PERMISSION } from "../../lib/labels";

type Share = Schemas["ShareOut"];
type Permission = Share["permission"];

const EXPIRY_OPTIONS = [
  { value: "", label: "Sin cambios" },
  { value: "24", label: "24 horas desde ahora" },
  { value: "72", label: "3 días desde ahora" },
  { value: "168", label: "7 días desde ahora" },
];

export function EditShareModal({ share, onClose }: { share: Share | null; onClose: () => void }) {
  return (
    <Modal
      zIndex={400}
      opened={share !== null}
      onClose={onClose}
      title={<Text fw={700}>Editar acceso</Text>}
    >
      {share && <EditShareForm key={share.id} share={share} onClose={onClose} />}
    </Modal>
  );
}

function EditShareForm({ share, onClose }: { share: Share; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [permission, setPermission] = useState<Permission>(share.permission);
  const [watermark, setWatermark] = useState(share.watermark ?? true);
  const [expires, setExpires] = useState("");
  const [maxAccesses, setMaxAccesses] = useState<number>(share.max_accesses);
  const anyone = share.audience === "ANYONE";

  const changes: Schemas["ShareUpdate"] = {
    ...(permission !== share.permission ? { permission } : {}),
    ...(watermark !== (share.watermark ?? true) ? { watermark } : {}),
    ...(expires ? { expires_in_hours: Number(expires) } : {}),
    ...(maxAccesses !== share.max_accesses ? { max_accesses: maxAccesses } : {}),
  };
  const dirty = Object.keys(changes).length > 0;

  const save = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.PATCH("/api/v1/shares/{share_id}", {
          params: { path: { share_id: share.id } },
          body: changes,
        }),
      ),
    onSuccess: () => {
      notifications.show({ color: "green", message: "Acceso actualizado." });
      void queryClient.invalidateQueries({ queryKey: ["shares"] });
      void queryClient.invalidateQueries({ queryKey: ["library"] });
      onClose();
    },
  });

  return (
    <Stack>
      <Text size="sm" c="dimmed">
        {share.recipient
          ? `${share.recipient.name} · ${share.recipient.contact}`
          : "Cualquier persona con el enlace"}
      </Text>
      <div>
        <Text size="sm" fw={500} mb={4}>
          Permiso
        </Text>
        <SegmentedControl
          fullWidth
          value={permission}
          onChange={(v) => setPermission(v as Permission)}
          data={(["VIEW", "DOWNLOAD", "EDIT"] as const).map((value) => ({
            value,
            label: PERMISSION[value]!.label,
            disabled: value === "EDIT" && anyone,
          }))}
        />
      </div>
      <Switch
        label="Marca de agua"
        checked={watermark}
        onChange={(e) => setWatermark(e.currentTarget.checked)}
      />
      <Select
        label="Vencimiento"
        description={`Actual: ${formatDateTime(share.expires_at)}`}
        data={EXPIRY_OPTIONS}
        value={expires}
        onChange={(v) => setExpires(v ?? "")}
        allowDeselect={false}
        comboboxProps={{ zIndex: 500 }}
      />
      <NumberInput
        label="Accesos permitidos"
        description={`Usados: ${share.access_count}`}
        min={Math.max(1, share.access_count)}
        max={100}
        value={maxAccesses}
        onChange={(v) => setMaxAccesses(Number(v) || share.max_accesses)}
      />
      {save.error && <Alert color="red">{save.error.message}</Alert>}
      <Group justify="flex-end">
        <Button variant="default" onClick={onClose}>
          Cancelar
        </Button>
        <Button disabled={!dirty} loading={save.isPending} onClick={() => save.mutate()}>
          Guardar
        </Button>
      </Group>
    </Stack>
  );
}
