import { Badge, Tooltip } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";

const ENVIRONMENTS: Record<string, { label: string; color: string; hint: string }> = {
  local: {
    label: "Local",
    color: "gray",
    hint: "Todo corre en Docker en este equipo, con datos locales.",
  },
  hybrid: {
    label: "Híbrido",
    color: "orange",
    hint: "Contenedores en este equipo conectados a la infraestructura de GCP: los datos son los de la nube.",
  },
  gcp: { label: "GCP", color: "blue", hint: "Desplegado en Google Cloud (Cloud Run)." },
};

/** Muestra contra qué entorno se está trabajando (APP_ENV de share-api). */
export function EnvironmentBadge() {
  const meta = useQuery({
    queryKey: ["meta"],
    staleTime: Infinity,
    queryFn: async () => unwrap(await api.GET("/api/v1/meta")),
  });
  const env = meta.data ? ENVIRONMENTS[meta.data.app_env] : undefined;
  if (!env) return null;
  return (
    <Tooltip label={env.hint} multiline w={260}>
      <Badge color={env.color} variant="light" size="sm">
        {env.label}
      </Badge>
    </Tooltip>
  );
}
