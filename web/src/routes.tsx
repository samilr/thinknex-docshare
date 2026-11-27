import { lazy } from "react";
import type { RouteObject } from "react-router";
import { RequireAuth, RequireRoles } from "./auth/guards";
import { AppLayout } from "./layout/AppLayout";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";

const AuditPage = lazy(() => import("./pages/AuditPage").then((m) => ({ default: m.AuditPage })));
const ChangePasswordPage = lazy(() =>
  import("./pages/ChangePasswordPage").then((m) => ({ default: m.ChangePasswordPage })),
);
const DashboardPage = lazy(() =>
  import("./pages/DashboardPage").then((m) => ({ default: m.DashboardPage })),
);
const DocumentsPage = lazy(() =>
  import("./pages/DocumentsPage").then((m) => ({ default: m.DocumentsPage })),
);
const InboxPage = lazy(() => import("./pages/InboxPage").then((m) => ({ default: m.InboxPage })));
const SharesPage = lazy(() =>
  import("./pages/SharesPage").then((m) => ({ default: m.SharesPage })),
);
const UsersPage = lazy(() => import("./pages/UsersPage").then((m) => ({ default: m.UsersPage })));

export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  {
    path: "/",
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <DashboardPage /> },
      {
        path: "documentos",
        element: (
          <RequireRoles roles={["SHARER"]}>
            <DocumentsPage />
          </RequireRoles>
        ),
      },
      { path: "envios", element: <SharesPage /> },
      {
        path: "auditoria",
        element: (
          <RequireRoles roles={["AUDITOR"]}>
            <AuditPage />
          </RequireRoles>
        ),
      },
      {
        path: "usuarios",
        element: (
          <RequireRoles roles={["ADMIN"]}>
            <UsersPage />
          </RequireRoles>
        ),
      },
      {
        path: "bandeja",
        element: (
          <RequireRoles roles={["ADMIN"]}>
            <InboxPage />
          </RequireRoles>
        ),
      },
      { path: "cuenta/clave", element: <ChangePasswordPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
