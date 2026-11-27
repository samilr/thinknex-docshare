import { createTheme } from "@mantine/core";
import { QueryClient } from "@tanstack/react-query";

export const theme = createTheme({
  primaryColor: "blue",
  cursorType: "pointer",
  defaultRadius: "md",
  fontFamily: "Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
  headings: { fontWeight: "700" },
});

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 10_000 },
      mutations: { retry: 0 },
    },
  });
}
