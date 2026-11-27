import { Badge, Group, Text } from "@mantine/core";
import { IconBrandWhatsapp, IconMail, IconMessage } from "@tabler/icons-react";
import { CHANNEL, CLASSIFICATION, DECISION, labelOf, ROLE, SHARE_STATUS } from "../lib/labels";

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

const CHANNEL_ICON = { EMAIL: IconMail, WHATSAPP: IconBrandWhatsapp, SMS: IconMessage } as const;

export function ChannelLabel({ channel }: { channel: string }) {
  const Icon = CHANNEL_ICON[channel as keyof typeof CHANNEL_ICON] ?? IconMessage;
  return (
    <Group gap={6} wrap="nowrap">
      <Icon size={16} color={`var(--mantine-color-${labelOf(CHANNEL, channel).color}-6)`} />
      <Text size="sm">{labelOf(CHANNEL, channel).label}</Text>
    </Group>
  );
}
