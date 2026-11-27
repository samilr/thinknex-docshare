import {
  IconBooks,
  IconBriefcase,
  IconBuildingSkyscraper,
  IconFile,
  IconFileText,
  IconFileTypeDoc,
  IconFileTypePdf,
  IconFileTypeXls,
  IconPhoto,
  IconScale,
  IconSettings,
  IconSpeakerphone,
  IconUsersGroup,
} from "@tabler/icons-react";
import type { ComponentType } from "react";
import { fileKind } from "./files";

type Icon = ComponentType<{ size?: number; stroke?: number; color?: string }>;

const LIBRARY_ICONS: Record<string, Icon> = {
  legal: IconScale,
  rrhh: IconUsersGroup,
  operaciones: IconSettings,
  comercial: IconBriefcase,
  marketing: IconSpeakerphone,
  gerencia: IconBuildingSkyscraper,
};

export function LibraryIcon({ id, size = 18 }: { id: string; size?: number }) {
  const Component = LIBRARY_ICONS[id] ?? IconBooks;
  return <Component size={size} stroke={1.6} />;
}

const FILE_ICONS: Record<ReturnType<typeof fileKind>, [Icon, string]> = {
  pdf: [IconFileTypePdf, "red"],
  image: [IconPhoto, "grape"],
  text: [IconFileText, "gray"],
  word: [IconFileTypeDoc, "blue"],
  excel: [IconFileTypeXls, "green"],
  other: [IconFile, "gray"],
};

export function FileIcon({ mime, size = 22 }: { mime: string; size?: number }) {
  const [Component, color] = FILE_ICONS[fileKind(mime)];
  return <Component size={size} stroke={1.5} color={`var(--mantine-color-${color}-6)`} />;
}
