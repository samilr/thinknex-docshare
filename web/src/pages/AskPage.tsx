import { Alert, Select, Stack } from "@mantine/core";
import { useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { AskPanel } from "../features/ai/AskPanel";
import { useAiStatus } from "../features/ai/api";
import { useLibraries } from "../features/library/api";

export function AskPage() {
  const status = useAiStatus();
  const libraries = useLibraries();
  const [libraryId, setLibraryId] = useState<string | null>(null);

  return (
    <Stack maw={880}>
      <PageHeader
        title="Preguntar"
        actions={
          <Select
            aria-label="Biblioteca"
            placeholder="Todas las bibliotecas"
            clearable
            data={(libraries.data ?? []).map((l) => ({ value: l.id, label: l.name }))}
            value={libraryId}
            onChange={setLibraryId}
            w={240}
          />
        }
      />
      {status.data && !status.data.llm ? (
        <Alert color="gray">La IA no está disponible en este entorno.</Alert>
      ) : (
        <AskPanel key={libraryId ?? "all"} libraryId={libraryId} />
      )}
    </Stack>
  );
}
