import { lazy, Suspense } from "react";
import type { RouteObject } from "react-router";
import { RequireAuth, RequireRoles } from "./auth/guards";
import { AppLayout } from "./layout/AppLayout";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { RouteErrorPage } from "./pages/RouteErrorPage";

const AuditPage = lazy(() => import("./pages/AuditPage").then((m) => ({ default: m.AuditPage })));
const ChangePasswordPage = lazy(() =>
  import("./pages/ChangePasswordPage").then((m) => ({ default: m.ChangePasswordPage })),
);
const DashboardPage = lazy(() =>
  import("./pages/DashboardPage").then((m) => ({ default: m.DashboardPage })),
);
const ExplorerPage = lazy(() =>
  import("./features/library/ExplorerPage").then((m) => ({ default: m.ExplorerPage })),
);
const RecipientPage = lazy(() =>
  import("./features/recipient/RecipientPage").then((m) => ({ default: m.RecipientPage })),
);
const InboxPage = lazy(() => import("./pages/InboxPage").then((m) => ({ default: m.InboxPage })));
const SharesPage = lazy(() =>
  import("./pages/SharesPage").then((m) => ({ default: m.SharesPage })),
);
const UsersPage = lazy(() => import("./pages/UsersPage").then((m) => ({ default: m.UsersPage })));

export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage />, errorElement: <RouteErrorPage /> },
  // Público: el destinatario abre el enlace sin cuenta de la organización.
  {
    path: "/s/:token",
    errorElement: <RouteErrorPage />,
    element: (
      <Suspense fallback={null}>
        <RecipientPage />
      </Suspense>
    ),
  },
  {
    path: "/",
    errorElement: <RouteErrorPage />,
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <DashboardPage /> },
      {
        path: "documentos/:libraryId?/:folderId?",
        element: (
          <RequireRoles roles={["SHARER"]}>
            <ExplorerPage />
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
