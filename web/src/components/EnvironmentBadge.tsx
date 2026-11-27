import { Badge } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";

const ENVIRONMENTS: Record<string, { label: string; color: string }> = {
  local: { label: "Local", color: "gray" },
  hybrid: { label: "Híbrido", color: "orange" },
  gcp: { label: "GCP", color: "blue" },
};

export function EnvironmentBadge() {
  const meta = useQuery({
    queryKey: ["meta"],
    staleTime: Infinity,
    queryFn: async () => unwrap(await api.GET("/api/v1/meta")),
  });
  const env = meta.data ? ENVIRONMENTS[meta.data.app_env] : undefined;
  if (!env) return null;
  return (
    <Badge color={env.color} variant="light" size="sm">
      {env.label}
    </Badge>
  );
}
