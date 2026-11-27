import { createContext, useContext } from "react";
import type { Proposal } from "./api";

export interface OpenAssistantOptions {
  documentId?: string;
  documentTitle?: string;
  libraryId?: string;
  prompt?: string;
}

export interface AssistantState {
  available: boolean;
  openAssistant: (options?: OpenAssistantOptions) => void;
  /** Abre el asistente de compartir con los datos de una propuesta del asistente. */
  reviewShare: (proposal: Proposal, onDone: (ok: boolean, summary: string) => void) => void;
}

export const AssistantContext = createContext<AssistantState>({
  available: false,
  openAssistant: () => undefined,
  reviewShare: () => undefined,
});

export const useAssistant = () => useContext(AssistantContext);
