import { useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  type Me,
  onSessionChange,
  problemMessage,
  refreshSession,
  type Session,
  setSession,
} from "../api/client";
import { AuthContext, type AuthState, type Role } from "./context";

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AuthState["status"]>("loading");
  const [user, setUser] = useState<Me | null>(null);
  const [loggedOut, setLoggedOut] = useState(false);

  useEffect(() => {
    const unsubscribe = onSessionChange((session) => {
      setUser(session?.user ?? null);
      setStatus(session ? "authenticated" : "anonymous");
    });
    // Restaurar la sesión desde la cookie de refresh (si existe).
    void refreshSession();
    return () => {
      unsubscribe();
    };
  }, []);

  const applySession = useCallback((session: Session) => setSession(session), []);

  const login = useCallback(async (email: string, password: string) => {
    const { data, error } = await api.POST("/api/v1/auth/login", { body: { email, password } });
    if (!data) throw new Error(problemMessage(error, "No fue posible iniciar sesión"));
    setLoggedOut(false);
    setSession(data);
    return data.user;
  }, []);

  const logout = useCallback(async () => {
    await api.POST("/api/v1/auth/logout").catch(() => undefined);
    setLoggedOut(true);
    setSession(null);
    queryClient.clear();
  }, [queryClient]);

  const value = useMemo<AuthState>(
    () => ({
      status,
      user,
      loggedOut,
      login,
      logout,
      applySession,
      hasRole: (...roles: Role[]) => !!user && roles.some((r) => user.roles.includes(r)),
    }),
    [status, user, loggedOut, login, logout, applySession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
