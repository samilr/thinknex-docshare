import {
  ActionIcon,
  Anchor,
  AppShell,
  Avatar,
  Burger,
  Group,
  Menu,
  NavLink,
  ScrollArea,
  Text,
  Tooltip,
  UnstyledButton,
  useComputedColorScheme,
  useMantineColorScheme,
} from "@mantine/core";
import { useDisclosure, useLocalStorage } from "@mantine/hooks";
import {
  IconChartBar,
  IconFiles,
  IconInbox,
  IconKey,
  IconLayoutSidebarLeftCollapse,
  IconLayoutSidebarLeftExpand,
  IconLogout,
  IconMoon,
  IconSend,
  IconShieldCheck,
  IconSparkles,
  IconShieldLock,
  IconSun,
  IconScale,
  IconUserShare,
  IconUsers,
} from "@tabler/icons-react";
import type { ComponentType } from "react";
import { Suspense, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router";
import { RoleBadge } from "../components/badges";
import { EnvironmentBadge } from "../components/EnvironmentBadge";
import { type Role, useAuth } from "../auth/context";
import { useAiStatus } from "../features/ai/api";
import { AssistantProvider } from "../features/assistant/AssistantProvider";
import { labelOf, ROLE } from "../lib/labels";

interface NavItem {
  to: string;
  label: string;
  icon: ComponentType<{ size?: number; stroke?: number }>;
  roles?: Role[];
  requiresAi?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Resumen", icon: IconChartBar },
  { to: "/documentos", label: "Documentos", icon: IconFiles, roles: ["SHARER", "ADMIN"] },
  { to: "/asistente", label: "Asistente", icon: IconSparkles, requiresAi: true },
  { to: "/envios", label: "Envíos", icon: IconSend },
  { to: "/auditoria", label: "Auditoría", icon: IconShieldCheck, roles: ["AUDITOR", "ADMIN"] },
  { to: "/politicas", label: "Políticas", icon: IconScale, roles: ["ADMIN", "AUDITOR"] },
  { to: "/usuarios", label: "Usuarios", icon: IconUsers, roles: ["ADMIN"] },
  { to: "/bandeja", label: "Bandeja simulada", icon: IconInbox, roles: ["ADMIN"] },
];

function ColorSchemeToggle() {
  const { setColorScheme } = useMantineColorScheme();
  const scheme = useComputedColorScheme("light");
  const next = scheme === "dark" ? "light" : "dark";
  return (
    <Tooltip label={next === "dark" ? "Modo oscuro" : "Modo claro"}>
      <ActionIcon
        variant="default"
        size="lg"
        onClick={() => setColorScheme(next)}
        aria-label="Cambiar tema"
      >
        {scheme === "dark" ? <IconSun size={18} /> : <IconMoon size={18} />}
      </ActionIcon>
    </Tooltip>
  );
}

export function AppLayout() {
  const [opened, { toggle, close }] = useDisclosure();
  const { user, hasRole, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const aiStatus = useAiStatus();
  const items = NAV_ITEMS.filter(
    (item) =>
      (!item.roles || hasRole(...item.roles)) && (!item.requiresAi || aiStatus.data?.llm === true),
  );
  const impersonating = !!user?.impersonator;
  const [compact, setCompact] = useLocalStorage({
    key: "thinknex-sidebar-compact",
    defaultValue: false,
  });

  return (
    <AssistantProvider>
      <AppShell
        header={{ height: 60 + (impersonating ? IMPERSONATION_BAR : 0) }}
        navbar={{
          width: { base: 250, sm: compact ? 68 : 250 },
          breakpoint: "sm",
          collapsed: { mobile: !opened },
        }}
        padding="lg"
      >
        <AppShell.Header>
          {impersonating && <ImpersonationBar />}
          <Group h={60} px="md" justify="space-between">
            <Group gap="sm">
              <Burger
                opened={opened}
                onClick={toggle}
                hiddenFrom="sm"
                size="sm"
                aria-label="Menú"
              />
              <Tooltip label={compact ? "Expandir menú" : "Contraer menú"}>
                <ActionIcon
                  variant="subtle"
                  color="gray"
                  size="lg"
                  visibleFrom="sm"
                  aria-label={compact ? "Expandir menú" : "Contraer menú"}
                  aria-expanded={!compact}
                  onClick={() => setCompact((c) => !c)}
                >
                  {compact ? (
                    <IconLayoutSidebarLeftExpand size={20} stroke={1.6} />
                  ) : (
                    <IconLayoutSidebarLeftCollapse size={20} stroke={1.6} />
                  )}
                </ActionIcon>
              </Tooltip>
              <IconShieldLock size={26} color="var(--mantine-primary-color-filled)" />
              <Text fw={700} size="lg">
                ThinkNex Docs
              </Text>
              <EnvironmentBadge />
            </Group>
            <Group gap="sm">
              <ColorSchemeToggle />
              <Menu position="bottom-end" width={240} withinPortal>
                <Menu.Target>
                  <UnstyledButton aria-label="Menú de usuario">
                    <Group gap="xs">
                      <Avatar radius="xl" color="blue" name={user?.name} />
                      <div style={{ lineHeight: 1.1 }}>
                        <Text size="sm" fw={600} visibleFrom="xs">
                          {user?.name}
                        </Text>
                        <Text size="xs" c="dimmed" visibleFrom="xs">
                          {user?.email}
                        </Text>
                      </div>
                    </Group>
                  </UnstyledButton>
                </Menu.Target>
                <Menu.Dropdown>
                  <Menu.Label>Roles</Menu.Label>
                  <Group gap={4} px="sm" pb="xs">
                    {user?.roles.map((r) => (
                      <RoleBadge key={r} role={r} />
                    ))}
                  </Group>
                  <Menu.Divider />
                  <Menu.Item
                    leftSection={<IconKey size={16} />}
                    component={Link}
                    to="/cuenta/clave"
                  >
                    Cambiar contraseña
                  </Menu.Item>
                  <Menu.Item
                    color="red"
                    leftSection={<IconLogout size={16} />}
                    onClick={async () => {
                      await logout();
                      navigate("/login", { replace: true });
                    }}
                  >
                    Cerrar sesión
                  </Menu.Item>
                </Menu.Dropdown>
              </Menu>
            </Group>
          </Group>
        </AppShell.Header>

        <AppShell.Navbar p="sm">
          <AppShell.Section grow component={ScrollArea}>
            {items.map((item) => {
              const active =
                item.to === "/" ? location.pathname === "/" : location.pathname.startsWith(item.to);
              return (
                <Tooltip
                  key={item.to}
                  label={item.label}
                  position="right"
                  disabled={!compact}
                  withArrow
                >
                  <NavLink
                    component={Link}
                    to={item.to}
                    label={item.label}
                    aria-label={item.label}
                    leftSection={<item.icon size={18} stroke={1.6} />}
                    active={active}
                    onClick={close}
                    className={compact ? "nav-compact" : undefined}
                    style={{ borderRadius: 8 }}
                  />
                </Tooltip>
              );
            })}
          </AppShell.Section>
          <AppShell.Section className={compact ? "nav-compact-hide" : undefined}>
            <Text size="xs" c="dimmed" px="sm">
              ThinkNex Docs · prototipo de prueba técnica con datos ficticios.
            </Text>
          </AppShell.Section>
        </AppShell.Navbar>

        <AppShell.Main>
          <Suspense fallback={null}>
            <Outlet />
          </Suspense>
        </AppShell.Main>
      </AppShell>
    </AssistantProvider>
  );
}

const IMPERSONATION_BAR = 34;

function ImpersonationBar() {
  const { user, stopImpersonation } = useAuth();
  const navigate = useNavigate();
  const [leaving, setLeaving] = useState(false);
  if (!user?.impersonator) return null;
  const roles = user.roles.map((r) => labelOf(ROLE, r).label).join(", ");
  return (
    <Group
      h={IMPERSONATION_BAR}
      px="md"
      gap="xs"
      justify="center"
      wrap="nowrap"
      bg="var(--mantine-color-yellow-6)"
      c="dark.9"
      role="status"
      style={{ whiteSpace: "nowrap", overflow: "hidden" }}
    >
      <IconUserShare size={16} style={{ flexShrink: 0 }} />
      <Text size="sm" fw={600} truncate="end">
        Estás actuando como {user.name} ({roles})
      </Text>
      <Text size="sm" fw={600} visibleFrom="xs">
        —
      </Text>
      <Anchor
        component="button"
        size="sm"
        fw={700}
        c="dark.9"
        underline="always"
        disabled={leaving}
        style={{ flexShrink: 0 }}
        onClick={() => {
          setLeaving(true);
          void stopImpersonation()
            .then(() => navigate("/usuarios"))
            .finally(() => setLeaving(false));
        }}
      >
        Volver a mi cuenta
      </Anchor>
    </Group>
  );
}
