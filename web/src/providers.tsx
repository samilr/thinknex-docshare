import { MantineProvider } from "@mantine/core";
import { ModalsProvider } from "@mantine/modals";
import { Notifications } from "@mantine/notifications";
import { type QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { AuthProvider } from "./auth/AuthProvider";
import { makeQueryClient, theme } from "./theme";

export function Providers({
  children,
  queryClient,
}: {
  children: ReactNode;
  queryClient?: QueryClient;
}) {
  const [client] = useState(() => queryClient ?? makeQueryClient());
  return (
    <MantineProvider theme={theme} defaultColorScheme="auto">
      <Notifications position="top-right" />
      <QueryClientProvider client={client}>
        <ModalsProvider>
          <AuthProvider>{children}</AuthProvider>
        </ModalsProvider>
      </QueryClientProvider>
    </MantineProvider>
  );
}
