import {
  ActionIcon,
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
import { useDisclosure } from "@mantine/hooks";
import {
  IconChartBar,
  IconFiles,
  IconInbox,
  IconKey,
  IconLogout,
  IconMoon,
  IconSend,
  IconShieldCheck,
  IconShieldLock,
  IconSun,
  IconScale,
  IconUsers,
} from "@tabler/icons-react";
import type { ComponentType } from "react";
import { Suspense } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router";
import { RoleBadge } from "../components/badges";
import { EnvironmentBadge } from "../components/EnvironmentBadge";
import { type Role, useAuth } from "../auth/context";

interface NavItem {
  to: string;
  label: string;
  icon: ComponentType<{ size?: number; stroke?: number }>;
  roles?: Role[];
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Resumen", icon: IconChartBar },
  { to: "/documentos", label: "Documentos", icon: IconFiles, roles: ["SHARER", "ADMIN"] },
  { to: "/envios", label: "Envíos", icon: IconSend },
  { to: "/auditoria", label: "Auditoría", icon: IconShieldCheck, roles: ["AUDITOR"] },
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
  const items = NAV_ITEMS.filter((item) => !item.roles || hasRole(...item.roles));

  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{ width: 250, breakpoint: "sm", collapsed: { mobile: !opened } }}
      padding="lg"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="sm">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" aria-label="Menú" />
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
                <Menu.Item leftSection={<IconKey size={16} />} component={Link} to="/cuenta/clave">
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
          {items.map((item) => (
            <NavLink
              key={item.to}
              component={Link}
              to={item.to}
              label={item.label}
              leftSection={<item.icon size={18} stroke={1.6} />}
              active={
                item.to === "/" ? location.pathname === "/" : location.pathname.startsWith(item.to)
              }
              onClick={close}
              style={{ borderRadius: 8 }}
            />
          ))}
        </AppShell.Section>
        <AppShell.Section>
          <Text size="xs" c="dimmed" px="sm">
            Toda acción queda registrada en una auditoría inmutable.
          </Text>
          <Text size="xs" c="dimmed" px="sm" mt={6}>
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
  );
}
