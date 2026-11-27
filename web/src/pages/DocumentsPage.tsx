import { Alert, Button, Card, Skeleton, Table, Text, TextInput } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { useQuery } from "@tanstack/react-query";
import { IconSearch, IconShare } from "@tabler/icons-react";
import { useState } from "react";
import { api, type Schemas, unwrap } from "../api/client";
import { ClassificationBadge } from "../components/badges";
import { PageHeader } from "../components/PageHeader";
import { ShareWizard } from "../features/share/ShareWizard";

export function DocumentsPage() {
  const [search, setSearch] = useState("");
  const [q] = useDebouncedValue(search, 300);
  const [selected, setSelected] = useState<Schemas["SourceDocument"] | null>(null);
  const docs = useQuery({
    queryKey: ["documents", q],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/documents", {
          params: { query: { q: q || undefined, limit: 100 } },
        }),
      ),
  });

  return (
    <>
      <PageHeader
        title="Documentos"
        description="Catálogo del sistema documental. Al compartir se toma una copia inmutable y se evalúa su sensibilidad."
      />
      <TextInput
        placeholder="Buscar por título…"
        leftSection={<IconSearch size={16} />}
        value={search}
        onChange={(e) => setSearch(e.currentTarget.value)}
        mb="md"
        maw={420}
      />
      {docs.isError && <Alert color="red">{docs.error.message}</Alert>}
      <Card withBorder radius="lg" p={0}>
        <Skeleton visible={docs.isPending}>
          <Table.ScrollContainer minWidth={640}>
            <Table highlightOnHover verticalSpacing="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>ID</Table.Th>
                  <Table.Th>Título</Table.Th>
                  <Table.Th>Clasificación</Table.Th>
                  <Table.Th>Versión</Table.Th>
                  <Table.Th>Responsable</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {docs.data?.items.map((doc) => (
                  <Table.Tr key={doc.id}>
                    <Table.Td ff="monospace" c="dimmed" style={{ whiteSpace: "nowrap" }}>
                      {doc.id}
                    </Table.Td>
                    <Table.Td fw={500}>{doc.title}</Table.Td>
                    <Table.Td>
                      <ClassificationBadge value={doc.classification} />
                    </Table.Td>
                    <Table.Td>v{doc.version}</Table.Td>
                    <Table.Td>
                      <Text size="sm" c="dimmed">
                        {doc.owner}
                      </Text>
                    </Table.Td>
                    <Table.Td ta="right">
                      <Button
                        size="xs"
                        leftSection={<IconShare size={14} />}
                        onClick={() => setSelected(doc)}
                      >
                        Compartir
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Skeleton>
      </Card>
      <ShareWizard
        document={selected}
        opened={selected !== null}
        onClose={() => setSelected(null)}
      />
    </>
  );
}
