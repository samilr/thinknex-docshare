import { Badge, Group, Text } from "@mantine/core";
import {
  IconBrandWhatsapp,
  IconDownload,
  IconEye,
  IconLink,
  IconMail,
  IconMessage,
  IconPencil,
  IconWorld,
} from "@tabler/icons-react";
import {
  AUDIENCE,
  CHANNEL,
  CLASSIFICATION,
  DECISION,
  labelOf,
  PERMISSION,
  ROLE,
  SHARE_STATUS,
} from "../lib/labels";

export function StatusBadge({ status }: { status: string }) {
  const { label, color } = labelOf(SHARE_STATUS, status);
  return (
    <Badge
      color={color}
      variant="light"
      style={{ overflow: "visible", flexShrink: 0 }}
      miw="max-content"
    >
      {label}
    </Badge>
  );
}

export function ClassificationBadge({ value }: { value: string }) {
  const { label, color } = labelOf(CLASSIFICATION, value);
  return (
    <Badge color={color} variant="dot" miw="max-content">
      {label}
    </Badge>
  );
}

export function DecisionBadge({ value }: { value: string }) {
  const { label, color } = labelOf(DECISION, value);
  return (
    <Badge color={color} variant="filled">
      {label}
    </Badge>
  );
}

export function RoleBadge({ role }: { role: string }) {
  const { label, color } = labelOf(ROLE, role);
  return (
    <Badge color={color} variant="light" size="sm">
      {label}
    </Badge>
  );
}

const PERMISSION_ICON = { VIEW: IconEye, DOWNLOAD: IconDownload, EDIT: IconPencil } as const;

export function PermissionBadge({ value }: { value: string }) {
  const { label, color } = labelOf(PERMISSION, value);
  const Icon = PERMISSION_ICON[value as keyof typeof PERMISSION_ICON] ?? IconEye;
  return (
    <Badge color={color} variant="light" size="sm" leftSection={<Icon size={12} />}>
      {label}
    </Badge>
  );
}

export function AudienceBadge({ value }: { value: string }) {
  if (value !== "ANYONE") return null;
  const { label, color } = labelOf(AUDIENCE, value);
  return (
    <Badge color={color} variant="outline" size="sm" leftSection={<IconWorld size={12} />}>
      {label}
    </Badge>
  );
}

const CHANNEL_ICON = {
  LINK: IconLink,
  EMAIL: IconMail,
  WHATSAPP: IconBrandWhatsapp,
  SMS: IconMessage,
} as const;

export function ChannelLabel({ channel }: { channel: string }) {
  const Icon = CHANNEL_ICON[channel as keyof typeof CHANNEL_ICON] ?? IconMessage;
  return (
    <Group gap={6} wrap="nowrap">
      <Icon size={16} color={`var(--mantine-color-${labelOf(CHANNEL, channel).color}-6)`} />
      <Text size="sm">{labelOf(CHANNEL, channel).label}</Text>
    </Group>
  );
}
