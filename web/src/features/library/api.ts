import { useQuery } from "@tanstack/react-query";
import { api, type Problem, problemMessage, type Schemas, unwrap } from "../../api/client";

export type Library = Schemas["SourceLibrary"];
export type Folder = Schemas["SourceFolder"];
export type LibraryDocument = Schemas["LibraryDocument"];
export type LibraryItems = Schemas["LibraryItems"];
export type DocumentDetail = Schemas["DocumentDetail"];
export type UploadResult = Schemas["UploadResult"];
export type Classification = Schemas["SourceDocument"]["classification"];

export const libraryKeys = {
  all: ["library"] as const,
  libraries: ["library", "libraries"] as const,
  items: (libraryId: string, folderId: string | null, q: string) =>
    ["library", "items", libraryId, folderId, q] as const,
  document: (id: string) => ["library", "document", id] as const,
  access: (id: string) => ["library", "document", id, "access"] as const,
  activity: (id: string) => ["library", "document", id, "activity"] as const,
};

export function useLibraries() {
  return useQuery({
    queryKey: libraryKeys.libraries,
    queryFn: async () => unwrap(await api.GET("/api/v1/library/libraries")),
  });
}

export function useItems(libraryId: string | undefined, folderId: string | null, q: string) {
  return useQuery({
    queryKey: libraryKeys.items(libraryId ?? "", folderId, q),
    enabled: !!libraryId,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/library/items", {
          params: {
            query: { library_id: libraryId!, folder_id: folderId ?? undefined, q: q || undefined },
          },
        }),
      ),
  });
}

export function useDocumentDetail(id: string | null) {
  return useQuery({
    queryKey: libraryKeys.document(id ?? ""),
    enabled: !!id,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/library/documents/{doc_id}", {
          params: { path: { doc_id: id! } },
        }),
      ),
  });
}

export function useAccess(id: string | null) {
  return useQuery({
    queryKey: libraryKeys.access(id ?? ""),
    enabled: !!id,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/library/documents/{doc_id}/access", {
          params: { path: { doc_id: id! } },
        }),
      ),
  });
}

export function useActivity(id: string | null) {
  return useQuery({
    queryKey: libraryKeys.activity(id ?? ""),
    enabled: !!id,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/library/documents/{doc_id}/activity", {
          params: { path: { doc_id: id! } },
        }),
      ),
  });
}

export async function fetchContent(
  id: string,
  { version, disposition = "inline" }: { version?: number; disposition?: "inline" | "attachment" },
): Promise<Blob> {
  const { data, error } = await api.GET("/api/v1/library/documents/{doc_id}/content", {
    params: { path: { doc_id: id }, query: { version, disposition } },
    parseAs: "blob",
  });
  if (!data) throw new Error(problemMessage(error, "No fue posible abrir el archivo"));
  return data as Blob;
}

export async function downloadDocument(id: string, filename: string, version?: number) {
  const blob = await fetchContent(id, { version, disposition: "attachment" });
  const url = URL.createObjectURL(blob);
  const anchor = Object.assign(document.createElement("a"), { href: url, download: filename });
  anchor.click();
  URL.revokeObjectURL(url);
}

type UploadOutcome =
  { kind: "ok"; result: UploadResult } | { kind: "conflict"; documentId: string; message: string };

function formBody(fields: Record<string, string | Blob | null | undefined>): FormData {
  const form = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    if (value !== null && value !== undefined && value !== "") form.append(key, value);
  }
  return form;
}

export async function uploadDocument(input: {
  file: File;
  libraryId: string;
  folderId: string | null;
  classification: Classification;
}): Promise<UploadOutcome> {
  const form = formBody({
    file: input.file,
    library_id: input.libraryId,
    folder_id: input.folderId,
    classification: input.classification,
  });
  const { data, error, response } = await api.POST("/api/v1/library/documents", {
    body: form as never,
    bodySerializer: () => form,
  });
  if (data) return { kind: "ok", result: data };
  const problem = error as Problem & { code?: string; document_id?: string };
  if (response.status === 409 && problem?.code === "name_conflict" && problem.document_id) {
    return { kind: "conflict", documentId: problem.document_id, message: problemMessage(error) };
  }
  throw new Error(problemMessage(error, "No fue posible subir el archivo"));
}

export async function uploadVersion(
  id: string,
  file: File,
  comment: string,
): Promise<UploadResult> {
  const form = formBody({ file, comment });
  const { data, error } = await api.POST("/api/v1/library/documents/{doc_id}/versions", {
    params: { path: { doc_id: id } },
    body: form as never,
    bodySerializer: () => form,
  });
  if (!data) throw new Error(problemMessage(error, "No fue posible subir la nueva versión"));
  return data;
}

export async function updateDocument(
  id: string,
  changes: { name?: string; classification?: Classification },
): Promise<LibraryDocument> {
  const { data, error } = await api.PATCH("/api/v1/library/documents/{doc_id}", {
    params: { path: { doc_id: id } },
    body: changes,
  });
  if (!data) throw new Error(problemMessage(error, "No fue posible actualizar el archivo"));
  return data;
}

export async function deleteDocument(id: string): Promise<number> {
  const { data, error } = await api.DELETE("/api/v1/library/documents/{doc_id}", {
    params: { path: { doc_id: id } },
  });
  if (!data) throw new Error(problemMessage(error, "No fue posible eliminar el archivo"));
  return data.revoked_shares;
}

export async function createFolder(libraryId: string, parentId: string | null, name: string) {
  const { data, error } = await api.POST("/api/v1/library/folders", {
    body: { library_id: libraryId, parent_id: parentId, name },
  });
  if (!data) throw new Error(problemMessage(error, "No fue posible crear la carpeta"));
  return data;
}
