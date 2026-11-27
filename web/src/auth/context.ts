import { createContext, useContext } from "react";
import type { Me, Session } from "../api/client";

export type Role = "ADMIN" | "SHARER" | "AUDITOR";

export interface AuthState {
  status: "loading" | "authenticated" | "anonymous";
  user: Me | null;

  loggedOut: boolean;
  login: (email: string, password: string) => Promise<Me>;
  logout: () => Promise<void>;
  applySession: (session: Session) => void;
  impersonate: (userId: string) => Promise<Me>;
  stopImpersonation: () => Promise<void>;
  hasRole: (...roles: Role[]) => boolean;
}

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth debe usarse dentro de <AuthProvider>");
  return ctx;
}
