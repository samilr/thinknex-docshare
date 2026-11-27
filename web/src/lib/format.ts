import dayjs from "dayjs";
import "dayjs/locale/es";
import relativeTime from "dayjs/plugin/relativeTime";

dayjs.extend(relativeTime);
dayjs.locale("es");

export const formatDateTime = (value: string | null | undefined): string =>
  value ? dayjs(value).format("DD MMM YYYY, HH:mm") : "—";

export const formatRelative = (value: string | null | undefined): string =>
  value ? dayjs(value).fromNow() : "—";

export const formatDay = (value: string): string => dayjs(value).format("ddd DD");

/** CSV compatible con Excel (separador ; y BOM UTF-8 para tildes). */
export function toCsv(rows: Record<string, unknown>[]): string {
  if (rows.length === 0) return "";
  const headers = Object.keys(rows[0]!);
  const escape = (value: unknown): string => {
    const text =
      value === null || value === undefined
        ? ""
        : typeof value === "object"
          ? JSON.stringify(value)
          : String(value);
    return /[;"\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  };
  return (
    "﻿" +
    [headers.join(";"), ...rows.map((r) => headers.map((h) => escape(r[h])).join(";"))].join("\r\n")
  );
}

export function downloadText(
  filename: string,
  content: string,
  mime = "text/csv;charset=utf-8",
): void {
  const url = URL.createObjectURL(new Blob([content], { type: mime }));
  const anchor = Object.assign(document.createElement("a"), { href: url, download: filename });
  anchor.click();
  URL.revokeObjectURL(url);
}
