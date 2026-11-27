import { api, type Schemas, unwrap } from "../../api/client";

export type Share = Schemas["ShareOut"];

export async function revealLink(shareId: string): Promise<string> {
  const share = unwrap(
    await api.GET("/api/v1/shares/{share_id}/link", { params: { path: { share_id: shareId } } }),
  );
  if (!share.link) throw new Error("Enlace no disponible");
  return share.link;
}
